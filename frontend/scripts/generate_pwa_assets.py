"""Generate PWA icons and iOS splash screens for every Waselni app.

Run from the frontend directory:
    python scripts/generate_pwa_assets.py

The generated PNGs are committed so production builds do not need Pillow.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "pwa-assets"

FONT_CANDIDATES = {
    "bold": [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ],
    "regular": [
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ],
}

ROLES = {
    "customer": {
        "theme": "#6d35c8",
        "theme_dark": "#3f1c7d",
        "background": "#f8f7fc",
        "glyph": "bag",
        "label": "Customer App",
    },
    "merchant": {
        "theme": "#4b2e83",
        "theme_dark": "#291747",
        "background": "#f8f6fc",
        "glyph": "store",
        "label": "Merchant App",
    },
    "captain": {
        "theme": "#1f5a55",
        "theme_dark": "#0d3531",
        "background": "#f4faf8",
        "glyph": "scooter",
        "label": "Captain App",
    },
    "admin": {
        "theme": "#33245a",
        "theme_dark": "#1a1130",
        "background": "#f6f6fb",
        "glyph": "grid",
        "label": "Admin Console",
    },
    "all": {
        "theme": "#6d35c8",
        "theme_dark": "#3f1c7d",
        "background": "#f8f7fc",
        "glyph": "network",
        "label": "Delivery Platform",
    },
}

PORTRAIT_SPLASHES = [
    (640, 1136),
    (750, 1334),
    (828, 1792),
    (1125, 2436),
    (1170, 2532),
    (1179, 2556),
    (1242, 2208),
    (1242, 2688),
    (1284, 2778),
    (1290, 2796),
    (1536, 2048),
    (1668, 2388),
    (2048, 2732),
]

LANDSCAPE_SPLASHES = [
    (1334, 750),
    (2208, 1242),
    (2388, 1668),
    (2688, 1242),
    (2796, 1290),
    (2048, 1536),
    (2732, 2048),
]


def load_font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES[kind]:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def mix(first, second, amount: float):
    return tuple(round(first[i] + (second[i] - first[i]) * amount) for i in range(3))


def shade(color, factor: float):
    return tuple(max(0, min(255, round(channel * factor))) for channel in color)


def vertical_gradient(size, top, bottom) -> Image.Image:
    width, height = size
    strip = Image.new("RGB", (1, height))
    pixels = strip.load()
    for y in range(height):
        pixels[0, y] = mix(top, bottom, y / max(1, height - 1))
    return strip.resize(size, Image.Resampling.BILINEAR)


def ellipse_mask(size, box, blur=0) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).ellipse(box, fill=255)
    if blur:
        mask = mask.filter(ImageFilter.GaussianBlur(blur))
    return mask


def glyph_layer(glyph: str, size: int, scale: float = 1.0) -> Image.Image:
    """Draw a white role glyph on a transparent square canvas."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    s = size
    white = (255, 255, 255, 255)
    soft = (255, 255, 255, 150)

    def unit(value: float) -> float:
        return (0.5 + (value - 0.5) * scale) * s

    def span(value: float) -> float:
        return value * scale * s

    def line(points, width=0.045, color=white):
        draw.line(
            [(unit(x), unit(y)) for x, y in points],
            fill=color,
            width=max(2, round(width * s)),
            joint="curve",
        )

    if glyph == "bag":
        draw.arc(
            [unit(0.33), unit(0.16), unit(0.67), unit(0.54)],
            start=180,
            end=360,
            fill=white,
            width=max(2, round(0.055 * s)),
        )
        draw.rounded_rectangle(
            [unit(0.17), unit(0.35), unit(0.83), unit(0.46)],
            radius=span(0.045),
            fill=white,
        )
        draw.rounded_rectangle(
            [unit(0.19), unit(0.43), unit(0.81), unit(0.84)],
            radius=span(0.09),
            outline=white,
            width=max(2, round(0.052 * s)),
        )
        draw.ellipse(
            [unit(0.475), unit(0.58), unit(0.525), unit(0.64)],
            fill=soft,
        )

    elif glyph == "store":
        draw.rounded_rectangle(
            [unit(0.16), unit(0.22), unit(0.84), unit(0.35)],
            radius=span(0.035),
            fill=white,
        )
        for index in range(5):
            left = 0.16 + index * 0.136
            draw.ellipse(
                [unit(left), unit(0.32), unit(left + 0.136), unit(0.40)],
                fill=white,
            )
        draw.rounded_rectangle(
            [unit(0.22), unit(0.40), unit(0.78), unit(0.84)],
            radius=span(0.04),
            outline=white,
            width=max(2, round(0.045 * s)),
        )
        draw.rounded_rectangle(
            [unit(0.42), unit(0.58), unit(0.58), unit(0.84)],
            radius=span(0.025),
            outline=white,
            width=max(2, round(0.038 * s)),
        )
        draw.rounded_rectangle(
            [unit(0.28), unit(0.48), unit(0.36), unit(0.56)],
            radius=span(0.015),
            fill=soft,
        )
        draw.rounded_rectangle(
            [unit(0.64), unit(0.48), unit(0.72), unit(0.56)],
            radius=span(0.015),
            fill=soft,
        )

    elif glyph == "scooter":
        stroke = max(2, round(0.05 * s))
        draw.ellipse(
            [unit(0.12), unit(0.62), unit(0.40), unit(0.90)],
            outline=white,
            width=stroke,
        )
        draw.ellipse(
            [unit(0.60), unit(0.62), unit(0.88), unit(0.90)],
            outline=white,
            width=stroke,
        )
        line([(0.26, 0.76), (0.64, 0.76), (0.70, 0.76)], width=0.05)
        line([(0.68, 0.76), (0.62, 0.46), (0.56, 0.40)], width=0.05)
        line([(0.48, 0.37), (0.72, 0.37)], width=0.05)
        draw.rounded_rectangle(
            [unit(0.28), unit(0.52), unit(0.48), unit(0.58)],
            radius=span(0.025),
            fill=white,
        )

    elif glyph == "grid":
        for row in range(2):
            for column in range(2):
                x = 0.17 + column * 0.36
                y = 0.17 + row * 0.36
                draw.rounded_rectangle(
                    [unit(x), unit(y), unit(x + 0.30), unit(y + 0.30)],
                    radius=span(0.06),
                    fill=white if (row + column) % 2 == 0 else soft,
                )

    elif glyph == "network":
        points = [(0.50, 0.18), (0.83, 0.44), (0.68, 0.84), (0.32, 0.84), (0.17, 0.44)]
        line(points + [points[0]], width=0.035, color=soft)
        for x, y in points:
            draw.ellipse(
                [unit(x - 0.065), unit(y - 0.065), unit(x + 0.065), unit(y + 0.065)],
                fill=white,
            )
        draw.ellipse(
            [unit(0.44), unit(0.47), unit(0.56), unit(0.59)],
            fill=(255, 255, 255, 190),
        )

    return layer


