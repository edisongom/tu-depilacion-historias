import datetime as dt
import unittest
from pathlib import Path

from helpers import cleanup, make_project, santiago
from igstories.catalog import load_catalog
from igstories.config import ConfigError, Override, load_settings
from igstories.history import Entry, History
from igstories.publisher import build_plan
from igstories.schedule import OverlayHistory, due_slots, find_override, pick_story


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.root = make_project()
        self.settings = load_settings(self.root / "config.toml")
        self.catalog = load_catalog(self.settings.stories_file)
        self.slot = self.settings.slots[0]

    def tearDown(self):
        cleanup(self.root)

    def test_weekday_tags_filter_pool(self):
        monday = dt.date(2026, 10, 19)  # lunes -> tag "a"
        pick = pick_story(self.slot, monday, self.catalog, OverlayHistory(History(Path("x"))))
        self.assertIn(pick.story.id, {"a1", "a2"})
        tuesday = dt.date(2026, 10, 20)  # martes -> tag "b"
        pick = pick_story(self.slot, tuesday, self.catalog, OverlayHistory(History(Path("x"))))
        self.assertEqual(pick.story.id, "b1")

    def test_least_recent_first_and_deterministic(self):
        hist = History(Path("x"))
        hist.put(Entry("2026-10-12:midday", "2026-10-12", "midday", "a1", "published"))
        pick = pick_story(self.slot, dt.date(2026, 10, 19), self.catalog, hist)
        self.assertEqual(pick.story.id, "a2")  # a2 nunca se mostró
        again = pick_story(self.slot, dt.date(2026, 10, 19), self.catalog, hist)
        self.assertEqual(pick.story.id, again.story.id)

    def test_cooldown_relaxes_when_pool_exhausted(self):
        hist = History(Path("x"))
        hist.put(Entry("2026-10-17:midday", "2026-10-17", "midday", "a1", "published"))
        hist.put(Entry("2026-10-18:midday", "2026-10-18", "midday", "a2", "published"))
        pick = pick_story(self.slot, dt.date(2026, 10, 19), self.catalog, hist, default_cooldown=3)
        self.assertEqual(pick.reason, "relaxed-cooldown")
        self.assertEqual(pick.story.id, "a1")  # la menos reciente

    def test_failed_attempts_do_not_count_as_shown(self):
        hist = History(Path("x"))
        hist.put(Entry("2026-10-18:midday", "2026-10-18", "midday", "a1", "failed"))
        self.assertIsNone(hist.last_published("a1"))

    def test_override_story_and_skip(self):
        day = dt.date(2026, 10, 19)
        forced = (Override(day, story="b1"),)
        self.assertEqual(pick_story(self.slot, day, self.catalog, History(Path("x")), forced).story.id, "b1")
        skip = (Override(day, slot="midday", skip=True), Override(day, story="a1"))
        pick = pick_story(self.slot, day, self.catalog, History(Path("x")), skip)
        self.assertEqual(pick.reason, "skip")  # el override específico del slot gana
        self.assertIs(find_override(skip, day, "midday"), skip[0])
        bad = (Override(day, story="no-existe"),)
        self.assertEqual(pick_story(self.slot, day, self.catalog, History(Path("x")), bad).reason, "bad-override")

    def test_story_active_window(self):
        from igstories.catalog import Story

        s = Story("x", "x.jpg", active_from=dt.date(2026, 12, 1), active_to=dt.date(2026, 12, 25))
        self.assertFalse(s.is_active_on(dt.date(2026, 11, 30)))
        self.assertTrue(s.is_active_on(dt.date(2026, 12, 25)))
        self.assertFalse(s.is_active_on(dt.date(2026, 12, 26)))

    def test_plan_simulates_without_repeats_inside_cooldown(self):
        rows = build_plan(self.settings, self.catalog, History(Path("x")), dt.date(2026, 10, 19), 14)
        self.assertEqual(len(rows), 14)
        last: dict[str, dt.date] = {}
        for r in rows:
            if r.story_id in last and r.reason == "least-recent":
                self.assertGreaterEqual((r.day - last[r.story_id]).days, 3)
            last[r.story_id] = r.day

    def test_due_slots_window_and_timezone(self):
        before = santiago(2026, 10, 19, 12, 29)
        self.assertEqual(due_slots(self.settings, before), [])
        on_time = santiago(2026, 10, 19, 12, 31)
        self.assertEqual([d.key for d in due_slots(self.settings, on_time)], ["2026-10-19:midday"])
        late_but_in_grace = santiago(2026, 10, 19, 18, 29)
        self.assertEqual(len(due_slots(self.settings, late_but_in_grace)), 1)
        expired = santiago(2026, 10, 19, 18, 31)
        self.assertEqual(due_slots(self.settings, expired), [])

    def test_due_slot_crossing_midnight_uses_previous_day(self):
        text = (self.root / "config.toml").read_text().replace('time = "12:30"', 'time = "22:00"')
        (self.root / "config.toml").write_text(text)
        settings = load_settings(self.root / "config.toml")
        now = santiago(2026, 10, 20, 1, 0)  # 01:00 del martes; el slot de 22:00 del lunes sigue vigente
        self.assertEqual([d.key for d in due_slots(settings, now)], ["2026-10-19:midday"])

    def test_config_errors_are_aggregated(self):
        bad = self.root / "bad.toml"
        bad.write_text('timezone = "Marte/Olimpo"\n[account]\n[hosting]\nprovider="static"\n')
        with self.assertRaises(ConfigError) as ctx:
            load_settings(bad)
        msg = str(ctx.exception)
        self.assertIn("timezone", msg)
        self.assertIn("ig_user_id", msg)
        self.assertIn("base_url", msg)
        self.assertIn("slots", msg)


