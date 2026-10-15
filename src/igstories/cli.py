"""Línea de comandos: ``igstories <comando>``.

Códigos de salida: 0 ok · 1 error de ejecución o historias fallidas · 2 configuración inválida.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import subprocess
import sys

from igstories import images, notify
from igstories.catalog import Catalog, load_catalog
from igstories.config import ConfigError, Settings, get_access_token, load_settings
from igstories.graph import GraphClient, GraphError, refresh_long_lived_token
from igstories.history import History
from igstories.hosting import HostingError, make_provider, preflight
from igstories.publisher import Outcome, Publisher, build_plan
from igstories.schedule import tags_for

log = logging.getLogger("igstories")


# ------------------------------------------------------------------------------ helpers
def _setup_logging(level: str, as_json: bool) -> None:
    if as_json:

        class JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                return json.dumps(
                    {
                        "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                        "level": record.levelname,
                        "msg": record.getMessage(),
                    },
                    ensure_ascii=False,
                )

        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logging.basicConfig(level=level, handlers=[handler])
    else:
        logging.basicConfig(level=level, format="%(asctime)s %(levelname)-7s %(message)s")


def _client(settings: Settings) -> GraphClient:
    a = settings.account
    return GraphClient(
        base_url=a.graph_base_url,
        api_version=a.api_version,
        access_token=get_access_token(),
        ig_user_id=a.ig_user_id,
        timeout=a.timeout_s,
        max_retries=a.max_retries,
    )


def _publisher(settings: Settings, catalog: Catalog, *, preflight_override: bool | None) -> Publisher:
    return Publisher(
        settings,
        catalog,
        History.load(settings.history_file),
        _client(settings),
        make_provider(settings.hosting),
        notifier=notify.from_env(),
        check_url=preflight_override,
    )


def _print_outcomes(outcomes: list[Outcome]) -> None:
    if not outcomes:
        print("Nada pendiente en este momento.")
        return
    for o in outcomes:
        print(f"{o.status:<12} {o.key:<28} {o.story_id or '-':<22} {o.detail}")


# ---------------------------------------------------------------------------- comandos
def cmd_plan(args, settings: Settings, catalog: Catalog) -> int:
    start = dt.date.fromisoformat(args.start) if args.start else dt.datetime.now(settings.timezone).date()
    rows = build_plan(settings, catalog, History.load(settings.history_file), start, args.days)
    print(f"{'fecha':<12}{'día':<5}{'hora':<7}{'slot':<10}{'historia':<24}{'motivo':<18}estado")
    for r in rows:
        print(
            f"{r.day.isoformat():<12}{r.day.strftime('%a'):<5}{r.time.strftime('%H:%M'):<7}"
            f"{r.slot:<10}{r.story_id or '-':<24}{r.reason:<18}{r.status}"
        )
    return 0


def cmd_prepare(args, settings: Settings, catalog: Catalog) -> int:
    results = images.prepare_all(
        settings.source_dir, settings.ready_dir, settings.image, force=args.force
    )
    for r in results:
        print(f"{r.action:<10}{r.source.name} -> {r.output.name}")
    print(f"{len(results)} imagen(es) procesada(s).")
    return 0


def cmd_verify(args, settings: Settings, catalog: Catalog) -> int:
    errors: list[str] = []
    warnings: list[str] = []

    for story in catalog:
        for problem in images.inspect_ready(settings.ready_dir / story.image):
            target = warnings if problem.startswith("proporción") else errors
            target.append(f"{story.id}: {problem}")

    known_tags = catalog.tags()
    for slot in settings.slots:
        wanted = set(slot.tags).union(*slot.tags_by_weekday.values())
        for tag in sorted(wanted - known_tags):
            errors.append(f"slot {slot.name}: ninguna historia tiene la etiqueta {tag!r}")
    for o in settings.overrides:
        if o.story and o.story not in catalog:
            errors.append(f"override {o.date}: la historia {o.story!r} no existe")

    # cada día de cada slot debería tener candidatas
    today = dt.datetime.now(settings.timezone).date()
    for slot in settings.slots:
        for offset in range(7):
            day = today + dt.timedelta(days=offset)
            wanted = set(tags_for(slot, day))
            if slot.enabled and wanted and not any(wanted & set(s.tags) for s in catalog):
                warnings.append(f"slot {slot.name} el {day:%a}: sin historias para {sorted(wanted)}")

    if args.online:
        provider = make_provider(settings.hosting)
        if settings.hosting.provider == "static":
            for story in catalog:
                url = provider.url_for(settings.ready_dir / story.image)
                try:
                    preflight(url)
                    print(f"ok  {url}")
                except HostingError as exc:
                    errors.append(f"{story.id}: {exc}")
        else:
            warnings.append("--online con s3 no sube archivos; se omite")

    for w in warnings:
        print(f"AVISO  {w}")
    for e in errors:
        print(f"ERROR  {e}")
    print(f"{len(catalog)} historia(s), {len(errors)} error(es), {len(warnings)} aviso(s).")
    return 1 if errors else 0


def cmd_publish(args, settings: Settings, catalog: Catalog) -> int:
    pub = _publisher(settings, catalog, preflight_override=False if args.no_preflight else None)
    now = dt.datetime.fromisoformat(args.now).astimezone(settings.timezone) if args.now else None
    outcomes = pub.run_due(now, dry_run=args.dry_run)
    _print_outcomes(outcomes)
    bad = [o for o in outcomes if o.status in ("failed", "unknown")]
    return 1 if bad else 0


def cmd_post(args, settings: Settings, catalog: Catalog) -> int:
    pub = _publisher(settings, catalog, preflight_override=False if args.no_preflight else None)
    outcome = pub.post_now(args.story, dry_run=args.dry_run)
    _print_outcomes([outcome])
    return 0 if outcome.status in ("published", "dry-run") else 1


def cmd_status(args, settings: Settings, catalog: Catalog) -> int:
    client = _client(settings)
    try:
        print("Cuenta:", client.whoami().get("username", "?"))
        print("Cuota de publicación:", json.dumps(client.publishing_limit().get("data", []), ensure_ascii=False))
    except GraphError as exc:
        print(f"ERROR de la API: {exc}", file=sys.stderr)
        return 1
    hist = History.load(settings.history_file).entries()
    print(f"Historial: {len(hist)} entradas; últimas:")
    for e in hist[-args.last:]:
        print(f"  {e.date} {e.slot:<8} {e.status:<10} {e.story_id or '-':<22} {e.error or ''}")
    return 0


def cmd_history(args, settings: Settings, catalog: Catalog) -> int:
    for e in History.load(settings.history_file).entries()[-args.last:]:
        print(f"{e.date} {e.slot:<8} {e.status:<10} intentos={e.attempts} {e.story_id or '-':<22} {e.permalink or ''}")
    return 0


def cmd_token_refresh(args, settings: Settings, catalog: Catalog) -> int:
    if settings.account.login != "instagram":
        print("La renovación automática aplica solo a Instagram Login.", file=sys.stderr)
        return 1
    info = refresh_long_lived_token(get_access_token())
    days = info.expires_in / 86400
    print(f"Token renovado; vence en {days:.0f} días.")
    if args.gh_secret:
        cmd = ["gh", "secret", "set", args.gh_secret]
        if args.gh_repo:
            cmd += ["--repo", args.gh_repo]
        subprocess.run(cmd, input=info.access_token.encode(), check=True)  # por stdin: no queda en argv
        print(f"Secreto {args.gh_secret} actualizado vía gh.")
    elif args.print_token:
        print(info.access_token)
    else:
        print("Usa --gh-secret NOMBRE (recomendado) o --print-token para obtener el nuevo valor.")
    return 0


# -------------------------------------------------------------------------------- main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="igstories", description="Publicador de historias de Instagram")
    p.add_argument("-c", "--config", default="config.toml", help="ruta a config.toml")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    p.add_argument("--json-logs", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("plan", help="muestra el calendario simulado")
    s.add_argument("--days", type=int, default=14)
    s.add_argument("--start", help="YYYY-MM-DD (por defecto hoy)")
    s.set_defaults(func=cmd_plan)

    s = sub.add_parser("prepare", help="convierte assets/source a JPEG 1080x1920 en assets/ready")
    s.add_argument("--force", action="store_true")
    s.set_defaults(func=cmd_prepare)

    s = sub.add_parser("verify", help="valida configuración, catálogo e imágenes")
    s.add_argument("--online", action="store_true", help="comprueba que cada URL pública responde")
    s.set_defaults(func=cmd_verify)

    s = sub.add_parser("publish", help="publica los slots vencidos (para cron)")
    s.add_argument("--due", action="store_true", help="(por claridad) publica lo vencido")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--no-preflight", action="store_true")
    s.add_argument("--now", help="ISO 8601; solo para pruebas")
    s.set_defaults(func=cmd_publish)

    s = sub.add_parser("post", help="publica una historia concreta ahora")
    s.add_argument("story", help="id de la historia en el catálogo")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--no-preflight", action="store_true")
    s.set_defaults(func=cmd_post)

    s = sub.add_parser("status", help="cuenta, cuota de la API e historial reciente")
    s.add_argument("--last", type=int, default=7)
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("history", help="historial local")
    s.add_argument("--last", type=int, default=20)
    s.set_defaults(func=cmd_history)

    s = sub.add_parser("token-refresh", help="renueva el token de larga duración")
    s.add_argument("--gh-secret", help="nombre del secreto de GitHub a actualizar (requiere gh)")
    s.add_argument("--gh-repo", help="OWNER/REPO del secreto")
    s.add_argument("--print-token", action="store_true")
    s.set_defaults(func=cmd_token_refresh)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _setup_logging(args.log_level, args.json_logs)
    try:
        settings = load_settings(args.config)
        catalog = load_catalog(settings.stories_file)
        return args.func(args, settings, catalog)
    except ConfigError as exc:
        print(f"ERROR de configuración: {exc}", file=sys.stderr)
        return 2
    except GraphError as exc:
        print(f"ERROR de la API: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:  # pragma: no cover
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
