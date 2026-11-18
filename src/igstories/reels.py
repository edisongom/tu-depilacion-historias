"""Reels programados: cada slot con ``format = "reel"`` publica el siguiente video de [reels].dir.

Reglas:

* Los videos se publican en orden alfabético (ponles número delante: 01-..., 02-...).
* Un reel **nunca se repite**: si ya está en el historial como publicado, se salta.
  Cuando se acaban, el slot queda ``skipped`` y llega un aviso para subir más.
* Descripción: si junto a ``video.mp4`` existe ``video.txt`` se usa ese texto; si no,
  ``[reels].caption``.
"""

from __future__ import annotations

from pathlib import Path

from igstories.config import ReelsConfig
from igstories.history import COUNTS_AS_SHOWN

PREFIX = "reel:"
VIDEO_SUFFIXES = (".mp4", ".mov")


def reel_id(path: Path) -> str:
    return f"{PREFIX}{path.name}"


def list_reels(cfg: ReelsConfig) -> list[Path]:
    if not cfg.dir.is_dir():
        return []
    return sorted(p for p in cfg.dir.iterdir() if p.suffix.lower() in VIDEO_SUFFIXES)


def used_reels(history) -> set[str]:
    return {
        e.story_id
        for e in history.entries()
        if e.story_id and e.story_id.startswith(PREFIX) and e.status in COUNTS_AS_SHOWN
    }


def pending_reels(cfg: ReelsConfig, history, extra_used: set[str] | None = None) -> list[Path]:
    used = used_reels(history) | (extra_used or set())
    return [p for p in list_reels(cfg) if reel_id(p) not in used]


def path_for(cfg: ReelsConfig, story_id: str) -> Path:
    return cfg.dir / story_id[len(PREFIX):]


def caption_for(cfg: ReelsConfig, video: Path) -> str:
    txt = video.with_suffix(".txt")
    if txt.exists():
        return txt.read_text(encoding="utf-8").strip()
    return cfg.caption


MUSIC_SUFFIXES = (".mp3", ".m4a", ".aac", ".wav")


def list_music(music_dir: Path) -> list[Path]:
    if not music_dir.is_dir():
        return []
    return sorted(p for p in music_dir.iterdir() if p.suffix.lower() in MUSIC_SUFFIXES)


def pick_music(video: Path, tracks: list[Path]) -> Path:
    """Canción estable por video (misma entrada, misma canción) repartida entre todas."""
    import hashlib

    h = int(hashlib.sha256(video.name.encode()).hexdigest(), 16)
    return tracks[h % len(tracks)]


def add_music(video: Path, track: Path, duration: float) -> None:
    """Mezcla ``track`` como audio del video (sin recodificar la imagen) y lo reemplaza."""
    import subprocess

    tmp = video.with_name(f".{video.stem}.music.mp4")
    fade_at = max(duration - 1.2, 0)
    cmd = [
        "ffmpeg", "-v", "error", "-y", "-i", str(video), "-stream_loop", "-1", "-i", str(track),
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-af", f"afade=t=in:d=0.4,afade=t=out:st={fade_at:.2f}:d=1.2,volume=0.9",
        "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2",
        "-t", f"{duration:.3f}", "-movflags", "+faststart", str(tmp),
    ]
    subprocess.run(cmd, check=True)
    tmp.replace(video)
