import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from fake_graph import FakeGraph
from helpers import cleanup, make_project
from igstories import cli, images
from igstories.catalog import load_catalog
from igstories.config import ImageSpec, load_settings
from igstories.graph import GraphClient, GraphError
from igstories.history import History
from igstories.hosting import HostingError, make_provider, preflight
from igstories.publisher import Publisher

HAS_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def make_video(path: Path, size="540x960", seconds=2, audio=False):
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=30"]
    if audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440"]
    cmd += ["-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p"]
    if audio:
        cmd += ["-c:a", "aac", "-shortest"]
    subprocess.run(cmd + [str(path)], check=True)


class StubSession:
    def __init__(self, ctype, status=200, length=None):
        self.ctype, self.status, self.length = ctype, status, length

    def head(self, url, **kw):
        from types import SimpleNamespace

        headers = {"Content-Type": self.ctype}
        if self.length:
            headers["Content-Length"] = str(self.length)
        return SimpleNamespace(status_code=self.status, headers=headers, history=[])


class PreflightVideoTests(unittest.TestCase):
    def test_video_types(self):
        preflight("http://x/a.mp4", video=True, session=StubSession("video/mp4"))
        preflight("http://x/a.mp4", video=True, session=StubSession("application/octet-stream"))
        with self.assertRaises(HostingError):
            preflight("http://x/a.mp4", video=True, session=StubSession("text/html"))
        with self.assertRaises(HostingError):
            preflight("http://x/a.mp4", video=True, session=StubSession("video/mp4", length=101 * 2**20))
        with self.assertRaises(HostingError):  # una imagen no puede ser video/mp4
            preflight("http://x/a.jpg", session=StubSession("video/mp4"))


@unittest.skipUnless(HAS_FFMPEG, "ffmpeg no disponible")
class PrepareVideoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="igvideo-"))
        self.src, self.ready = self.tmp / "src", self.tmp / "ready"
        self.src.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_compliant_video_is_copied_untouched(self):
        make_video(self.src / "Bueno.mp4", "540x960", audio=True)
        res = images.prepare_all(self.src, self.ready, ImageSpec())
        self.assertEqual(res[0].action, "created")
        self.assertEqual((self.ready / "bueno.mp4").read_bytes(), (self.src / "Bueno.mp4").read_bytes())

    def test_landscape_video_is_transcoded_to_9_16(self):
        make_video(self.src / "ancho.mp4", "640x360")
        images.prepare_all(self.src, self.ready, ImageSpec())
        info = images.probe_video(self.ready / "ancho.mp4")
        self.assertEqual((info["width"], info["height"]), (1080, 1920))
        self.assertTrue(images.video_is_compliant(info))

    def test_bad_video_does_not_stop_the_rest_and_manifest_is_stable(self):
        (self.src / "roto.mp4").write_bytes(b"no soy un video")
        make_video(self.src / "ok.mp4", "540x960")
        res = {r.source.name: r.action for r in images.prepare_all(self.src, self.ready, ImageSpec())}
        self.assertEqual(res["ok.mp4"], "created")
        self.assertIn(res["roto.mp4"], ("error", "created"))  # ffprobe no lo entiende -> ffmpeg falla
        manifest = (self.ready / ".manifest.json").read_text()
        os.utime(self.src / "ok.mp4", (time.time() + 500, time.time() + 500))  # cambia solo la fecha
        again = {r.source.name: r.action for r in images.prepare_all(self.src, self.ready, ImageSpec())}
        self.assertEqual(again["ok.mp4"], "unchanged")
        self.assertEqual(manifest.count("ok.mp4"), (self.ready / ".manifest.json").read_text().count("ok.mp4"))


class FingerprintTests(unittest.TestCase):
    def test_depends_on_content_not_mtime(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "a.png"
            f.write_bytes(b"abc")
            a = images._fingerprint(f, ImageSpec())
            os.utime(f, (time.time() + 999, time.time() + 999))
            self.assertEqual(a, images._fingerprint(f, ImageSpec()))
            f.write_bytes(b"abd")
            self.assertNotEqual(a, images._fingerprint(f, ImageSpec()))


class VideoPublishTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGraph()
        url = self.fake.start()
        self.root = make_project(graph_url=url, static_url=f"{url}/static")
        self.ready = self.root / "assets" / "ready"
        self.fake.ready_dir = self.ready
        (self.ready / "Mi-Video.mp4").write_bytes(b"\x00\x00\x00\x18ftypmp42")
        self.settings = load_settings(self.root / "config.toml")
        self.catalog = load_catalog(self.settings.stories_file, ready_dir=self.ready)

    def tearDown(self):
        self.fake.stop()
        cleanup(self.root)

    def test_autodiscovered_video_is_published_with_video_url(self):
        story = next(s for s in self.catalog if s.image == "Mi-Video.mp4")
        self.assertTrue(story.is_video)
        a = self.settings.account
        client = GraphClient(
            base_url=a.graph_base_url, api_version=a.api_version, access_token="t",
            ig_user_id=a.ig_user_id, timeout=2, max_retries=0, sleep=lambda s: None,
        )
        pub = Publisher(self.settings, self.catalog, History.load(self.settings.history_file),
                        client, make_provider(self.settings.hosting))
        out = pub.post_now(story.id)
        self.assertEqual(out.status, "published")
        create = next(c for c in self.fake.calls if c[0] == "create")
        self.assertIn("video_url", create[2])
        self.assertNotIn("image_url", create[2])


class DoctorTests(unittest.TestCase):
    def test_token_problems(self):
        good = "IG" + "A" * 120
        self.assertEqual(cli._token_problems(good), [])
        self.assertTrue(cli._token_problems(""))
        self.assertTrue(cli._token_problems(good + "\n"))
        self.assertTrue(cli._token_problems('"' + good + '"'))
        self.assertTrue(cli._token_problems("IGAA short"))
        self.assertTrue(cli._token_problems("EAAB" + "A" * 120))
        for p in cli._token_problems(good + " x"):
            self.assertNotIn(good, p)

    def test_graph_error_describe_includes_codes_but_not_token(self):
        e = GraphError("Failed to decode", status=400, code=1, subcode=2, trace_id="T", error_type="OAuthException")
        d = e.describe()
        for part in ("Failed to decode", "code=1", "subcode=2", "OAuthException", "trace=T"):
            self.assertIn(part, d)


if __name__ == "__main__":
    unittest.main()
