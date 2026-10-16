"""Calendario: qué slots están vencidos y qué historia toca en cada uno.

Estrategia de selección ("menos reciente primero"):

1. Se filtran las historias activas ese día y que tengan alguna de las etiquetas del slot
   (``tags_by_weekday`` manda sobre ``tags``).
2. Se descartan las que se mostraron hace menos de ``cooldown_days``.
3. Entre las restantes gana la que nunca se mostró (las imágenes nuevas salen primero); luego la
   más antigua; luego mayor ``priority``; luego un desempate estable (alfabético, o "aleatorio"
   derivado de un hash del día si ``shuffle``). Mismo historial, misma elección.
4. Si el cooldown deja el conjunto vacío, se relaja (se elige la menos reciente igualmente).

Para añadir otra estrategia basta con cambiar la función ``_sort_key`` o ``pick_story``.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from typing import Protocol

from igstories.catalog import Catalog, Story
from igstories.config import WEEKDAYS, Override, Settings, Slot


class HistoryLike(Protocol):
    def last_published(self, story_id: str) -> dt.date | None: ...


class OverlayHistory:
    """Historial real + elecciones simuladas (para ``plan``)."""

    def __init__(self, base: HistoryLike):
        self._base = base
        self._virtual: dict[str, dt.date] = {}

    def last_published(self, story_id: str) -> dt.date | None:
        dates = [d for d in (self._base.last_published(story_id), self._virtual.get(story_id)) if d]
        return max(dates, default=None)

    def record(self, story_id: str, day: dt.date) -> None:
        self._virtual[story_id] = day


@dataclass(frozen=True)
class Pick:
    story: Story | None
    reason: str  # override | least-recent | relaxed-cooldown | skip | no-candidates | bad-override


@dataclass(frozen=True)
class DueSlot:
    slot: Slot
    day: dt.date
    scheduled: dt.datetime  # con zona horaria

    @property
    def key(self) -> str:
        return f"{self.day.isoformat()}:{self.slot.name}"


def weekday_code(day: dt.date) -> str:
    return WEEKDAYS[day.weekday()]


def slot_runs_on(slot: Slot, day: dt.date) -> bool:
    return slot.enabled and weekday_code(day) in slot.days


def tags_for(slot: Slot, day: dt.date) -> tuple[str, ...]:
    return slot.tags_by_weekday.get(weekday_code(day), slot.tags)


def find_override(overrides: tuple[Override, ...], day: dt.date, slot_name: str) -> Override | None:
    matches = [o for o in overrides if o.date == day and o.slot in (None, slot_name)]
    matches.sort(key=lambda o: o.slot is None)  # el específico del slot gana al genérico
    return matches[0] if matches else None


def _digest(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest(), 16)


def scheduled_time(slot: Slot, day: dt.date) -> dt.time:
    """Hora del slot ese día. Con ``window`` es un minuto pseudoaleatorio pero estable.

    Se deriva de un hash de (día, slot), así todas las ejecuciones del cron coinciden
    en la hora elegida sin necesidad de guardar estado.
    """
    if slot.window_end is None:
        return slot.time
    start = slot.time.hour * 60 + slot.time.minute
    end = slot.window_end.hour * 60 + slot.window_end.minute
    minute = start + _digest(f"time:{day.isoformat()}:{slot.name}") % (end - start + 1)
    return dt.time(minute // 60, minute % 60)


def _sort_key(story: Story, last: dt.date | None, day: dt.date, shuffle: bool):
    tiebreak = f"{_digest(f'{story.id}:{day.isoformat()}'):x}" if shuffle else story.id
    return (last is not None, last or dt.date.min, -story.priority, tiebreak)


def pick_story(
    slot: Slot,
    day: dt.date,
    catalog: Catalog,
    history: HistoryLike,
    overrides: tuple[Override, ...] = (),
    default_cooldown: int = 6,
    shuffle: bool = False,
) -> Pick:
    override = find_override(overrides, day, slot.name)
    if override:
        if override.skip:
            return Pick(None, "skip")
        if override.story in catalog:
            return Pick(catalog.get(override.story), "override")
        return Pick(None, "bad-override")

    wanted = set(tags_for(slot, day))
    pool = [
        s
        for s in catalog
        if s.is_active_on(day) and (not wanted or wanted.intersection(s.tags))
    ]
    if not pool:
        return Pick(None, "no-candidates")

    scored = [(s, history.last_published(s.id)) for s in pool]
    fresh = [
        (s, last)
        for s, last in scored
        if last is None
        or (day - last).days >= (s.cooldown_days if s.cooldown_days is not None else default_cooldown)
    ]
    reason = "least-recent"
    if not fresh:
        fresh, reason = scored, "relaxed-cooldown"
    story, _ = min(fresh, key=lambda sl: _sort_key(sl[0], sl[1], day, shuffle))
    return Pick(story, reason)


def due_slots(settings: Settings, now: dt.datetime) -> list[DueSlot]:
    """Slots cuya hora ya pasó y siguen dentro de su ventana de gracia."""
    now = now.astimezone(settings.timezone)
    due: list[DueSlot] = []
    for day in (now.date() - dt.timedelta(days=1), now.date()):
        for slot in settings.slots:
            if not slot_runs_on(slot, day):
                continue
            scheduled = dt.datetime.combine(day, scheduled_time(slot, day), tzinfo=settings.timezone)
            if scheduled <= now < scheduled + dt.timedelta(minutes=slot.grace_minutes):
                due.append(DueSlot(slot, day, scheduled))
    due.sort(key=lambda d: d.scheduled)
    return due
