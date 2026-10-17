"""Catálogo de historias (content/stories.toml)."""

from __future__ import annotations

import datetime as dt
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from igstories.config import ConfigError

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
VIDEO_SUFFIXES = (".mp4", ".mov")


@dataclass(frozen=True)
class Story:
    id: str
    image: str  # nombre del JPEG dentro de assets/ready
    tags: tuple[str, ...] = ()
    priority: int = 0  # desempata a favor de la mayor prioridad
    enabled: bool = True
    active_from: dt.date | None = None
    active_to: dt.date | None = None
    cooldown_days: int | None = None  # None = usa default_cooldown_days
    note: str = ""

    @property
    def is_video(self) -> bool:
        return self.image.lower().endswith(VIDEO_SUFFIXES)

    def is_active_on(self, day: dt.date) -> bool:
        if not self.enabled:
            return False
        if self.active_from and day < self.active_from:
            return False
        return not (self.active_to and day > self.active_to)


class Catalog:
    def __init__(self, stories: list[Story]):
        self._by_id = {s.id: s for s in stories}

    def __contains__(self, story_id: str) -> bool:
        return story_id in self._by_id

    def __iter__(self):
        return iter(self._by_id.values())

    def __len__(self) -> int:
        return len(self._by_id)

    def get(self, story_id: str) -> Story:
        try:
            return self._by_id[story_id]
        except KeyError as exc:
            raise KeyError(f"Historia desconocida: {story_id!r}") from exc

    def tags(self) -> set[str]:
        return {t for s in self for t in s.tags}


def _opt_date(value, where: str, errors: list[str]) -> dt.date | None:
    if value is None:
        return None
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        errors.append(f"{where}: fecha inválida {value!r}")
        return None


def _discover(stories: list[Story], ready_dir: Path, auto_tag: str) -> list[Story]:
    """Agrega como historias las imágenes de ``ready_dir`` que no están en stories.toml."""
    used_images = {s.image for s in stories}
    used_ids = {s.id for s in stories}
    found: list[Story] = []
    files = sorted(p for p in Path(ready_dir).iterdir() if p.suffix.lower() in (".jpg", ".mp4"))
    for img in files:
        if img.name in used_images:
            continue
        sid = re.sub(r"[^a-z0-9_-]+", "-", img.stem.lower()).strip("-_") or "imagen"
        base, n = sid, 2
        while sid in used_ids:
            sid, n = f"{base}-{n}", n + 1
        used_ids.add(sid)
        found.append(Story(id=sid, image=img.name, tags=(auto_tag,), note="auto"))
    return found


def load_catalog(
    path: str | Path, *, ready_dir: str | Path | None = None, auto_tag: str = "libre"
) -> Catalog:
    path = Path(path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"No existe el catálogo: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"TOML inválido en {path}: {exc}") from exc

    errors: list[str] = []
    stories: list[Story] = []
    seen: set[str] = set()
    for n, s in enumerate(raw.get("story", [])):
        where = f"story[{n}]"
        sid = str(s.get("id", ""))
        if not _ID_RE.match(sid):
            errors.append(f"{where}: id inválido {sid!r} (minúsculas, números, - y _)")
        if sid in seen:
            errors.append(f"{where}: id duplicado {sid!r}")
        seen.add(sid)
        if not s.get("image"):
            errors.append(f"{where} ({sid}): falta 'image'")
        stories.append(
            Story(
                id=sid,
                image=str(s.get("image", "")),
                tags=tuple(s.get("tags", ())),
                priority=int(s.get("priority", 0)),
                enabled=bool(s.get("enabled", True)),
                active_from=_opt_date(s.get("active_from"), f"{where}.active_from", errors),
                active_to=_opt_date(s.get("active_to"), f"{where}.active_to", errors),
                cooldown_days=(int(s["cooldown_days"]) if "cooldown_days" in s else None),
                note=str(s.get("note", "")),
            )
        )
    if errors:
        raise ConfigError("Catálogo inválido:\n  - " + "\n  - ".join(errors))
    if ready_dir is not None:
        stories += _discover(stories, Path(ready_dir), auto_tag)
    return Catalog(stories)