def make_icon(role: dict, size: int, glyph_scale: float, solid_background: bool = True) -> Image.Image:
    theme = to_rgb(role["theme"])
    theme_dark = to_rgb(role["theme_dark"])

    if solid_background:
        canvas = vertical_gradient((size, size), mix(theme, (255, 255, 255), 0.18), theme_dark).convert("RGBA")
        glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        glow.paste(
            Image.new("RGBA", (size, size), (255, 255, 255, 38)),
            (0, 0),
            ellipse_mask((size, size), (size * 0.05, -size * 0.25, size * 0.95, size * 0.55), blur=size * 0.05),
        )
        canvas = Image.alpha_composite(canvas, glow)
    else:
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    work = size * 2
    glyph = glyph_layer(role["glyph"], work, scale=glyph_scale)
    glyph = glyph.resize((size, size), Image.Resampling.LANCZOS)
    return Image.alpha_composite(canvas, glyph)


def rounded_mask(size: int, radius_ratio: float) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1],
        radius=round(size * radius_ratio),
        fill=255,
    )
    return mask


def make_splash(role: dict, width: int, height: int, app_name: str) -> Image.Image:
    theme = to_rgb(role["theme"])
    theme_dark = to_rgb(role["theme_dark"])
    background = to_rgb(role["background"])
    small = min(width, height)

    canvas = vertical_gradient(
        (width, height),
        mix(background, (255, 255, 255), 0.55),
        mix(background, theme, 0.10),
    ).convert("RGBA")

    decor = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    decor.paste(
        Image.new("RGBA", (width, height), (*theme, 26)),
        (0, 0),
        ellipse_mask(
            (width, height),
            (-width * 0.35, -height * 0.20, width * 0.55, height * 0.42),
            blur=small * 0.09,
        ),
    )
    decor.paste(
        Image.new("RGBA", (width, height), (*theme, 20)),
        (0, 0),
        ellipse_mask(
            (width, height),
            (width * 0.55, height * 0.62, width * 1.25, height * 1.22),
            blur=small * 0.10,
        ),
    )
    canvas = Image.alpha_composite(canvas, decor)

    tile_size = round(small * 0.235)
    tile = vertical_gradient(
        (tile_size, tile_size),
        mix(theme, (255, 255, 255), 0.14),
        theme_dark,
    ).convert("RGBA")
    tile = Image.alpha_composite(
        tile,
        glyph_layer(role["glyph"], tile_size * 2, scale=0.86).resize(
            (tile_size, tile_size), Image.Resampling.LANCZOS
        ),
    )
    tile = Image.composite(tile, Image.new("RGBA", tile.size, (0, 0, 0, 0)), rounded_mask(tile_size, 0.24))

    center_x = width // 2
    center_y = round(height * 0.46)
    tile_left = center_x - tile_size // 2
    tile_top = center_y - tile_size // 2

    shadow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        [
            tile_left,
            tile_top + round(tile_size * 0.10),
            tile_left + tile_size,
            tile_top + tile_size + round(tile_size * 0.10),
        ],
        radius=round(tile_size * 0.26),
        fill=(*theme_dark, 70),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(small * 0.025))
    canvas = Image.alpha_composite(canvas, shadow)
    canvas.alpha_composite(tile, (tile_left, tile_top))

    draw = ImageDraw.Draw(canvas)
    title_font = load_font("bold", round(small * 0.055))
    subtitle_font = load_font("regular", round(small * 0.028))

    title = f"Waselni {app_name}"
    title_y = tile_top + tile_size + round(small * 0.075)
    draw.text((center_x, title_y), title, font=title_font, fill=mix(theme_dark, (20, 16, 34), 0.35), anchor="ma")
    draw.text(
        (center_x, title_y + round(small * 0.072)),
        role["label"],
        font=subtitle_font,
        fill=mix(theme, background, 0.25),
        anchor="ma",
    )

    return canvas.convert("RGB")


