"""Historial de publicaciones (state/history.json).

Es la fuente de verdad para la idempotencia: cada (fecha, slot) se publica una sola vez.
Se escribe de forma atómica y con orden estable para que los diffs en git sean legibles.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

# pending     intento iniciado, aún no se llamó a media_publish
# publishing  se llamó a media_publish y no sabemos el resultado (se reconcilia)
# published   confirmado
# failed      falló antes de publicar; se puede reintentar hasta max_attempts
# unknown     resultado ambiguo e imposible de reconciliar: revisar a mano
# skipped     no había historia elegible o hubo override skip
STATUSES = ("pending", "publishing", "published", "failed", "unknown", "skipped")
COUNTS_AS_SHOWN = ("published", "unknown", "publishing")


@dataclass
class Entry:
    key: str
    date: str
    slot: str
    story_id: str | None
    status: str = "pending"
    attempts: int = 0
    container_id: str | None = None
    media_id: str | None = None
    permalink: str | None = None
    publish_started_at: str | None = None
    updated_at: str = ""
    error: str | None = None


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class History:
    def __init__(self, path: Path, entries: dict[str, Entry] | None = None):
        self.path = Path(path)
        self._entries: dict[str, Entry] = entries or {}

    @classmethod
    def load(cls, path: str | Path) -> History:
        path = Path(path)
        if not path.exists():
            return cls(path)
        data = json.loads(path.read_text(encoding="utf-8") or "{}")
        entries = {e["key"]: Entry(**e) for e in data.get("entries", [])}
        return cls(path, entries)

    def get(self, key: str) -> Entry | None:
        return self._entries.get(key)

    def put(self, entry: Entry) -> None:
        entry.updated_at = utcnow().isoformat(timespec="seconds")
        self._entries[entry.key] = entry

    def entries(self) -> list[Entry]:
        return sorted(self._entries.values(), key=lambda e: (e.date, e.slot, e.key))

    def last_published(self, story_id: str) -> dt.date | None:
        dates = [
            dt.date.fromisoformat(e.date)
            for e in self._entries.values()
            if e.story_id == story_id and e.status in COUNTS_AS_SHOWN
        ]
        return max(dates, default=None)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": 1, "entries": [asdict(e) for e in self.entries()]}
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".history-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
