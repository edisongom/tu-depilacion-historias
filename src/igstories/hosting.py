"""URLs públicas para las imágenes.

La API de Meta no recibe el archivo: recibe una URL y la descarga ella misma. Cada proveedor
traduce un archivo local a una URL pública.

* ``static``: el directorio ``assets/ready`` ya se sirve en ``base_url`` (tu sitio, GitHub
  Pages, raw.githubusercontent.com en un repo público, un CDN…). No sube nada.
* ``s3``: sube el archivo a un bucket S3 / Cloudflare R2 antes de publicar.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import requests

from igstories.config import HostingConfig

log = logging.getLogger(__name__)
MAX_BYTES = 8 * 1024 * 1024


class HostingError(RuntimeError):
    pass


class UrlProvider(Protocol):
    def url_for(self, local_file: Path) -> str: ...


class StaticUrlProvider:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def url_for(self, local_file: Path) -> str:
        return f"{self.base_url}/{quote(local_file.name)}"


class S3UrlProvider:
    """Sube a S3/R2. Requiere ``pip install igstories[s3]`` y credenciales estándar de AWS."""

    def __init__(
        self,
        bucket: str,
        prefix: str,
        public_base_url: str,
        endpoint_url: str | None = None,
        client=None,
    ):
        if client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover
                raise HostingError("Instala el extra s3: pip install 'igstories[s3]'") from exc
            client = boto3.client("s3", endpoint_url=endpoint_url)
        self._client = client
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.public_base_url = public_base_url.rstrip("/")

    def url_for(self, local_file: Path) -> str:
        key = f"{self.prefix}/{local_file.name}" if self.prefix else local_file.name
        self._client.upload_file(
            str(local_file),
            self.bucket,
            key,
            ExtraArgs={"ContentType": "image/jpeg", "CacheControl": "public, max-age=3600"},
        )
        return f"{self.public_base_url}/{quote(key)}"


def make_provider(cfg: HostingConfig) -> UrlProvider:
    if cfg.provider == "static":
        return StaticUrlProvider(cfg.base_url)
    if cfg.provider == "s3":
        return S3UrlProvider(cfg.bucket, cfg.prefix, cfg.public_base_url, cfg.endpoint_url)
    raise HostingError(f"Proveedor de hosting desconocido: {cfg.provider}")


def preflight(url: str, *, session: requests.Session | None = None, timeout: float = 15.0) -> None:
    """Comprueba que la URL responde 200, es JPEG y no excede 8 MB (Meta la descargará luego)."""
    http = session or requests.Session()
    try:
        resp = http.head(url, timeout=timeout, allow_redirects=True)
        if resp.status_code in (403, 405, 501):  # algunos servidores no aceptan HEAD
            resp = http.get(url, timeout=timeout, stream=True, headers={"Range": "bytes=0-0"})
            resp.close()
    except requests.RequestException as exc:
        raise HostingError(f"No se pudo consultar {url}: {exc}") from exc

    if resp.status_code not in (200, 206):
        raise HostingError(f"{url} respondió HTTP {resp.status_code}")
    ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
    if ctype != "image/jpeg":
        raise HostingError(f"{url} sirve Content-Type {ctype or 'desconocido'}, se espera image/jpeg")
    length = resp.headers.get("Content-Length")
    if length and resp.status_code == 200 and int(length) > MAX_BYTES:
        raise HostingError(f"{url} pesa {int(length) / 1e6:.1f} MB (máximo 8 MB)")
    if resp.history:
        log.warning("%s redirige; Meta podría no seguir redirecciones. Usa la URL final.", url)