def save(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="PNG", optimize=True)


def build_role(key: str, role: dict) -> None:
    role_dir = OUT / key
    icons = role_dir / "icons"
    splashes = role_dir / "splash"

    save(make_icon(role, 512, 0.92), icons / "icon-512.png")
    save(make_icon(role, 192, 0.92), icons / "icon-192.png")
    save(make_icon(role, 180, 0.92), icons / "icon-180.png")
    save(make_icon(role, 32, 0.98), icons / "favicon-32.png")
    save(make_icon(role, 16, 1.0), icons / "favicon-16.png")
    save(make_icon(role, 512, 0.66), icons / "maskable-512.png")
    save(make_icon(role, 192, 0.66), icons / "maskable-192.png")
    save(make_icon(role, 512, 0.84, solid_background=False), icons / "monochrome-512.png")

    app_name = key.capitalize() if key != "all" else ""
    for width, height in PORTRAIT_SPLASHES + LANDSCAPE_SPLASHES:
        save(make_splash(role, width, height, app_name.strip()), splashes / f"splash-{width}x{height}.png")

    print(f"generated {key}: 8 icons, {len(PORTRAIT_SPLASHES) + len(LANDSCAPE_SPLASHES)} splash screens")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for key, role in ROLES.items():
        build_role(key, role)
    print(f"PWA assets written to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
