"""Migra config.toml al formato nuevo conservando tu ig_user_id y tu base_url.

Uso:  python tools/migrate_config.py
Deja una copia del archivo anterior en config.old.toml. También repara el error típico de
tener el número del ID escrito donde va el nombre del campo (``123 = "REEMPLAZA_..."``).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD, TEMPLATE = ROOT / "config.toml", ROOT / "config.template.toml"


def find_id(text: str) -> str | None:
    m = re.search(r'(?m)^\s*ig_user_id\s*=\s*"(\d{5,})"', text) or re.search(
        r'(?m)^\s*(\d{8,})\s*=\s*"REEMPLAZA_CON_TU_IG_USER_ID"', text
    )
    return m.group(1) if m else None


def find_base_url(text: str) -> str | None:
    m = re.search(r'(?m)^\s*base_url\s*=\s*"(https?://[^"]+)"', text)
    return m.group(1) if m else None


def main() -> int:
    if not TEMPLATE.exists():
        print("Falta config.template.toml (¿extrajiste la actualización en esta carpeta?)")
        return 1
    old = OLD.read_text(encoding="utf-8") if OLD.exists() else ""
    if "[[slots]]" in old and "window" in old and "__" not in old:
        print("config.toml ya tiene el formato nuevo; no se cambia nada.")
        return 0
    ig_id, base = find_id(old), find_base_url(old)
    missing = [n for n, v in (("ig_user_id", ig_id), ("base_url", base)) if not v]
    if missing:
        print("No pude leer de tu config.toml:", ", ".join(missing), file=sys.stderr)
        return 1
    if "tudepilacion.cl" in base:
        print("AVISO: base_url sigue con la dirección de ejemplo; revísala.", file=sys.stderr)
    (ROOT / "config.old.toml").write_text(old, encoding="utf-8")
    new = TEMPLATE.read_text(encoding="utf-8").replace("__IG_USER_ID__", ig_id).replace("__BASE_URL__", base)
    OLD.write_bytes(new.encode("utf-8"))  # UTF-8 sin BOM
    print(f"config.toml actualizado (ig_user_id={ig_id}).")
    print(f"base_url={base}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
