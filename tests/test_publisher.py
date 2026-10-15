import unittest

from fake_graph import FakeGraph
from helpers import cleanup, make_project, santiago
from igstories.catalog import load_catalog
from igstories.config import load_settings
from igstories.graph import GraphClient
from igstories.history import History
from igstories.hosting import make_provider
from igstories.publisher import Publisher

NOW = santiago(2026, 10, 19, 13, 0)  # lunes, pasado el slot de 12:30


class PublisherIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeGraph()
        url = self.fake.start()
        self.root = make_project(graph_url=url, static_url=f"{url}/static")
        self.fake.ready_dir = self.root / "assets" / "ready"
        self.settings = load_settings(self.root / "config.toml")
        self.catalog = load_catalog(self.settings.stories_file)

    def tearDown(self):
        self.fake.stop()
        cleanup(self.root)

    def publisher(self, timeout=1.5):
        a = self.settings.account
        client = GraphClient(
            base_url=a.graph_base_url, api_version=a.api_version, access_token="t",
            ig_user_id=a.ig_user_id, timeout=timeout, max_retries=0, sleep=lambda s: None,
        )
        return Publisher(
            self.settings, self.catalog, History.load(self.settings.history_file), client,
            make_provider(self.settings.hosting),
        )

    def test_publishes_once_and_is_idempotent(self):
        out = self.publisher().run_due(NOW)
        self.assertEqual([o.status for o in out], ["published"])
        # Segunda ejecución (proceso nuevo, historial recargado desde disco): no hace nada.
        out2 = self.publisher().run_due(NOW)
        self.assertEqual([o.status for o in out2], ["already-done"])
        self.assertEqual(self.fake.count("publish"), 1)
        self.assertEqual(len(self.fake.stories), 1)

    def test_not_due_yet(self):
        self.assertEqual(self.publisher().run_due(santiago(2026, 10, 19, 12, 0)), [])
        self.assertEqual(self.fake.count("create"), 0)

    def test_dry_run_touches_nothing(self):
        out = self.publisher().run_due(NOW, dry_run=True)
        self.assertEqual(out[0].status, "dry-run")
        self.assertEqual(self.fake.count("create"), 0)
        self.assertFalse(self.settings.history_file.exists())

    def test_failure_then_retry_counts_attempts(self):
        self.fake.script["create"] = [("status", 400, {"error": {"message": "bad", "code": 100}})]
        first = self.publisher().run_due(NOW)
        self.assertEqual(first[0].status, "failed")
        second = self.publisher().run_due(NOW)
        self.assertEqual(second[0].status, "published")
        entry = History.load(self.settings.history_file).get("2026-10-19:midday")
        self.assertEqual((entry.status, entry.attempts), ("published", 2))

    def test_gives_up_after_max_attempts(self):
        err = ("status", 400, {"error": {"message": "bad", "code": 100}})
        self.fake.script["create"] = [err] * 5
        for _ in range(5):
            self.publisher().run_due(NOW)
        self.assertEqual(self.fake.count("create"), 3)  # max_attempts = 3

    def test_missing_image_fails_without_api_calls(self):
        (self.root / "assets" / "ready" / "a1.jpg").unlink()
        (self.root / "assets" / "ready" / "a2.jpg").unlink()
        out = self.publisher().run_due(NOW)
        self.assertEqual(out[0].status, "failed")
        self.assertEqual(self.fake.count("create"), 0)

    def test_preflight_rejects_non_jpeg_url(self):
        (self.root / "assets" / "ready" / "a1.jpg").unlink()  # 404 en el hosting
        (self.root / "assets" / "ready" / "a2.jpg").unlink()
        out = self.publisher().run_due(NOW)
        self.assertEqual(out[0].status, "failed")

    def test_ambiguous_publish_that_did_happen_is_reconciled_not_duplicated(self):
        self.fake.script["publish"] = ["publish-then-hang"]
        out = self.publisher(timeout=0.5).run_due(NOW)
        self.assertEqual(out[0].status, "published")
        self.assertEqual(self.fake.count("publish"), 1)
        self.assertEqual(len(self.fake.stories), 1)
        self.assertEqual(self.publisher().run_due(NOW)[0].status, "already-done")

    def test_ambiguous_publish_that_did_not_happen_is_retried_later(self):
        self.fake.script["publish"] = ["hang"]
        out = self.publisher(timeout=0.5).run_due(NOW)
        self.assertEqual(out[0].status, "failed")
        again = self.publisher().run_due(NOW)
        self.assertEqual(again[0].status, "published")
        self.assertEqual(len(self.fake.stories), 1)

    def test_crash_while_publishing_is_reconciled_on_next_run(self):
        # Simula un proceso que murió tras escribir 'publishing' y tras publicar de verdad.
        from igstories.history import Entry, utcnow

        self.fake._publish_story()
        h = History.load(self.settings.history_file)
        h.put(Entry("2026-10-19:midday", "2026-10-19", "midday", "a1", "publishing",
                    attempts=1, container_id="c", publish_started_at=utcnow().isoformat(timespec="seconds")))
        h.save()
        out = self.publisher().run_due(NOW)
        self.assertEqual(out[0].status, "published")
        self.assertEqual(self.fake.count("publish"), 0)  # no volvió a publicar

    def test_post_now_records_history(self):
        out = self.publisher().post_now("b1")
        self.assertEqual(out.status, "published")
        self.assertEqual(len(self.fake.stories), 1)


if __name__ == "__main__":
    unittest.main()
