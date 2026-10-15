"""Carga y validación de la configuración (TOML).

Los secretos nunca viven en el archivo: el token se lee de la variable de entorno
``IG_ACCESS_TOKEN`` (ver :func:`get_access_token`).
"""

from __future__ import annotations

import datetime as dt
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

WEEKDAYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})$")


class ConfigError(ValueError):
    """Configuración inválida. El mensaje lista todos los problemas encontrados."""


@dataclass(frozen=True)
class AccountConfig:
    ig_user_id: str
    login: str = "instagram"  # "instagram" (Business Login) | "facebook" (Facebook Login)
    api_version: str = "v23.0"  # revisa el changelog de Meta y súbela cuando corresponda
    base_url: str | None = None  # solo para pruebas (servidor falso)
    timeout_s: float = 30.0
    poll_interval_s: float = 3.0
    poll_timeout_s: float = 180.0
    max_retries: int = 4

    @property
    def graph_base_url(self) -> str:
        if self.base_url:
            return self.base_url.rstrip("/")
        if self.login == "instagram":
            return "https://graph.instagram.com"
        return "https://graph.facebook.com"


@dataclass(frozen=True)
class HostingConfig:
    provider: str = "static"  # "static" | "s3"
    base_url: str = ""  # static: URL pública donde se sirve assets/ready
    preflight: bool = True  # verificar con HEAD que Meta podrá descargar la imagen
    # s3 / R2
    bucket: str = ""
    prefix: str = "stories"
    endpoint_url: str | None = None
    public_base_url: str = ""


@dataclass(frozen=True)
class ImageSpec:
    width: int = 1080
    height: int = 1920
    mode: str = "fit-blur"  # fit-blur | fit-solid | cover
    safe_top: int = 250  # zonas que tapa la interfaz de Instagram
    safe_bottom: int = 340
    background: str = "#fff6f9"
    blur_radius: int = 40
    quality: int = 90


@dataclass(frozen=True)
class Slot:
    name: str
    time: dt.time
    days: tuple[str, ...] = WEEKDAYS
    tags: tuple[str, ...] = ()
    tags_by_weekday: dict[str, tuple[str, ...]] = field(default_factory=dict)
    grace_minutes: int = 360  # ventana para "ponerse al día" si un ciclo de cron falla
    max_attempts: int = 3
    enabled: bool = True


@dataclass(frozen=True)
class Override:
    date: dt.date
    slot: str | None = None  # None = todos los slots de ese día
    story: str | None = None
    skip: bool = False


@dataclass(frozen=True)
class Settings:
    root: Path
    timezone: ZoneInfo
    account: AccountConfig
    hosting: HostingConfig
    image: ImageSpec
    slots: tuple[Slot, ...]
    overrides: tuple[Override, ...]
    stories_file: Path
    source_dir: Path
    ready_dir: Path
    history_file: Path
    default_cooldown_days: int = 6


def get_access_token(env: dict[str, str] | None = None) -> str:
    token = (env if env is not None else os.environ).get("IG_ACCESS_TOKEN", "").strip()
    if not token:
        raise ConfigError("Falta la variable de entorno IG_ACCESS_TOKEN")
    return token


def _time(value: Any, where: str, errors: list[str]) -> dt.time:
    if isinstance(value, dt.time):
        return value.replace(second=0, microsecond=0)
    if isinstance(value, str):
        m = _TIME_RE.match(value.strip())
        if m and int(m[1]) < 24 and int(m[2]) < 60:
            return dt.time(int(m[1]), int(m[2]))
    errors.append(f"{where}: hora inválida {value!r} (usa 'HH:MM')")
    return dt.time(0, 0)


def _date(value: Any, where: str, errors: list[str]) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value)
        except ValueError:
            pass
    errors.append(f"{where}: fecha inválida {value!r} (usa YYYY-MM-DD)")
    return dt.date.min


def _days(value: Any, where: str, errors: list[str]) -> tuple[str, ...]:
    days = tuple(str(d).lower() for d in value)
    bad = [d for d in days if d not in WEEKDAYS]
    if bad:
        errors.append(f"{where}: días inválidos {bad} (usa {', '.join(WEEKDAYS)})")
    return days


