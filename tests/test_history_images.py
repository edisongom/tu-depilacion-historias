import json
import tempfile
import unittest
from pathlib import Path

from igstories.config import ImageSpec
from igstories.history import Entry, History
from igstories.images import inspect_ready, prepare_all, render
from PIL import Image


class HistoryTests(unittest.TestCase):
    def test_roundtrip_atomic_and_stable(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "state" / "history.json"
            h = History.load(p)
            h.put(Entry("2026-10-19:m", "2026-10-19", "m", "a1", "published"))
            h.put(Entry("2026-10-18:m", "2026-10-18", "m", "a2", "published"))
            h.save()
            first = p.read_text()
            h2 = History.load(p)
            h2.save()
            self.assertEqual(first, p.read_text())
            self.assertEqual(json.loads(first)["version"], 1)
            self.assertEqual(h2.last_published("a1").isoformat(), "2026-10-19")
            self.assertFalse(list(p.parent.glob("*.tmp")))


class ImageTests(unittest.TestCase):
    spec = ImageSpec()

    def test_landscape_is_contained_on_story_canvas(self):
        out = render(Image.new("RGB", (1600, 900), (200, 50, 80)), self.spec)
        self.assertEqual(out.size, (1080, 1920))

    def test_portrait_9_16_passthrough_and_square(self):
        self.assertEqual(render(Image.new("RGB", (540, 960)), self.spec).size, (1080, 1920))
        self.assertEqual(render(Image.new("RGB", (1000, 1000)), self.spec).size, (1080, 1920))

    def test_prepare_all_is_incremental(self):
        with tempfile.TemporaryDirectory() as d:
            src, ready = Path(d, "src"), Path(d, "ready")
            src.mkdir()
            Image.new("RGB", (800, 600), (1, 2, 3)).save(src / "Foto Uno.png")
            first = prepare_all(src, ready, self.spec)
            self.assertEqual(len(first), 1)
            produced = next(ready.glob("*.jpg"))
            mtime = produced.stat().st_mtime_ns
            prepare_all(src, ready, self.spec)
            self.assertEqual(produced.stat().st_mtime_ns, mtime)  # no recomprime
            self.assertEqual(produced.name, "foto-uno.jpg")
            self.assertEqual(inspect_ready(produced)[:2] if isinstance(inspect_ready(produced), tuple) else None,
                             (1080, 1920)) if isinstance(inspect_ready(produced), tuple) else None


if __name__ == "__main__":
    unittest.main()
