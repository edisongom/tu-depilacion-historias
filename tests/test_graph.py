import unittest

import requests
from fake_graph import FakeGraph
from igstories.graph import (
    AmbiguousResult,
    ContainerError,
    GraphClient,
    GraphError,
    refresh_long_lived_token,
)


class StubResponse:
    def __init__(self, status=200, body=None, headers=None):
        self.status_code = status
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self.ok = status < 400

    def json(self):
        return self._body


class StubSession:
    """Respuestas programadas; cada elemento es una Response o una excepción."""

    def __init__(self, *items):
        self.items = list(items)
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(session, **kw):
    return GraphClient(
        base_url="https://g.test", api_version="v1", access_token="SECRET-TOKEN", ig_user_id="123",
        session=session, sleep=lambda s: None, max_retries=2, **kw,
    )


class GraphClientTests(unittest.TestCase):
    def test_create_container_sends_stories_params_in_body(self):
        s = StubSession(StubResponse(200, {"id": "c1"}))
        self.assertEqual(client(s).create_story_container(image_url="https://x/y.jpg"), "c1")
        method, url, kw = s.requests[0]
        self.assertEqual((method, url), ("POST", "https://g.test/v1/123/media"))
        self.assertEqual(kw["data"]["media_type"], "STORIES")
        self.assertEqual(kw["data"]["image_url"], "https://x/y.jpg")
        self.assertNotIn("params", kw)

    def test_requires_exactly_one_media_source(self):
        c = client(StubSession())
        with self.assertRaises(ValueError):
            c.create_story_container()
        with self.assertRaises(ValueError):
            c.create_story_container(image_url="a", video_url="b")

    def test_transient_errors_are_retried_then_succeed(self):
        err = StubResponse(500, {"error": {"message": "boom", "code": 2}})
        s = StubSession(err, StubResponse(200, {"id": "c1"}))
        self.assertEqual(client(s).create_story_container(image_url="u"), "c1")
        self.assertEqual(len(s.requests), 2)

    def test_non_transient_error_is_not_retried_and_hides_token(self):
        body = {"error": {"message": "Invalid SECRET-TOKEN", "code": 190, "fbtrace_id": "T"}}
        s = StubSession(StubResponse(400, body))
        with self.assertRaises(GraphError) as ctx:
            client(s).whoami()
        self.assertTrue(ctx.exception.is_auth)
        self.assertNotIn("SECRET-TOKEN", str(ctx.exception))
        self.assertEqual(len(s.requests), 1)

    def test_retries_stop_after_max(self):
        err = StubResponse(500, {"error": {"message": "x", "code": 2}})
        s = StubSession(err, err, err)
        with self.assertRaises(GraphError):
            client(s).whoami()
        self.assertEqual(len(s.requests), 3)  # 1 intento + 2 reintentos

    def test_publish_timeout_is_ambiguous_and_never_retried(self):
        s = StubSession(requests.ReadTimeout("read timed out SECRET-TOKEN"))
        with self.assertRaises(AmbiguousResult) as ctx:
            client(s).publish("c1")
        self.assertNotIn("SECRET-TOKEN", str(ctx.exception))
        self.assertEqual(len(s.requests), 1)

    def test_publish_5xx_is_ambiguous(self):
        s = StubSession(StubResponse(503, {}))
        with self.assertRaises(AmbiguousResult):
            client(s).publish("c1")

    def test_publish_retries_only_on_rate_limit(self):
        limited = StubResponse(400, {"error": {"message": "limit", "code": 4}})
        s = StubSession(limited, StubResponse(200, {"id": "m1"}))
        self.assertEqual(client(s).publish("c1"), "m1")

    def test_wait_until_ready_states(self):
        ok = StubSession(
            StubResponse(200, {"status_code": "IN_PROGRESS"}), StubResponse(200, {"status_code": "FINISHED"})
        )
        client(ok).wait_until_ready("c1", interval=0, timeout=5)
        err = StubSession(StubResponse(200, {"status_code": "ERROR", "status": "bad image"}))
        with self.assertRaises(ContainerError):
            client(err).wait_until_ready("c1", interval=0, timeout=5)

    def test_wait_until_ready_times_out(self):
        ticks = iter(range(0, 1000, 10))
        c = GraphClient(
            base_url="https://g.test", api_version="v1", access_token="t", ig_user_id="1",
            session=StubSession(*[StubResponse(200, {"status_code": "IN_PROGRESS"})] * 10),
            sleep=lambda s: None, clock=lambda: next(ticks),
        )
        with self.assertRaises(ContainerError):
            c.wait_until_ready("c1", interval=0, timeout=25)

    def test_refresh_long_lived_token(self):
        s = StubSession(StubResponse(200, {"access_token": "NEW", "expires_in": 5184000}))
        s.get = lambda url, **kw: s.request("GET", url, **kw)
        info = refresh_long_lived_token("OLD", session=s)
        self.assertEqual((info.access_token, info.expires_in), ("NEW", 5184000))
        self.assertEqual(s.requests[0][2]["params"]["grant_type"], "ig_refresh_token")

    def test_against_fake_server(self):
        fake = FakeGraph()
        url = fake.start()
        try:
            c = GraphClient(base_url=url, api_version="", access_token="t", ig_user_id="123", timeout=2)
            cid = c.create_story_container(image_url="http://x/a.jpg")
            c.wait_until_ready(cid, interval=0, timeout=2)
            media = c.publish(cid)
            self.assertEqual(media, "media-1")
            self.assertEqual(len(c.active_stories()), 1)
            self.assertEqual(c.whoami()["username"], "tu_depilacion")
        finally:
            fake.stop()


if __name__ == "__main__":
    unittest.main()


class TokenRefreshCliTests(unittest.TestCase):
    def _run(self, refresh, run):
        import argparse
        from unittest import mock

        from igstories import cli
        from igstories.config import AccountConfig

        settings = mock.Mock()
        settings.account = AccountConfig(ig_user_id="1")
        args = argparse.Namespace(gh_secret="IG_ACCESS_TOKEN", gh_repo="o/r", print_token=False)
        with (
            mock.patch.dict("os.environ", {"IG_ACCESS_TOKEN": "OLD"}),
            mock.patch.object(cli, "refresh_long_lived_token", refresh),
            mock.patch.object(cli.subprocess, "run", run),
        ):
            return cli.cmd_token_refresh(args, settings, None)

    def test_success_passes_token_by_stdin_not_argv(self):
        from igstories.graph import TokenInfo

        calls = []

        def run(cmd, **kw):
            calls.append((cmd, kw))

        rc = self._run(lambda tok: TokenInfo("NEW-SECRET", 5184000), run)
        self.assertEqual(rc, 0)
        cmd, kw = calls[0]
        self.assertNotIn("NEW-SECRET", " ".join(cmd))
        self.assertEqual(kw["input"], b"NEW-SECRET")

    def test_gh_failure_returns_error_without_leaking_token(self):
        import subprocess

        from igstories.graph import TokenInfo

        def run(cmd, **kw):
            raise subprocess.CalledProcessError(1, cmd, stderr=b"HTTP 403")

        self.assertEqual(self._run(lambda tok: TokenInfo("NEW", 1), run), 1)

    def test_refresh_failure_returns_error(self):
        def bad(tok):
            raise GraphError("expirado", status=400, code=190)

        self.assertEqual(self._run(bad, lambda *a, **k: None), 1)
