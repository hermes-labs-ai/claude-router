#!/usr/bin/env python3
"""Render the README terminal preview from its checked-in source text."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1600
HEIGHT = 900
PAGE = "#0b1020"
PANEL = "#111827"
HEADER = "#0f172a"
BODY = "#e5e7eb"
PROMPT = "#60a5fa"
KEY = "#fbbf24"
VALUE = "#34d399"
FONT_PATH = Path("/System/Library/Fonts/Menlo.ttc")


def load_font(size: int) -> ImageFont.FreeTypeFont:
    if not FONT_PATH.exists():
        raise SystemExit(f"Menlo is required to render the preview: {FONT_PATH}")
    return ImageFont.truetype(str(FONT_PATH), size=size)


def draw_json_line(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    line: str,
    font: ImageFont.FreeTypeFont,
) -> None:
    """Draw a JSON line with deterministic, minimal syntax highlighting."""
    x, y = xy
    stripped = line.lstrip()
    indent = line[: len(line) - len(stripped)]
    draw.text((x, y), indent, fill=BODY, font=font)
    x += round(draw.textlength(indent, font=font))

    if stripped.startswith('"') and '":' in stripped:
        key, rest = stripped.split(":", 1)
        key = f"{key}:"
        draw.text((x, y), key, fill=KEY, font=font)
        x += round(draw.textlength(key, font=font))
        color = VALUE if rest.strip().startswith(("true", "false", "null", *"0123456789-")) else BODY
        draw.text((x, y), rest, fill=color, font=font)
        return

    draw.text((x, y), stripped, fill=BODY, font=font)


def render(source: Path, output: Path) -> None:
    lines = source.read_text(encoding="utf-8").splitlines()
    if not lines or not lines[0].startswith("$ claude-router "):
        raise SystemExit(f"unexpected preview source: {source}")

    image = Image.new("RGB", (WIDTH, HEIGHT), PAGE)
    draw = ImageDraw.Draw(image)
    panel = (72, 84, 1528, 816)
    draw.rounded_rectangle(panel, radius=30, fill=PANEL, outline="#263244", width=2)
    draw.rounded_rectangle((72, 84, 1528, 158), radius=30, fill=HEADER)
    draw.rectangle((72, 128, 1528, 158), fill=HEADER)

    for x, color in ((106, "#fb7185"), (130, "#fbbf24"), (154, "#34d399")):
        draw.ellipse((x - 8, 112, x + 8, 128), fill=color)

    title_font = load_font(22)
    body_font = load_font(19)
    draw.text((800, 120), "claude-router preview", fill="#cbd5e1", font=title_font, anchor="mm")

    x = 120
    y = 190
    line_height = 27
    draw.text((x, y), lines[0], fill=PROMPT, font=body_font)
    for line in lines[1:]:
        y += line_height
        draw_json_line(draw, (x, y), line, body_font)

    if y + line_height > panel[3] - 20:
        raise SystemExit("preview output does not fit in the terminal panel")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("assets/preview-source.txt"))
    parser.add_argument("--output", type=Path, default=Path("assets/preview.png"))
    args = parser.parse_args()
    render(args.source, args.output)


if __name__ == "__main__":
    main()
