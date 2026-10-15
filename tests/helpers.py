"""Utilidades compartidas por las pruebas: proyecto temporal con configuración válida."""

from __future__ import annotations

import datetime as dt
import shutil
import tempfile
from pathlib import Path

from PIL import Image

CONFIG = """
timezone = "America/Santiago"
default_cooldown_days = 3

[account]
ig_user_id = "123"
base_url = "{graph}"
api_version = ""
poll_interval_s = 0
poll_timeout_s = 5
max_retries = 2
timeout_s = 1.5

[hosting]
provider = "static"
base_url = "{static}"
preflight = true

[[slots]]
name = "midday"
time = "12:30"
days = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
max_attempts = 3

[slots.tags_by_weekday]
mon = ["a"]
tue = ["b"]
wed = ["a"]
thu = ["b"]
fri = ["a"]
sat = ["b"]
sun = ["a"]
"""

STORIES = """
[[story]]
id = "a1"
image = "a1.jpg"
tags = ["a"]

[[story]]
id = "a2"
image = "a2.jpg"
tags = ["a"]

[[story]]
id = "b1"
image = "b1.jpg"
tags = ["b"]
"""


def make_project(graph_url: str = "http://127.0.0.1:1", static_url: str = "http://127.0.0.1:1/static") -> Path:
    root = Path(tempfile.mkdtemp(prefix="igstories-test-"))
    (root / "content").mkdir()
    (root / "assets" / "ready").mkdir(parents=True)
    (root / "assets" / "source").mkdir(parents=True)
    (root / "config.toml").write_text(CONFIG.format(graph=graph_url, static=static_url), encoding="utf-8")
    (root / "content" / "stories.toml").write_text(STORIES, encoding="utf-8")
    for name in ("a1", "a2", "b1"):
        Image.new("RGB", (1080, 1920), (255, 200, 220)).save(root / "assets" / "ready" / f"{name}.jpg", "JPEG")
    return root


def cleanup(root: Path) -> None:
    shutil.rmtree(root, ignore_errors=True)


def santiago(y, m, d, hh, mm):
    from zoneinfo import ZoneInfo

    return dt.datetime(y, m, d, hh, mm, tzinfo=ZoneInfo("America/Santiago"))
