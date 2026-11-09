#!/usr/bin/env python3
"""Draw the program icon and write PNG, ICO (Windows) and ICNS (macOS) files.

    python packaging/make_icons.py --text SC --color "#2f6f9f" --out packaging/icons

Needs Pillow (build-time only; the program itself does not use it).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf", "Helvetica.ttc",
                 "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
                 "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def draw(text: str, color: str, size: int = 1024) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = size // 16
    d.rounded_rectangle((pad, pad, size - pad, size - pad), radius=size // 5, fill=color)
    d.rounded_rectangle((pad, pad + size // 2, size - pad, size - pad), radius=size // 5,
                        fill=tuple(int(color[i:i + 2], 16) * 4 // 5 for i in (1, 3, 5)) + (255,))
    d.rectangle((pad, pad + size // 2, size - pad, pad + size // 2 + size // 5),
                fill=tuple(int(color[i:i + 2], 16) * 4 // 5 for i in (1, 3, 5)) + (255,))
    f = font(int(size * (0.42 if len(text) <= 2 else 0.30)))
    box = d.textbbox((0, 0), text, font=f)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((size - w) / 2 - box[0], (size - h) / 2 - box[1]), text, font=f, fill="white")
    return img


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--color", default="#2f6f9f")
    ap.add_argument("--out", type=Path, default=Path("packaging/icons"))
    ap.add_argument("--source", type=Path, help="use this square PNG instead of drawing one")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    img = (Image.open(args.source).convert("RGBA").resize((1024, 1024), Image.LANCZOS)
           if args.source else draw(args.text, args.color))
    img.save(args.out / "app.png")
    img.resize((256, 256), Image.LANCZOS).save(args.out / "app-256.png")
    img.save(args.out / "app.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    img.save(args.out / "app.icns")
    print("icons written to", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