if __name__ == "__main__":
    unittest.main()


class WindowAndDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.root = make_project()
        text = (self.root / "config.toml").read_text()
        text = text.replace('time = "12:30"', 'window = ["08:00", "11:00"]')
        text += '\n[[slots]]\nname = "noche"\nwindow = ["20:00", "23:00"]\n'
        (self.root / "config.toml").write_text(text)
        self.settings = load_settings(self.root / "config.toml")

    def tearDown(self):
        cleanup(self.root)

    def test_window_time_is_stable_inside_window_and_varies(self):
        from igstories.schedule import scheduled_time

        morning, night = self.settings.slots
        seen = set()
        for i in range(60):
            day = dt.date(2026, 10, 1) + dt.timedelta(days=i)
            t = scheduled_time(morning, day)
            self.assertEqual(t, scheduled_time(morning, day))  # estable
            self.assertTrue(dt.time(8, 0) <= t <= dt.time(11, 0))
            n = scheduled_time(night, day)
            self.assertTrue(dt.time(20, 0) <= n <= dt.time(23, 0))
            gap = (dt.datetime.combine(day, n) - dt.datetime.combine(day, t)).total_seconds() / 3600
            self.assertTrue(9 <= gap <= 15)
            seen.add(t)
        self.assertGreater(len(seen), 20)

    def test_due_slots_follow_the_random_time(self):
        from igstories.schedule import scheduled_time

        day = dt.date(2026, 10, 19)
        t = scheduled_time(self.settings.slots[0], day)
        before = santiago(2026, 10, 19, t.hour, t.minute) - dt.timedelta(minutes=1)
        after = santiago(2026, 10, 19, t.hour, t.minute) + dt.timedelta(minutes=1)
        self.assertEqual(due_slots(self.settings, before), [])
        self.assertEqual([d.slot.name for d in due_slots(self.settings, after)], ["midday"])

    def test_window_validation(self):
        bad = self.root / "bad.toml"
        text = (self.root / "config.toml").read_text().replace('window = ["20:00", "23:00"]', 'window = ["23:00", "20:00"]')
        bad.write_text(text)
        with self.assertRaises(ConfigError):
            load_settings(bad)
        bad.write_text(text.replace('window = ["23:00", "20:00"]', ""))
        with self.assertRaises(ConfigError):
            load_settings(bad)

    def test_autodiscover_adds_new_images_and_dedupes(self):
        from PIL import Image

        ready = self.root / "assets" / "ready"
        Image.new("RGB", (1080, 1920)).save(ready / "Mi Foto Nueva.jpg")
        Image.new("RGB", (1080, 1920)).save(ready / "a1-.jpg")
        cat = load_catalog(self.settings.stories_file, ready_dir=ready, auto_tag="libre")
        ids = {s.id for s in cat}
        self.assertEqual(len(cat), 5)
        self.assertIn("mi-foto-nueva", ids)
        self.assertEqual(cat.get("mi-foto-nueva").tags, ("libre",))
        self.assertEqual(sum(1 for s in cat if s.image == "a1.jpg"), 1)  # no duplica los ya listados
        self.assertEqual(len(load_catalog(self.settings.stories_file)), 3)  # sin ready_dir = como antes

    def test_never_shown_images_come_first_and_shuffle_is_stable(self):
        from igstories.schedule import pick_story

        cat = load_catalog(self.settings.stories_file)
        slot = self.settings.slots[1]  # "noche": sin tags
        hist = History(Path("x"))
        hist.put(Entry("2026-10-18:m", "2026-10-18", "m", "a1", "published"))
        day = dt.date(2026, 10, 19)
        first = pick_story(slot, day, cat, hist, shuffle=True)
        self.assertIn(first.story.id, {"a2", "b1"})  # a1 está en cooldown
        self.assertEqual(first.story.id, pick_story(slot, day, cat, hist, shuffle=True).story.id)
        picks = {pick_story(slot, dt.date(2026, 11, 1) + dt.timedelta(days=i), cat, History(Path("x")), shuffle=True).story.id
                 for i in range(20)}
        self.assertGreater(len(picks), 1)  # el desempate varía con el día
