#!/usr/bin/env python3
"""Genera tarjetas 9:16 (1080x1920) de ejemplo con la marca de Tu Depilación.

    python tools/make_cards.py            # escribe PNG en assets/source/cards/
    igstories prepare                      # los convierte a JPEG en assets/ready/

Todo el contenido está en los diccionarios de abajo: edítalos y vuelve a ejecutar.
Las fuentes se buscan en rutas habituales (DejaVu en Linux, Arial/Georgia en macOS/Windows);
puedes forzarlas con las variables FONT_SERIF_BI, FONT_SERIF_B, FONT_SANS, FONT_SANS_B.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
SAFE_TOP, SAFE_BOTTOM = 250, 340  # la interfaz de Instagram tapa estas franjas
FUCSIA, PLUM, MUTED = (217, 20, 107), (59, 20, 49), (125, 84, 112)
SOFT, WHITE = (255, 211, 228), (255, 255, 255)
BG_TOP, BG_BOTTOM = (255, 244, 249), (255, 214, 230)
PHONE = "+56 9 7882 8869"
CONTENT_BOTTOM = H - SAFE_BOTTOM - 150  # lo que queda sobre el pie con el botón

FONT_CANDIDATES = {
    "FONT_SERIF_BI": ["DejaVuSerif-BoldItalic.ttf", "Georgia Bold Italic.ttf", "georgiaz.ttf"],
    "FONT_SERIF_B": ["DejaVuSerif-Bold.ttf", "Georgia Bold.ttf", "georgiab.ttf"],
    "FONT_SANS": ["DejaVuSans.ttf", "Arial.ttf", "arial.ttf"],
    "FONT_SANS_B": ["DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf"],
}
FONT_DIRS = [
    "/usr/share/fonts/truetype/dejavu",
    "/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    "C:/Windows/Fonts",
]


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    forced = os.environ.get(kind)
    candidates = [forced] if forced else []
    for name in FONT_CANDIDATES[kind]:
        candidates += [str(Path(d) / name) for d in FONT_DIRS]
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size)
    print(f"AVISO: no encontré fuente para {kind}; usando la de Pillow", file=sys.stderr)
    return ImageFont.load_default(size=size)


# ------------------------------------------------------------------------------ primitivas
def canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H))
    px = img.load()
    for y in range(H):
        t = y / (H - 1)
        row = tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3))
        for x in range(W):
            px[x, y] = row
    return img, ImageDraw.Draw(img)


def text_w(d, text, f) -> int:
    return int(d.textlength(text, font=f))


def centered(d, y, text, f, fill):
    d.text(((W - text_w(d, text, f)) / 2, y), text, font=f, fill=fill)


def wrap(d, text, f, max_w) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if text_w(d, trial, f) <= max_w:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def paragraph(d, x, y, text, f, fill, max_w, gap=12, center=False) -> int:
    size = f.size
    for line in wrap(d, text, f, max_w):
        if center:
            centered(d, y, line, f, fill)
        else:
            d.text((x, y), line, font=f, fill=fill)
        y += size + gap
    return y


def brand(d):
    centered(d, SAFE_TOP + 10, "Tu depilación", font("FONT_SERIF_BI", 78), FUCSIA)


def footer(d):
    y0 = H - SAFE_BOTTOM - 130
    d.rounded_rectangle((90, y0, W - 90, y0 + 110), radius=55, fill=FUCSIA)
    centered(d, y0 + 18, "Reserva por WhatsApp", font("FONT_SANS_B", 38), WHITE)
    centered(d, y0 + 64, f"{PHONE} · link en bio", font("FONT_SANS", 28), (255, 225, 238))


def title(d, text, y=SAFE_TOP + 150) -> int:
    f = font("FONT_SERIF_B", 62)
    for line in wrap(d, text, f, W - 160):
        centered(d, y, line, f, PLUM)
        y += 80
    return y + 20


def check(y: int, name: str):
    if y > CONTENT_BOTTOM:
        raise SystemExit(f"{name}: el contenido llega a y={y} y pisa el pie ({CONTENT_BOTTOM})")


# ------------------------------------------------------------------------------- tarjetas
def price_card(name, heading, groups, note=None):
    img, d = canvas()
    brand(d)
    y = title(d, heading)
    row_h = 62
    for gname, rows in groups:
        d.text((90, y), gname, font=font("FONT_SERIF_BI", 46), fill=FUCSIA)
        y += 70
        for label, price, hot in rows:
            if hot:
                d.rounded_rectangle((80, y - 8, W - 80, y + row_h - 12), radius=24, fill=SOFT)
            f, fb = font("FONT_SANS", 37), font("FONT_SANS_B", 37)
            d.text((104, y), label, font=fb if hot else f, fill=PLUM)
            pw = text_w(d, price, fb)
            d.text((W - 104 - pw, y), price, font=fb, fill=FUCSIA if hot else PLUM)
            x = 104 + text_w(d, label, fb if hot else f) + 16
            while x < W - 104 - pw - 16:
                d.ellipse((x, y + 30, x + 5, y + 35), fill=(220, 160, 190))
                x += 16
            y += row_h
        y += 22
    if note:
        d.text((90, y), note, font=font("FONT_SANS", 28), fill=MUTED)
        y += 40
    check(y, name)
    footer(d)
    return img


def myth_card(name, quote, verdict, answer):
    img, d = canvas()
    brand(d)
    f = font("FONT_SANS_B", 36)
    pill = "MITO O VERDAD"
    pw = text_w(d, pill, f) + 70
    d.rounded_rectangle(((W - pw) / 2, 470, (W + pw) / 2, 540), radius=35, fill=FUCSIA)
    centered(d, 487, pill, f, WHITE)
    y = paragraph(d, 0, 620, f"“{quote}”", font("FONT_SERIF_BI", 64), PLUM, W - 180, gap=14, center=True)
    d.line((W / 2 - 80, y + 30, W / 2 + 80, y + 30), fill=FUCSIA, width=5)
    centered(d, y + 80, verdict.upper(), font("FONT_SERIF_B", 60), FUCSIA)
    y = paragraph(d, 0, y + 190, answer, font("FONT_SANS", 42), PLUM, W - 200, gap=14, center=True)
    check(y, name)
    footer(d)
    return img


def list_card(name, heading, items):
    img, d = canvas()
    brand(d)
    y = title(d, heading)
    for head, body in items:
        d.text((90, y), "◆", font=font("FONT_SANS_B", 30), fill=FUCSIA)
        d.text((140, y - 6), head, font=font("FONT_SERIF_B", 44), fill=FUCSIA)
        y += 62
        y = paragraph(d, 140, y, body, font("FONT_SANS", 34), PLUM, W - 230, gap=8) + 26
    check(y, name)
    footer(d)
    return img


def steps_card(name):
    img, d = canvas()
    brand(d)
    y = title(d, "Reservar es muy simple")
    steps = [
        ("Escríbenos", "Cuéntanos qué zonas quieres por WhatsApp o mensaje directo."),
        ("Confirma con el abono", "Abono de $5.000 para confirmar tu hora."),
        ("Ven y relájate", "Te atendemos con calma, en un ambiente privado."),
    ]
    for n, (head, body) in enumerate(steps, 1):
        d.ellipse((90, y, 180, y + 90), fill=FUCSIA)
        centered_x = 90 + (90 - text_w(d, str(n), font("FONT_SERIF_BI", 54))) / 2
        d.text((centered_x, y + 8), str(n), font=font("FONT_SERIF_BI", 54), fill=WHITE)
        d.text((215, y - 4), head, font=font("FONT_SERIF_B", 46), fill=PLUM)
        end = paragraph(d, 215, y + 58, body, font("FONT_SANS", 34), MUTED, W - 300, gap=8)
        y = max(y + 130, end) + 40
    d.rounded_rectangle((80, y, W - 80, y + 190), radius=34, fill=WHITE, outline=SOFT, width=4)
    d.text((115, y + 24), "Si necesitas anular", font=font("FONT_SERIF_B", 40), fill=FUCSIA)
    y2 = paragraph(
        d, 115, y + 84, "Avisa con 24 horas de anticipación y tu abono se reembolsa (una vez por clienta).",
        font("FONT_SANS", 32), PLUM, W - 230, gap=8,
    )
    check(y2, name)
    footer(d)
    return img


def place_card(name):
    img, d = canvas()
    brand(d)
    y = title(d, "Te esperamos en Serena Norte")
    d.rounded_rectangle((80, y, W - 80, y + 330), radius=40, fill=WHITE, outline=SOFT, width=4)
    d.text((120, y + 36), "Los Puquios 1676", font=font("FONT_SERIF_B", 60), fill=PLUM)
    paragraph(
        d, 120, y + 124, "Villa El Romero, La Serena. Es Villa El Romero, no el pueblo de El Romero.",
        font("FONT_SANS", 34), MUTED, W - 240, gap=8,
    )
    y += 370
    d.rounded_rectangle((80, y, W - 80, y + 290), radius=40, fill=WHITE, outline=SOFT, width=4)
    d.text((120, y + 30), "Horario", font=font("FONT_SERIF_BI", 46), fill=FUCSIA)
    d.text((120, y + 100), "Lunes a sábado", font=font("FONT_SANS_B", 42), fill=PLUM)
    d.text((120, y + 156), "15:00 a 20:00", font=font("FONT_SANS", 42), fill=PLUM)
    d.text((120, y + 220), "Antes de las 15:00, consulta disponibilidad.", font=font("FONT_SANS", 28), fill=MUTED)
    y += 330
    check(y, name)
    footer(d)
    return img


def combo_card(name):
    img, d = canvas()
    brand(d)
    y = title(d, "Cara completa")
    cx, cy, r = W // 2, y + 270, 270
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=FUCSIA)
    d.ellipse((cx - r + 18, cy - r + 18, cx + r - 18, cy + r - 18), outline=(255, 190, 215), width=4)
    f = font("FONT_SERIF_BI", 96)
    centered(d, cy - 80, "$10.000", f, WHITE)
    centered(d, cy + 60, "una sola sesión", font("FONT_SANS_B", 34), WHITE)
    y = cy + r + 60
    y = paragraph(
        d, 0, y, "Equivale a 7 zonas sueltas que suman $19.000.", font("FONT_SERIF_B", 48), PLUM,
        W - 200, gap=12, center=True,
    )
    y = paragraph(
        d, 0, y + 20, "Cejas, patillas, frente, bozo, cuello, mentón y nariz.", font("FONT_SANS", 36),
        MUTED, W - 220, gap=10, center=True,
    )
    check(y, name)
    footer(d)
    return img


# ------------------------------------------------------------------------------- contenido
CARDS = {
    "precios-rostro-brazos": lambda n: price_card(
        n, "Precios · Rostro y brazos",
        [
            ("Rostro", [("Cejas", "$4.000", 0), ("Patillas", "$4.000", 0), ("Frente", "$2.000", 0),
                        ("Bozo", "$2.000", 0), ("Cuello", "$3.000", 0), ("Mentón", "$2.000", 0),
                        ("Nariz", "$2.000", 0), ("Cara completa", "$10.000", 1)]),
            ("Brazos y axilas", [("Axila", "$3.000", 0), ("Brazo completo (2)", "$8.000", 0),
                                 ("Medio brazo (2)", "$5.000", 0)]),
        ],
        "(2) = precio por ambos lados",
    ),
    "precios-cuerpo-1": lambda n: price_card(
        n, "Precios · Abdomen y espalda",
        [
            ("Abdomen", [("Abdomen", "$7.000", 0), ("Medio abdomen", "$4.000", 0)]),
            ("Espalda y glúteos", [("Espalda completa", "$8.000", 0), ("Media espalda", "$5.000", 0),
                                   ("Colita", "$4.000", 0), ("Glúteos", "$4.000", 0),
                                   ("Entre glúteos", "$5.000", 0)]),
        ],
    ),
    "precios-cuerpo-2": lambda n: price_card(
        n, "Precios · Piernas y zona íntima",
        [
            ("Piernas", [("Pierna completa (2)", "$12.000", 0), ("Media pierna (2)", "$7.000", 0)]),
            ("Zona íntima", [("Rebaje corto", "$4.000", 0), ("Rebaje largo", "$7.000", 0),
                             ("Brasileño", "$10.000", 0), ("Completo", "$15.000", 0)]),
        ],
        "(2) = precio por ambos lados",
    ),
    "combo-cara": combo_card,
    "mito-vello-grueso": lambda n: myth_card(
        n, "Si me depilo con cera, el vello sale más grueso.", "Mito",
        "La cera no cambia el tipo de vello. Al sacarlo de raíz, con el tiempo muchas clientas lo notan más fino y suave.",
    ),
    "mito-dejar-crecer": lambda n: myth_card(
        n, "Tengo que dejar crecer el vello varias semanas.", "Mito",
        "Con unos 5 mm la cera ya lo toma bien. Esperar más solo alarga el tiempo entre sesiones.",
    ),
    "mito-afeitar-antes": lambda n: myth_card(
        n, "Afeitarme antes ayuda a que duela menos.", "Mito",
        "Si te afeitas, el vello queda demasiado corto y la cera no alcanza a tomarlo. Evita afeitarte entre sesiones.",
    ),
    "cuidados-post": lambda n: list_card(
        n, "Después de tu hora",
        [
            ("No toques la zona", "Evita tocar la piel recién depilada."),
            ("Hidrata", "Sin alcohol ni fragancia, al menos 2 veces al día. Toma harta agua."),
            ("Exfolia con paciencia", "Espera al menos un par de días."),
            ("Si hay irritación", "No la toques ni la agredas. Déjala descansar."),
            ("Higiene", "Usa siempre toallas limpias sobre la zona."),
            ("¿Dudas?", "Escríbele a tu depiladora."),
        ],
    ),
    "preparacion": lambda n: list_card(
        n, "Antes de tu hora",
        [
            ("Vello de unos 5 mm", "No te afeites: así la cera lo toma bien."),
            ("Exfolia suave", "1 o 2 días antes. El mismo día, mejor no."),
            ("Piel limpia y seca", "Sin cremas ni aceites el día de tu hora."),
            ("Ropa cómoda", "Holgada, para estar relajada y que no roce después."),
        ],
    ),
    "como-reservar": steps_card,
    "ubicacion-horario": place_card,
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="assets/source/cards", type=Path)
    ap.add_argument("--only", nargs="*", help="nombres de tarjetas a generar")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for name, build in CARDS.items():
        if args.only and name not in args.only:
            continue
        build(name).save(args.out / f"{name}.png", optimize=True)
        print("ok", name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
