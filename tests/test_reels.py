import unittest

from fake_graph import FakeGraph
from helpers import cleanup, make_project, santiago

from igstories.catalog import load_catalog
from igstories.config import load_settings
from igstories.graph import GraphClient
from igstories.history import History
from igstories.hosting import make_provider
from igstories.publisher import Publisher, build_plan

REELS = """
[[slots]]
name = "jueves-reel"
format = "reel"
time = "20:00"
days = ["thu"]
grace_minutes = 240

[reels]
dir = "assets/reels"
base_url = "https://example.com/reels"
caption = "Agende su hora #laserena"
"""


class ReelTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGraph()
        url = self.fake.start()
        self.root = make_project(graph_url=url, static_url=f"{url}/static")
        cfg = self.root / "config.toml"
        cfg.write_text(cfg.read_text(encoding="utf-8") + REELS, encoding="utf-8")
        self.reels = self.root / "assets" / "reels"
        self.reels.mkdir()
        for n in ("02-b.mp4", "01-a.mp4"):
            (self.reels / n).write_bytes(b"\x00\x00\x00\x18ftypmp42")
        (self.reels / "02-b.txt").write_text("Texto propio\n", encoding="utf-8")
        self.settings = load_settings(cfg)
        self.catalog = load_catalog(self.settings.stories_file, ready_dir=self.root / "assets" / "ready")
        self.history = History.load(self.settings.history_file)

    def tearDown(self):
        self.fake.stop()
        cleanup(self.root)

    def _pub(self):
        a = self.settings.account
        client = GraphClient(
            base_url=a.graph_base_url, api_version=a.api_version, access_token="t",
            ig_user_id=a.ig_user_id, timeout=2, max_retries=0, sleep=lambda s: None,
        )
        return Publisher(self.settings, self.catalog, self.history, client,
                         make_provider(self.settings.hosting), check_url=False)

    def _reel_creates(self):
        return [c[2] for c in self.fake.calls if c[0] == "create" and c[2].get("media_type") == "REELS"]

    def test_thursday_publishes_reels_in_order_without_repeating(self):
        pub = self._pub()
        pub.run_due(santiago(2026, 11, 19, 20, 30))  # jueves
        pub.run_due(santiago(2026, 11, 26, 20, 5))   # jueves siguiente
        creates = self._reel_creates()
        self.assertEqual(len(creates), 2)
        self.assertTrue(creates[0]["video_url"].endswith("/01-a.mp4"))
        self.assertEqual(creates[0]["caption"], "Agende su hora #laserena")
        self.assertEqual(creates[0]["share_to_feed"], "true")
        self.assertTrue(creates[1]["video_url"].endswith("/02-b.mp4"))
        self.assertEqual(creates[1]["caption"], "Texto propio")

        out = pub.run_due(santiago(2026, 12, 3, 20, 10))  # ya no quedan
        reel = [o for o in out if o.key.endswith("jueves-reel")]
        self.assertEqual(reel[0].status, "skipped")
        self.assertEqual(len(self._reel_creates()), 2)

    def test_rerun_same_thursday_does_not_duplicate(self):
        pub = self._pub()
        pub.run_due(santiago(2026, 11, 19, 20, 1))
        pub.run_due(santiago(2026, 11, 19, 20, 31))
        self.assertEqual(len(self._reel_creates()), 1)

    def test_not_on_other_days_or_too_late(self):
        pub = self._pub()
        pub.run_due(santiago(2026, 11, 18, 20, 30))  # miércoles
        pub.run_due(santiago(2026, 11, 20, 1, 0))    # viernes 01:00, fuera de la gracia
        self.assertEqual(self._reel_creates(), [])

    def test_plan_shows_next_reels(self):
        rows = build_plan(self.settings, self.catalog, self.history,
                          santiago(2026, 11, 19, 0, 0).date(), 8)
        reel = [r for r in rows if r.slot == "jueves-reel"]
        self.assertEqual([r.story_id for r in reel], ["reel:01-a.mp4", "reel:02-b.mp4"])


if __name__ == "__main__":
    unittest.main()
