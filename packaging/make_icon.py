"""Erzeugt packaging/icon.ico — ein einfaches, sauberes Produkt-Icon.

Motiv: dunkelblaue abgerundete Kachel mit weißem "P" und einem
Schild-Akzent (Datenschutz). Bewusst schlicht gehalten; kann später
durch ein Designer-Icon ersetzt werden (gleicher Dateiname genügt).

Aufruf:  python packaging/make_icon.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).parent
SIZES = [16, 24, 32, 48, 64, 128, 256]
BG = (16, 42, 84, 255)  # dunkles Marineblau
FG = (255, 255, 255, 255)
ACCENT = (74, 222, 128, 255)  # gruener Schild-Punkt: "geschuetzt"


def _font(px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default()


def render(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    radius = max(2, size // 5)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=BG)

    font = _font(int(size * 0.62))
    bbox = draw.textbbox((0, 0), "P", font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x = (size - w) / 2 - bbox[0]
    y = (size - h) / 2 - bbox[1]
    draw.text((x, y), "P", font=font, fill=FG)

    # Gruener Akzent-Punkt unten rechts (ab 32px sichtbar sinnvoll).
    if size >= 32:
        d = max(4, size // 5)
        margin = max(2, size // 12)
        x1 = size - margin - d
        y1 = size - margin - d
        draw.ellipse([x1, y1, x1 + d, y1 + d], fill=ACCENT)

    return img


def main() -> None:
    images = [render(s) for s in SIZES]
    out = HERE / "icon.ico"
    images[-1].save(out, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"OK: {out}")


if __name__ == "__main__":
    main()
