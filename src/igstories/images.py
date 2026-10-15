"""Preparación de imágenes: cualquier original → JPEG 1080x1920 listo para historias.

Meta exige JPEG para imágenes y descarga el archivo desde una URL pública. Este módulo
normaliza tamaño, orientación EXIF, espacio de color y peso, y es idempotente: solo vuelve
a generar lo que cambió (huella en ``assets/ready/.manifest.json``).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

from igstories.config import ImageSpec

log = logging.getLogger(__name__)

SOURCE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
MAX_BYTES = 8 * 1024 * 1024  # límite de Meta para imágenes de historias
RATIO = 9 / 16


@dataclass(frozen=True)
class PrepareResult:
    source: Path
    output: Path
    action: str  # created | updated | unchanged


def slugify(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "story"


def _hex(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)


def render(img: Image.Image, spec: ImageSpec) -> Image.Image:
    """Devuelve una imagen RGB de ``spec.width`` x ``spec.height``."""
    base = ImageOps.exif_transpose(img).convert("RGB")
    size = (spec.width, spec.height)

    already_vertical = abs(base.width / base.height - RATIO) < 0.01
    if spec.mode == "cover" or already_vertical:
        # Si ya es 9:16 se asume diseñada respetando las zonas seguras.
        return ImageOps.fit(base, size, Image.Resampling.LANCZOS)

    box = (spec.width, spec.height - spec.safe_top - spec.safe_bottom)
    fg = ImageOps.contain(base, box, Image.Resampling.LANCZOS)

    if spec.mode == "fit-blur":
        bg = ImageOps.fit(base, size, Image.Resampling.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(spec.blur_radius))
        tint = Image.new("RGB", size, _hex(spec.background))
        bg = Image.blend(bg, tint, 0.35)
    else:
        bg = Image.new("RGB", size, _hex(spec.background))

    x = (spec.width - fg.width) // 2
    y = spec.safe_top + (box[1] - fg.height) // 2
    bg.paste(fg, (x, y))
    return bg


def save_jpeg(img: Image.Image, dst: Path, quality: int) -> int:
    dst.parent.mkdir(parents=True, exist_ok=True)
    q = quality
    while True:
        img.save(dst, "JPEG", quality=q, optimize=True, subsampling=0)
        size = dst.stat().st_size
        if size <= MAX_BYTES or q <= 60:
            return size
        q -= 5


def _fingerprint(src: Path, spec: ImageSpec) -> str:
    st = src.stat()
    payload = json.dumps([asdict(spec), st.st_size, st.st_mtime_ns], sort_keys=True)
    return hashlib.sha1(payload.encode()).hexdigest()


def prepare_all(
    source_dir: Path, ready_dir: Path, spec: ImageSpec, *, force: bool = False
) -> list[PrepareResult]:
    ready_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = ready_dir / ".manifest.json"
    manifest: dict[str, str] = {}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    results: list[PrepareResult] = []
    sources = sorted(
        p for p in source_dir.rglob("*") if p.is_file() and p.suffix.lower() in SOURCE_EXTS
    )
    for src in sources:
        out = ready_dir / f"{slugify(src.stem)}.jpg"
        fp = _fingerprint(src, spec)
        existed = out.exists()
        if existed and not force and manifest.get(out.name) == fp:
            results.append(PrepareResult(src, out, "unchanged"))
            continue
        with Image.open(src) as im:
            save_jpeg(render(im, spec), out, spec.quality)
        manifest[out.name] = fp
        results.append(PrepareResult(src, out, "updated" if existed else "created"))
        log.info("%s -> %s", src.name, out.name)

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return results


def inspect_ready(path: Path) -> list[str]:
    """Problemas de un JPEG ya preparado (lista vacía = OK)."""
    problems: list[str] = []
    if not path.exists():
        return [f"no existe {path.name}"]
    if path.suffix.lower() not in (".jpg", ".jpeg"):
        problems.append("Meta solo acepta JPEG para imágenes de historias")
    if path.stat().st_size > MAX_BYTES:
        problems.append("pesa más de 8 MB")
    with Image.open(path) as im:
        if abs(im.width / im.height - RATIO) > 0.01:
            problems.append(f"proporción {im.width}x{im.height}, se recomienda 9:16")
        if im.format != "JPEG":
            problems.append(f"el formato real es {im.format}, no JPEG")
    return problems