def load_settings(path: str | Path) -> Settings:
    path = Path(path).resolve()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"No existe el archivo de configuración: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"TOML inválido en {path}: {exc}") from exc

    errors: list[str] = []
    root = path.parent

    tz_name = raw.get("timezone", "UTC")
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        errors.append(f"timezone: zona horaria desconocida {tz_name!r}")
        tz = ZoneInfo("UTC")

    acc = raw.get("account", {})
    if not acc.get("ig_user_id"):
        errors.append("account.ig_user_id es obligatorio")
    if acc.get("login", "instagram") not in ("instagram", "facebook"):
        errors.append("account.login debe ser 'instagram' o 'facebook'")
    account = AccountConfig(
        ig_user_id=str(acc.get("ig_user_id", "")),
        login=acc.get("login", "instagram"),
        api_version=acc.get("api_version", "v23.0"),
        base_url=acc.get("base_url"),
        timeout_s=float(acc.get("timeout_s", 30.0)),
        poll_interval_s=float(acc.get("poll_interval_s", 3.0)),
        poll_timeout_s=float(acc.get("poll_timeout_s", 180.0)),
        max_retries=int(acc.get("max_retries", 4)),
    )

    h = raw.get("hosting", {})
    hosting = HostingConfig(
        provider=h.get("provider", "static"),
        base_url=str(h.get("base_url", "")).rstrip("/"),
        preflight=bool(h.get("preflight", True)),
        bucket=h.get("bucket", ""),
        prefix=str(h.get("prefix", "stories")).strip("/"),
        endpoint_url=h.get("endpoint_url"),
        public_base_url=str(h.get("public_base_url", "")).rstrip("/"),
    )
    if hosting.provider not in ("static", "s3"):
        errors.append("hosting.provider debe ser 'static' o 's3'")
    if hosting.provider == "static" and not hosting.base_url:
        errors.append("hosting.base_url es obligatorio con provider='static'")
    if hosting.provider == "s3" and not (hosting.bucket and hosting.public_base_url):
        errors.append("hosting.bucket y hosting.public_base_url son obligatorios con provider='s3'")

    i = raw.get("image", {})
    image = ImageSpec(
        width=int(i.get("width", 1080)),
        height=int(i.get("height", 1920)),
        mode=i.get("mode", "fit-blur"),
        safe_top=int(i.get("safe_top", 250)),
        safe_bottom=int(i.get("safe_bottom", 340)),
        background=i.get("background", "#fff6f9"),
        blur_radius=int(i.get("blur_radius", 40)),
        quality=int(i.get("quality", 90)),
    )
    if image.mode not in ("fit-blur", "fit-solid", "cover"):
        errors.append("image.mode debe ser fit-blur, fit-solid o cover")

    slots: list[Slot] = []
    names: set[str] = set()
    for n, s in enumerate(raw.get("slots", [])):
        where = f"slots[{n}]"
        name = s.get("name")
        if not name:
            errors.append(f"{where}: falta 'name'")
            continue
        if name in names:
            errors.append(f"{where}: nombre duplicado {name!r}")
        names.add(name)
        by_wd = {
            k.lower(): tuple(v) for k, v in (s.get("tags_by_weekday") or {}).items()
        }
        bad = [k for k in by_wd if k not in WEEKDAYS]
        if bad:
            errors.append(f"{where}.tags_by_weekday: días inválidos {bad}")
        slots.append(
            Slot(
                name=name,
                time=_time(s.get("time"), f"{where}.time", errors),
                days=_days(s.get("days", WEEKDAYS), f"{where}.days", errors),
                tags=tuple(s.get("tags", ())),
                tags_by_weekday=by_wd,
                grace_minutes=int(s.get("grace_minutes", 360)),
                max_attempts=int(s.get("max_attempts", 3)),
                enabled=bool(s.get("enabled", True)),
            )
        )
    if not slots:
        errors.append("Define al menos un [[slots]]")

    overrides: list[Override] = []
    for n, o in enumerate(raw.get("overrides", [])):
        where = f"overrides[{n}]"
        if not o.get("story") and not o.get("skip"):
            errors.append(f"{where}: usa 'story' o 'skip = true'")
        if o.get("slot") and o["slot"] not in names:
            errors.append(f"{where}: el slot {o['slot']!r} no existe")
        overrides.append(
            Override(
                date=_date(o.get("date"), f"{where}.date", errors),
                slot=o.get("slot"),
                story=o.get("story"),
                skip=bool(o.get("skip", False)),
            )
        )

    paths = raw.get("paths", {})
    if errors:
        raise ConfigError("Configuración inválida:\n  - " + "\n  - ".join(errors))

    return Settings(
        root=root,
        timezone=tz,
        account=account,
        hosting=hosting,
        image=image,
        slots=tuple(slots),
        overrides=tuple(overrides),
        stories_file=root / paths.get("stories", "content/stories.toml"),
        source_dir=root / paths.get("source", "assets/source"),
        ready_dir=root / paths.get("ready", "assets/ready"),
        history_file=root / paths.get("history", "state/history.json"),
        default_cooldown_days=int(raw.get("default_cooldown_days", 6)),
    )
