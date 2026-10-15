"""Cliente mínimo de la Instagram Graph API para publicar historias.

Flujo oficial (Content Publishing):

1. ``POST /{ig-user-id}/media``          media_type=STORIES + image_url   -> id del contenedor
2. ``GET  /{container-id}?fields=status_code``                            -> FINISHED | ERROR…
3. ``POST /{ig-user-id}/media_publish``  creation_id=<contenedor>          -> id del medio

Decisiones de diseño:

* El token nunca se imprime: todo texto de error pasa por ``_redact``.
* Las llamadas idempotentes (GET, crear contenedor) se reintentan con backoff exponencial.
* ``media_publish`` NO es idempotente: ante un timeout o un 5xx no sabemos si Instagram
  publicó. En vez de reintentar a ciegas lanza :class:`AmbiguousResult` y el publicador
  reconcilia contra ``/stories`` antes de decidir.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

RATE_LIMIT_CODES = {4, 17, 32, 613}
TRANSIENT_CODES = {1, 2, 341}


class GraphError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: int | None = None,
        subcode: int | None = None,
        trace_id: str | None = None,
    ):
        super().__init__(message)
        self.status = status
        self.code = code
        self.subcode = subcode
        self.trace_id = trace_id

    @property
    def is_rate_limit(self) -> bool:
        return self.code in RATE_LIMIT_CODES

    @property
    def is_transient(self) -> bool:
        return self.is_rate_limit or self.code in TRANSIENT_CODES or (self.status or 0) >= 500

    @property
    def is_auth(self) -> bool:
        return self.code == 190 or self.status == 401


class AmbiguousResult(Exception):
    """No sabemos si una operación no idempotente llegó a ejecutarse."""


class ContainerError(Exception):
    """El contenedor de medios quedó en ERROR / EXPIRED o no terminó a tiempo."""


@dataclass(frozen=True)
class TokenInfo:
    access_token: str
    expires_in: int


class GraphClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_version: str,
        access_token: str,
        ig_user_id: str,
        session: requests.Session | None = None,
        timeout: float = 30.0,
        max_retries: int = 4,
        sleep=time.sleep,
        clock=time.monotonic,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version.strip("/")
        self.ig_user_id = ig_user_id
        self._token = access_token
        self._http = session or requests.Session()
        self._timeout = timeout
        self._max_retries = max_retries
        self._sleep = sleep
        self._clock = clock

    # ------------------------------------------------------------------ infraestructura
    def _url(self, path: str) -> str:
        prefix = f"/{self.api_version}" if self.api_version else ""
        return f"{self.base_url}{prefix}/{path.lstrip('/')}"

    def _redact(self, text: str) -> str:
        return text.replace(self._token, "***") if self._token else text

    def _backoff(self, attempt: int, *, rate_limited: bool, retry_after: str | None) -> float:
        if retry_after and retry_after.isdigit():
            return min(float(retry_after), 120.0)
        base = 30.0 if rate_limited else 2.0**attempt
        return min(base, 120.0) + random.random()

    @staticmethod
    def _to_error(resp: requests.Response) -> GraphError:
        try:
            err = resp.json().get("error", {})
        except ValueError:
            err = {}
        return GraphError(
            err.get("message") or f"HTTP {resp.status_code}",
            status=resp.status_code,
            code=err.get("code"),
            subcode=err.get("error_subcode"),
            trace_id=err.get("fbtrace_id"),
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        idempotent: bool = True,
    ) -> dict:
        payload = {**(params or {}), "access_token": self._token}
        url = self._url(path)
        attempt = 0
        while True:
            attempt += 1
            try:
                if method == "POST":
                    resp = self._http.request(method, url, data=payload, timeout=self._timeout)
                else:
                    resp = self._http.request(method, url, params=payload, timeout=self._timeout)
            except (requests.ConnectionError, requests.Timeout) as exc:
                msg = self._redact(str(exc))
                if not idempotent:
                    raise AmbiguousResult(f"{method} {path}: {msg}") from exc
                if attempt > self._max_retries:
                    raise GraphError(f"Error de red en {method} {path}: {msg}") from exc
                self._sleep(self._backoff(attempt, rate_limited=False, retry_after=None))
                continue

            try:
                body = resp.json()
            except ValueError:
                body = {}
            if resp.ok and "error" not in body:
                return body

            err = self._to_error(resp)
            err.args = (self._redact(str(err)),)
            if not idempotent and (err.status or 0) >= 500:
                raise AmbiguousResult(f"{method} {path}: HTTP {err.status}") from err
            retryable = err.is_rate_limit if not idempotent else err.is_transient
            if retryable and attempt <= self._max_retries:
                delay = self._backoff(
                    attempt,
                    rate_limited=err.is_rate_limit,
                    retry_after=resp.headers.get("Retry-After"),
                )
                log.warning("%s %s falló (%s); reintento en %.0fs", method, path, err, delay)
                self._sleep(delay)
                continue
            raise err

    # ---------------------------------------------------------------------- operaciones
    def whoami(self) -> dict:
        return self._request("GET", self.ig_user_id, params={"fields": "username"})

    def publishing_limit(self) -> dict:
        return self._request(
            "GET",
            f"{self.ig_user_id}/content_publishing_limit",
            params={"fields": "quota_usage,config"},
        )

    def create_story_container(self, *, image_url: str | None = None, video_url: str | None = None) -> str:
        if bool(image_url) == bool(video_url):
            raise ValueError("Indica exactamente uno: image_url o video_url")
        params = {"media_type": "STORIES"}
        params["image_url" if image_url else "video_url"] = image_url or video_url
        return self._request("POST", f"{self.ig_user_id}/media", params=params)["id"]

    def container_status(self, container_id: str) -> dict:
        return self._request("GET", container_id, params={"fields": "status_code,status"})

    def wait_until_ready(
        self, container_id: str, *, interval: float = 3.0, timeout: float = 180.0
    ) -> None:
        deadline = self._clock() + timeout
        while True:
            info = self.container_status(container_id)
            code = info.get("status_code")
            if code == "FINISHED":
                return
            if code in ("ERROR", "EXPIRED"):
                raise ContainerError(f"Contenedor {container_id} en {code}: {info.get('status')}")
            if self._clock() >= deadline:
                raise ContainerError(f"Contenedor {container_id} no terminó a tiempo (último: {code})")
            self._sleep(interval)

    def publish(self, container_id: str) -> str:
        body = self._request(
            "POST",
            f"{self.ig_user_id}/media_publish",
            params={"creation_id": container_id},
            idempotent=False,
        )
        return body["id"]

    def media_info(self, media_id: str) -> dict:
        return self._request(
            "GET", media_id, params={"fields": "permalink,media_product_type,timestamp"}
        )

    def active_stories(self) -> list[dict]:
        """Historias activas (últimas 24 h). Se usa para reconciliar publicaciones ambiguas."""
        body = self._request(
            "GET", f"{self.ig_user_id}/stories", params={"fields": "id,timestamp,permalink"}
        )
        return body.get("data", [])


def refresh_long_lived_token(
    token: str, *, session: requests.Session | None = None, timeout: float = 30.0
) -> TokenInfo:
    """Renueva un token de larga duración de Instagram Login (válido ~60 días).

    Meta exige que el token tenga al menos 24 h de antigüedad y no haya expirado.
    """
    http = session or requests.Session()
    resp = http.get(
        "https://graph.instagram.com/refresh_access_token",
        params={"grant_type": "ig_refresh_token", "access_token": token},
        timeout=timeout,
    )
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if not resp.ok or "access_token" not in body:
        msg = body.get("error", {}).get("message", f"HTTP {resp.status_code}")
        raise GraphError(msg.replace(token, "***"), status=resp.status_code)
    return TokenInfo(body["access_token"], int(body.get("expires_in", 0)))
