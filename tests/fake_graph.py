"""Servidor HTTP que imita lo mínimo de la Graph API y sirve imágenes estáticas.

Permite probar el flujo completo (contenedor → estado → publicar → reconciliar) sin red real
ni credenciales. El comportamiento se controla con ``FakeGraph.script``.
"""

from __future__ import annotations

import datetime as dt
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


class FakeGraph:
    def __init__(self, ready_dir: Path | None = None, ig_user_id: str = "123"):
        self.ig_user_id = ig_user_id
        self.ready_dir = ready_dir
        self.calls: list[tuple[str, str, dict]] = []
        self.stories: list[dict] = []
        # script: respuestas forzadas por operación. Valores: dict JSON | ("status", int, dict)
        # | "hang" (no responde: provoca timeout en el cliente) | "publish-then-hang"
        self.script: dict[str, list] = {}
        self._n = 0
        self._server: ThreadingHTTPServer | None = None
        self._release = threading.Event()

    # ------------------------------------------------------------------ ciclo de vida
    def start(self) -> str:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # silencio en los tests
                pass

            def _send(self, status: int, body: dict | bytes, ctype="application/json"):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(data)

            def _params(self) -> dict:
                url = urlparse(self.path)
                params = {k: v[0] for k, v in parse_qs(url.query).items()}
                length = int(self.headers.get("Content-Length") or 0)
                if length:
                    params.update({k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()})
                return params

            def do_HEAD(self):
                self.do_GET()

            def do_GET(self):
                path = urlparse(self.path).path
                if path.startswith("/static/") and fake.ready_dir:
                    f = fake.ready_dir / path.removeprefix("/static/")
                    if f.exists():
                        return self._send(200, f.read_bytes(), "image/jpeg")
                    return self._send(404, b"nope", "text/plain")
                fake._handle(self, "GET", path, self._params())

            def do_POST(self):
                fake._handle(self, "POST", urlparse(self.path).path, self._params())

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        return self.url

    @property
    def url(self) -> str:
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def stop(self) -> None:
        self._release.set()
        if self._server:
            self._server.shutdown()
            self._server.server_close()

    # ------------------------------------------------------------------ lógica de la API
    def _next(self, op: str):
        queue = self.script.get(op)
        return queue.pop(0) if queue else None

    def _handle(self, h, method: str, path: str, params: dict) -> None:
        params = {k: v for k, v in params.items() if k != "access_token"}
        op = None
        if method == "POST" and path.endswith("/media_publish"):
            op = "publish"
        elif method == "POST" and path.endswith("/media"):
            op = "create"
        elif method == "GET" and path.endswith("/stories"):
            op = "stories"
        elif method == "GET" and path.endswith("/content_publishing_limit"):
            op = "limit"
        elif method == "GET" and "fields" in params and "status_code" in params["fields"]:
            op = "status"
        elif method == "GET":
            op = "get"
        self.calls.append((op or "?", path, params))

        forced = self._next(op) if op else None
        if forced == "hang" or forced == "publish-then-hang":
            if forced == "publish-then-hang":
                self._publish_story()
            self._release.wait(timeout=5)
            return
        if isinstance(forced, tuple) and forced[0] == "status":
            return h._send(forced[1], forced[2])
        if isinstance(forced, dict):
            return h._send(200, forced)

        if op == "create":
            if params.get("media_type") != "STORIES" or not params.get("image_url"):
                return h._send(400, {"error": {"message": "bad params", "code": 100}})
            self._n += 1
            return h._send(200, {"id": f"container-{self._n}"})
        if op == "status":
            return h._send(200, {"status_code": "FINISHED"})
        if op == "publish":
            media = self._publish_story()
            return h._send(200, {"id": media})
        if op == "stories":
            return h._send(200, {"data": self.stories})
        if op == "limit":
            return h._send(200, {"data": [{"quota_usage": len(self.stories), "config": {"quota_total": 100}}]})
        return h._send(200, {"id": path.rsplit("/", 1)[-1], "username": "tu_depilacion", "permalink": "https://instagram.com/stories/x"})

    def _publish_story(self) -> str:
        media = f"media-{len(self.stories) + 1}"
        ts = dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S+0000")
        self.stories.append({"id": media, "timestamp": ts, "permalink": f"https://instagram.com/stories/{media}"})
        return media

    def count(self, op: str) -> int:
        return sum(1 for c in self.calls if c[0] == op)
