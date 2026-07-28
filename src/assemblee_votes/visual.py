from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from .config import load_config


SIZE = 1080
MARGIN = 72
LOGO_DIR = Path("assets/logos")


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Helvetica.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int, bold: bool = True) -> ImageFont.ImageFont:
    for size in range(start_size, 9, -1):
        font = _font(size, bold=bold)
        if _text_width(draw, text, font) <= max_width:
            return font
    return _font(10, bold=bold)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int, max_lines: int) -> list[str]:
    words = text.replace("\n", " ").split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if _text_width(draw, candidate, font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and len(" ".join(words)) > len(" ".join(lines)):
        lines[-1] = lines[-1].rstrip(" .") + "..."
    return lines


def _short_title(scrutin: dict[str, Any]) -> str:
    dossier = scrutin.get("dossier")
    if dossier:
        return dossier.upper()
    title = scrutin["titre"]
    title = title.replace("l'ensemble du ", "").replace("sur ", "")
    return title.upper()


def _subtitle(scrutin: dict[str, Any]) -> str:
    return f"{scrutin['type_vote'].capitalize()} n°{scrutin['numero']} du {scrutin['date']} - {scrutin['sort']}."


def _load_logo(sigle: str) -> Image.Image | None:
    for suffix in (".png", ".jpg", ".jpeg"):
        path = LOGO_DIR / f"{sigle}{suffix}"
        if path.exists():
            logo = Image.open(path).convert("RGBA")
            bbox = logo.getbbox()
            if bbox:
                logo = logo.crop(bbox)
            return logo
    return None


def _paste_contained(base: Image.Image, logo: Image.Image, box: tuple[int, int, int, int]) -> None:
    x0, y0, x1, y1 = box
    max_w = x1 - x0
    max_h = y1 - y0
    logo.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    x = x0 + (max_w - logo.width) // 2
    y = y0 + (max_h - logo.height) // 2
    base.paste(logo, (x, y), logo)


def _draw_logo_badge(
    img: Image.Image,
    draw: ImageDraw.ImageDraw,
    group_config_by_sigle: dict[str, Any],
    sigle: str,
    center_x: int,
    center_y: int,
    max_w: int,
    max_h: int,
) -> None:
    if sigle == "non-inscrits":
        font = _fit_font(draw, "inscrits", max_w - 8, 13, bold=True)
        line_1 = "non-"
        line_2 = "inscrits"
        y0 = center_y - 16
        for offset, line in enumerate((line_1, line_2)):
            bbox = draw.textbbox((0, 0), line, font=font)
            draw.text(
                (center_x - (bbox[2] - bbox[0]) / 2, y0 + offset * 16),
                line,
                fill="#6F767D",
                font=font,
            )
        return

    logo = _load_logo(sigle)
    if logo:
        _paste_contained(img, logo, (center_x - max_w // 2, center_y - max_h // 2, center_x + max_w // 2, center_y + max_h // 2))
        return

    group_config = group_config_by_sigle.get(sigle)
    color = getattr(group_config, "logo_color", "#8D949A")
    text = getattr(group_config, "logo_text", sigle)
    if len(text) <= 3:
        radius = min(max_w, max_h) // 2
        draw.ellipse((center_x - radius, center_y - radius, center_x + radius, center_y + radius), fill=color)
        font = _fit_font(draw, text, radius * 2 - 10, 18, bold=True)
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text((center_x - (bbox[2] - bbox[0]) / 2, center_y - (bbox[3] - bbox[1]) / 2 - 1), text, fill="white", font=font)
    else:
        w = max_w
        h = min(max_h, 34)
        x0 = center_x - w // 2
        y0 = center_y - h // 2
        draw.rounded_rectangle((x0, y0, x0 + w, y0 + h), radius=5, fill="white", outline=color, width=2)
        font = _fit_font(draw, text, w - 8, 15, bold=True)
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text((center_x - (bbox[2] - bbox[0]) / 2, center_y - (bbox[3] - bbox[1]) / 2 - 1), text, fill=color, font=font)


def draw_card(scrutin: dict[str, Any], output: str | Path, config_path: str | Path = "groupes_politiques.json") -> None:
    config = load_config(config_path)
    colors = config.vote_colors
    layout = config.layout_colors
    img = Image.new("RGB", (SIZE, SIZE), layout["background"])
    draw = ImageDraw.Draw(img)

    title_font = _font(62, bold=True)
    subtitle_font = _font(30)
    small_font = _font(22, bold=True)
    footer_font = _font(18)

    # Paper-like grid.
    for x in range(0, SIZE, 36):
        draw.line([(x, 0), (x, SIZE)], fill=layout["grid"], width=1)
    for y in range(0, SIZE, 36):
        draw.line([(0, y), (SIZE, y)], fill=layout["grid"], width=1)

    y = 58
    last_title_bbox = None
    for line in _wrap(draw, _short_title(scrutin), title_font, SIZE - 2 * MARGIN, 3):
        draw.text((MARGIN, y), line, fill=layout["text"], font=title_font)
        last_title_bbox = draw.textbbox((MARGIN, y), line, font=title_font)
        y += 66

    # Accent underline under the first impactful line segment.
    underline_y = (last_title_bbox[3] if last_title_bbox else y) + 10
    draw.rounded_rectangle((MARGIN, underline_y, min(SIZE - MARGIN, MARGIN + 420), underline_y + 7), radius=4, fill=colors["pour"])
    y = underline_y + 36

    for line in _wrap(draw, _subtitle(scrutin), subtitle_font, SIZE - 2 * MARGIN, 2):
        draw.text((MARGIN, y), line, fill=layout["text"], font=subtitle_font)
        y += 38

    legend_y = y + 18
    legend_x = MARGIN
    for key, label in (("pour", "POUR"), ("contre", "CONTRE"), ("abstention", "ABSTENU")):
        draw.ellipse((legend_x, legend_y + 5, legend_x + 20, legend_y + 25), fill=colors[key])
        draw.text((legend_x + 30, legend_y), label, fill=layout["text"], font=small_font)
        legend_x += 160

    chart_top = 432
    chart_bottom = 804
    axis_x = 98
    chart_left = 112
    chart_right = SIZE - 54
    chart_height = chart_bottom - chart_top
    max_members = max(max(group["membres"], group["pour"] + group["contre"] + group["abstention"] + group["non_votant"]) for group in scrutin["groups"])
    y_max = max(50, ((max_members + 49) // 50) * 50)

    for tick in range(0, y_max + 1, 50):
        tick_y = chart_bottom - int((tick / y_max) * chart_height)
        draw.line((axis_x, tick_y, chart_right, tick_y), fill=layout["grid"], width=2)
        label = str(tick)
        label_w = _text_width(draw, label, footer_font)
        draw.text((axis_x - label_w - 16, tick_y - 11), label, fill=layout["text"], font=footer_font)
    draw.line((axis_x, chart_bottom, chart_right, chart_bottom), fill=layout["text"], width=2)
    draw.line((axis_x, chart_top, axis_x, chart_bottom), fill=layout["text"], width=2)

    groups = scrutin["groups"]
    gap = 16
    bar_area = chart_right - chart_left
    bar_width = max(34, int((bar_area - gap * (len(groups) - 1)) / len(groups)))
    group_config_by_sigle = {group.sigle: group for group in config.groups}

    for index, group in enumerate(groups):
        x0 = chart_left + index * (bar_width + gap)
        x1 = x0 + bar_width
        bottom = chart_bottom
        for key in ("non_votant", "abstention", "contre", "pour"):
            value = group[key]
            if value <= 0:
                continue
            h = int((value / y_max) * chart_height)
            y0 = bottom - h
            color_key = key if key != "abstention" else "abstention"
            draw.rectangle((x0, y0, x1, bottom), fill=colors[color_key], outline=layout["text"])
            bottom = y0
        _draw_logo_badge(
            img,
            draw,
            group_config_by_sigle,
            group["sigle"],
            center_x=int(x0 + bar_width / 2),
            center_y=chart_bottom + 42,
            max_w=max(42, min(70, bar_width + gap - 8)),
            max_h=46,
        )

    total_line = (
        f"TOTAL  POUR {scrutin['totals']['pour']}  /  CONTRE {scrutin['totals']['contre']}  /  "
        f"ABST. {scrutin['totals']['abstention']}"
    )
    draw.text((MARGIN, 890), total_line, fill=layout["text"], font=small_font)

    footer_top = 944
    draw.rectangle((0, footer_top, SIZE, SIZE), fill="#111111")
    footer = f"Source : Assemblee nationale, scrutin public n°{scrutin['numero']} - {scrutin['source_url']}"
    footer_y = footer_top + 18
    for line in _wrap(draw, footer, footer_font, SIZE - 2 * MARGIN - 180, 2):
        draw.text((MARGIN, footer_y), line, fill=layout["background"], font=footer_font)
        footer_y += 26
    handle_w = _text_width(draw, config.account_handle, small_font)
    draw.text((SIZE - MARGIN - handle_w, footer_top + 42), config.account_handle, fill=layout["background"], font=small_font)

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    img.save(output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Genere une carte Instagram depuis un scrutin normalise.")
    parser.add_argument("--input", default="work/latest_scrutins.json")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--config", default="groupes_politiques.json")
    args = parser.parse_args()

    scrutins = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not scrutins:
        print("Aucun scrutin a generer.")
        return
    for scrutin in scrutins:
        output = Path(args.output_dir) / f"scrutin-{scrutin['numero']}.png"
        draw_card(scrutin, output, args.config)
        print(f"Image ecrite: {output}")


if __name__ == "__main__":
    main()
