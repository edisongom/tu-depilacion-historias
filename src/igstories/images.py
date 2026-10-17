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
import shutil
import subprocess
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

from igstories.config import ImageSpec

log = logging.getLogger(__name__)

SOURCE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v"}
MAX_BYTES = 8 * 1024 * 1024  # límite de Meta para imágenes de historias
MAX_VIDEO_BYTES = 100 * 1024 * 1024
MAX_VIDEO_SECONDS = 60
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


def _file_hash(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fingerprint(src: Path, spec: ImageSpec) -> str:
    """Huella por contenido (no por fecha de modificación), estable entre máquinas."""
    video = src.suffix.lower() in VIDEO_EXTS
    payload = json.dumps(["video-v1" if video else asdict(spec), _file_hash(src)], sort_keys=True)
    return hashlib.sha1(payload.encode()).hexdigest()


def probe_video(path: Path) -> dict | None:
    """Datos del video vía ffprobe, o None si ffprobe no está disponible o falla."""
    if not shutil.which("ffprobe"):
        return None
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        return None
    data = json.loads(proc.stdout or "{}")
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if not v:
        return None
    rotate = 0
    for sd in v.get("side_data_list", []) or []:
        rotate = int(sd.get("rotation", rotate) or 0)
    rotate = int(v.get("tags", {}).get("rotate", rotate) or rotate)
    w, h = int(v["width"]), int(v["height"])
    if abs(rotate) in (90, 270):
        w, h = h, w
    duration = float(data.get("format", {}).get("duration") or v.get("duration") or 0)
    return {
        "vcodec": v.get("codec_name"), "pix_fmt": v.get("pix_fmt"), "width": w, "height": h,
        "acodec": a.get("codec_name") if a else None, "duration": duration,
        "size": path.stat().st_size, "format": data.get("format", {}).get("format_name", ""),
        "rotated": bool(rotate),
    }


def video_is_compliant(info: dict) -> bool:
    """¿Cumple lo que pide Meta para historias? (MP4, H.264, AAC, 9:16, ≤60 s, ≤100 MB)."""
    return (
        info["vcodec"] == "h264"
        and info["pix_fmt"] == "yuv420p"
        and abs(info["width"] / info["height"] - RATIO) < 0.01
        and info["width"] <= 1920
        and info["duration"] <= MAX_VIDEO_SECONDS
        and info["acodec"] in (None, "aac")
        and info["size"] <= MAX_VIDEO_BYTES
        and "mp4" in info["format"]
        and not info["rotated"]
    )


def prepare_video(src: Path, out: Path, spec: ImageSpec) -> str:
    """Copia el video si ya cumple; si no, lo convierte con ffmpeg. Devuelve la acción."""
    out.parent.mkdir(parents=True, exist_ok=True)
    info = probe_video(src)
    if info and video_is_compliant(info):
        shutil.copyfile(src, out)
        return "copied"
    if not shutil.which("ffmpeg"):
        return "skipped-no-ffmpeg"
    if info and info["duration"] > MAX_VIDEO_SECONDS:
        log.warning("%s dura %.0f s; se recorta a %d s", src.name, info["duration"], MAX_VIDEO_SECONDS)
    bg = spec.background.lstrip("#")
    vf = (
        f"scale={spec.width}:{spec.height}:force_original_aspect_ratio=decrease,"
        f"pad={spec.width}:{spec.height}:(ow-iw)/2:(oh-ih)/2:color=0x{bg},setsar=1,fps=30"
    )
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-t", str(MAX_VIDEO_SECONDS),
        "-map", "0:v:0", "-map", "0:a:0?", "-vf", vf,
        "-c:v", "libx264", "-preset", "medium", "-crf", "23", "-pix_fmt", "yuv420p",
        "-profile:v", "high", "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-movflags", "+faststart", str(out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        out.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg falló con {src.name}: {proc.stderr.strip()[-300:]}")
    return "transcoded"


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
        p
        for p in source_dir.rglob("*")
        if p.is_file() and p.suffix.lower() in SOURCE_EXTS | VIDEO_EXTS
    )
    for src in sources:
        is_video = src.suffix.lower() in VIDEO_EXTS
        out = ready_dir / f"{slugify(src.stem)}{'.mp4' if is_video else '.jpg'}"
        fp = _fingerprint(src, spec)
        existed = out.exists()
        if existed and not force and manifest.get(out.name) == fp:
            results.append(PrepareResult(src, out, "unchanged"))
            continue
        if is_video:
            try:
                action = prepare_video(src, out, spec)
            except RuntimeError as exc:  # un video malo no debe frenar al resto
                log.error("%s", exc)
                results.append(PrepareResult(src, out, "error"))
                continue
            if action == "skipped-no-ffmpeg":
                log.warning("%s necesita conversión pero no hay ffmpeg instalado; se omite", src.name)
                results.append(PrepareResult(src, out, action))
                continue
        else:
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
    if path.suffix.lower() == ".mp4":
        if path.stat().st_size > MAX_VIDEO_BYTES:
            problems.append("el video pesa más de 100 MB")
        info = probe_video(path)
        if info and not video_is_compliant(info):
            problems.append("proporción o códec fuera de lo recomendado (usa `igstories prepare`)")
        return problems
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
