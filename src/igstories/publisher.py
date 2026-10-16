"""Orquestación: elegir historia → verificar URL → contenedor → publicar → registrar.

Garantías:

* **Idempotencia**: cada (fecha, slot) tiene una entrada en el historial; si ya está
  ``published`` / ``skipped`` no se vuelve a tocar.
* **Puesta al día**: ``run_due`` publica los slots cuya hora ya pasó (dentro de su ventana de
  gracia), así que un cron que se atrasa o se salta una ejecución no pierde la historia del día.
* **Sin duplicados por resultados ambiguos**: antes de llamar a ``media_publish`` se deja
  constancia (``publishing``). Si el proceso muere o hay timeout, la siguiente ejecución
  reconcilia contra ``/stories`` en lugar de volver a publicar a ciegas.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
from dataclasses import dataclass
from pathlib import Path

from igstories.catalog import Catalog, Story
from igstories.config import Settings
from igstories.graph import AmbiguousResult, ContainerError, GraphClient, GraphError
from igstories.history import Entry, History, utcnow
from igstories.hosting import HostingError, UrlProvider, preflight
from igstories.notify import Notifier, NullNotifier
from igstories.schedule import (
    DueSlot,
    OverlayHistory,
    due_slots,
    pick_story,
    scheduled_time,
    slot_runs_on,
)

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Outcome:
    key: str
    story_id: str | None
    status: str  # published | dry-run | failed | unknown | skipped | already-done | waiting
    detail: str = ""


@dataclass(frozen=True)
class PlanRow:
    day: dt.date
    slot: str
    time: dt.time
    story_id: str | None
    reason: str
    status: str  # estado real si ya existe en el historial, o "planned"


def _parse_ts(value: str) -> dt.datetime:
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z"):
        try:
            return dt.datetime.strptime(value, fmt)
        except ValueError:
            continue
    return dt.datetime.fromisoformat(value)


def build_plan(
    settings: Settings, catalog: Catalog, history: History, start: dt.date, days: int
) -> list[PlanRow]:
    """Simula el calendario de los próximos ``days`` días sin red ni token."""
    overlay = OverlayHistory(history)
    rows: list[PlanRow] = []
    for offset in range(days):
        day = start + dt.timedelta(days=offset)
        for slot in sorted(settings.slots, key=lambda s: scheduled_time(s, day)):
            if not slot_runs_on(slot, day):
                continue
            existing = history.get(f"{day.isoformat()}:{slot.name}")
            if existing and existing.status in ("published", "unknown", "publishing"):
                rows.append(
                    PlanRow(day, slot.name, scheduled_time(slot, day), existing.story_id, "history", existing.status)
                )
                continue
            pick = pick_story(
                slot, day, catalog, overlay, settings.overrides, settings.default_cooldown_days,
                settings.shuffle,
            )
            if pick.story:
                overlay.record(pick.story.id, day)
            rows.append(
                PlanRow(
                    day, slot.name, scheduled_time(slot, day),
                    pick.story.id if pick.story else None, pick.reason, "planned",
                )
            )
    return rows


class Publisher:
    def __init__(
        self,
        settings: Settings,
        catalog: Catalog,
        history: History,
        client: GraphClient,
        urls: UrlProvider,
        *,
        notifier: Notifier | None = None,
        check_url: bool | None = None,
    ):
        self.settings = settings
        self.catalog = catalog
        self.history = history
        self.client = client
        self.urls = urls
        self.notifier = notifier or NullNotifier()
        self.check_url = settings.hosting.preflight if check_url is None else check_url

    # ------------------------------------------------------------------------------ plan
    def plan(self, start: dt.date, days: int) -> list[PlanRow]:
        return build_plan(self.settings, self.catalog, self.history, start, days)

    # ------------------------------------------------------------------------ ejecución
    def run_due(self, now: dt.datetime | None = None, *, dry_run: bool = False) -> list[Outcome]:
        now = now or dt.datetime.now(self.settings.timezone)
        outcomes = [self._handle_due(d, now, dry_run) for d in due_slots(self.settings, now)]
        if not dry_run:
            self.history.save()
        return outcomes

    def post_now(self, story_id: str, *, dry_run: bool = False) -> Outcome:
        """Publica una historia concreta ya mismo (prueba inicial o emergencia)."""
        story = self.catalog.get(story_id)
        stamp = dt.datetime.now(self.settings.timezone)
        entry = Entry(
            key=f"manual:{stamp:%Y%m%dT%H%M%S}",
            date=stamp.date().isoformat(),
            slot="manual",
            story_id=story.id,
        )
        outcome = self._publish(entry, story, max_attempts=1, dry_run=dry_run)
        if not dry_run:
            self.history.save()
        return outcome

    def _handle_due(self, due: DueSlot, now: dt.datetime, dry_run: bool) -> Outcome:
        slot, key = due.slot, due.key
        entry = self.history.get(key)

        reconciled = False
        if entry and entry.status == "publishing":
            entry = self._reconcile(entry)
            reconciled = True
        if entry:
            if reconciled and entry.status == "published":
                return Outcome(key, entry.story_id, "published", "confirmada tras reconciliar")
            if entry.status in ("published", "skipped"):
                return Outcome(key, entry.story_id, "already-done")
            if entry.status == "unknown":
                return Outcome(key, entry.story_id, "unknown", "requiere revisión manual")
            if entry.status in ("failed", "pending") and entry.attempts >= slot.max_attempts:
                return Outcome(key, entry.story_id, "failed", "intentos agotados")

        if entry and entry.story_id and entry.story_id in self.catalog:
            story = self.catalog.get(entry.story_id)  # reintento: misma historia
        else:
            pick = pick_story(
                slot, due.day, self.catalog, self.history, self.settings.overrides,
                self.settings.default_cooldown_days, self.settings.shuffle,
            )
            if pick.story is None:
                msg = f"{key}: sin historia elegible ({pick.reason})"
                log.warning(msg)
                if not dry_run:
                    self.history.put(
                        Entry(key, due.day.isoformat(), slot.name, None, "skipped", error=pick.reason)
                    )
                    if pick.reason != "skip":
                        self.notifier.notify(msg, level="warning")
                return Outcome(key, None, "skipped", pick.reason)
            story = pick.story
            log.info("%s -> %s (%s)", key, story.id, pick.reason)

        entry = entry or Entry(key, due.day.isoformat(), slot.name, story.id)
        return self._publish(entry, story, max_attempts=slot.max_attempts, dry_run=dry_run)

    def _publish(self, entry: Entry, story: Story, *, max_attempts: int, dry_run: bool) -> Outcome:
        cfg = self.settings.account
        local = Path(self.settings.ready_dir) / story.image
        entry.story_id = story.id
        entry.attempts += 1
        entry.status, entry.error = "pending", None
        try:
            if not local.exists():
                raise HostingError(f"No existe la imagen preparada: {local}")
            url = self.urls.url_for(local)
            if self.check_url:
                preflight(url)
            if dry_run:
                return Outcome(entry.key, story.id, "dry-run", url)

            entry.container_id = self.client.create_story_container(image_url=url)
            self.history.put(entry)
            self.history.save()
            self.client.wait_until_ready(
                entry.container_id, interval=cfg.poll_interval_s, timeout=cfg.poll_timeout_s
            )

            entry.status = "publishing"
            entry.publish_started_at = utcnow().isoformat(timespec="seconds")
            self.history.put(entry)
            self.history.save()
            entry.media_id = self.client.publish(entry.container_id)
        except AmbiguousResult as exc:
            return self._ambiguous(entry, exc)
        except (GraphError, ContainerError, HostingError, ValueError) as exc:
            return self._failed(entry, exc, max_attempts)

        entry.status = "published"
        with contextlib.suppress(GraphError):  # el permalink es solo informativo
            entry.permalink = self.client.media_info(entry.media_id).get("permalink")
        self.history.put(entry)
        self.history.save()
        log.info("Publicada %s (%s) media_id=%s", entry.key, story.id, entry.media_id)
        self.notifier.notify(f"Historia publicada: {story.id} ({entry.key})", level="info")
        return Outcome(entry.key, story.id, "published", entry.media_id or "")

    # ---------------------------------------------------------------------- fallos / estado
    def _failed(self, entry: Entry, exc: Exception, max_attempts: int) -> Outcome:
        entry.status, entry.error = "failed", str(exc)[:500]
        self.history.put(entry)
        self.history.save()
        log.error("Fallo %s (intento %d/%d): %s", entry.key, entry.attempts, max_attempts, exc)
        auth = isinstance(exc, GraphError) and exc.is_auth
        if auth or entry.attempts >= max_attempts:
            hint = " — el token es inválido o expiró; renuévalo" if auth else ""
            self.notifier.notify(
                f"No se pudo publicar {entry.story_id} ({entry.key}): {exc}{hint}", level="error"
            )
        return Outcome(entry.key, entry.story_id, "failed", str(exc))

    def _ambiguous(self, entry: Entry, exc: Exception) -> Outcome:
        entry.status, entry.error = "publishing", f"resultado ambiguo: {exc}"
        self.history.put(entry)
        self.history.save()
        entry = self._reconcile(entry)
        if entry.status == "published":
            return Outcome(entry.key, entry.story_id, "published", "confirmada tras reconciliar")
        if entry.status == "unknown":
            self.notifier.notify(
                f"Revisa Instagram: no se pudo confirmar {entry.story_id} ({entry.key}).",
                level="error",
            )
            return Outcome(entry.key, entry.story_id, "unknown", str(exc))
        return Outcome(entry.key, entry.story_id, "failed", "no se publicó; se reintentará")

    def _reconcile(self, entry: Entry) -> Entry:
        """Decide qué pasó con un intento en estado ``publishing`` mirando las historias activas."""
        started = (
            _parse_ts(entry.publish_started_at)
            if entry.publish_started_at
            else utcnow() - dt.timedelta(hours=1)
        )
        try:
            stories = self.client.active_stories()
        except GraphError as exc:
            log.warning("No se pudo reconciliar %s: %s", entry.key, exc)
            entry.status = "unknown"
            self.history.put(entry)
            self.history.save()
            return entry

        window = started - dt.timedelta(seconds=90)
        matches = [s for s in stories if s.get("timestamp") and _parse_ts(s["timestamp"]) >= window]
        if matches:
            entry.status, entry.error = "published", None
            entry.media_id = matches[0].get("id")
            entry.permalink = matches[0].get("permalink")
            log.info("Reconciliado %s: ya estaba publicada (%s)", entry.key, entry.media_id)
        else:
            entry.status = "failed"
            entry.error = "no apareció en /stories tras el intento; seguro reintentar"
        self.history.put(entry)
        self.history.save()
        return entry
