from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

from .config import load_config
from .stages import stage_label
from .titles import editorial_title


# Instagram portrait feed format, also known as 4:5.
WIDTH = 1080
HEIGHT = 1350
MARGIN = 72
LOGO_DIR = Path("assets/logos")
BACKGROUND_PATH = Path("assets/backgrounds/weekly-cover.png")


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


def _fit_wrapped_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_lines: int,
    start_size: int,
    min_size: int,
    bold: bool = True,
) -> tuple[ImageFont.ImageFont, list[str]]:
    for size in range(start_size, min_size - 1, -2):
        font = _font(size, bold=bold)
        lines = _wrap(draw, text, font, max_width, max_lines)
        if len(lines) <= max_lines and not any(_text_width(draw, line, font) > max_width for line in lines):
            return font, lines
    font = _font(min_size, bold=bold)
    return font, _wrap(draw, text, font, max_width, max_lines)


def _short_title(scrutin: dict[str, Any]) -> str:
    return editorial_title(scrutin)


def _stage_badge(scrutin: dict[str, Any]) -> str:
    return stage_label(scrutin.get("stage_id")).upper()


def _result_word(scrutin: dict[str, Any]) -> str:
    sort = (scrutin.get("sort") or "").lower()
    if "adopt" in sort:
        return "ADOPTÉ"
    if "rejet" in sort:
        return "REJETÉ"
    return "VOTE"


def _title_color(word: str, default: str) -> str:
    clean = word.upper().strip(".,;:!?()[]{}«»\"'")
    normalized = clean.removeprefix("L'").removeprefix("D'").removeprefix("L’").removeprefix("D’")
    if "ÉTAT" in clean or "ETAT" in clean or clean in {"ASSEMBLÉE", "ASSEMBLEE"}:
        return "#0D3556"
    if normalized in {
        "AIDE",
        "MOURIR",
        "PATRIMOINE",
        "IMMOBILIER",
        "LOGEMENT",
        "SÉCURITÉ",
        "SECURITE",
        "MINEURS",
    }:
        return "#8A1028"
    if normalized in {"DROIT", "LOI", "VOTE", "TEXTE"}:
        return "#A77A2D"
    return default


def _display_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return value


def _round_up_to_five(value: int) -> int:
    return ((value + 4) // 5) * 5


def _draw_colored_title(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    line_height: int,
    max_lines: int,
) -> int:
    x, y = xy
    line: list[str] = []
    lines: list[list[str]] = []
    for word in text.split():
        candidate = " ".join([*line, word])
        if _text_width(draw, candidate, font) <= max_width:
            line.append(word)
            continue
        if line:
            lines.append(line)
        line = [word]
        if len(lines) >= max_lines:
            break
    if line and len(lines) < max_lines:
        lines.append(line)

    for words in lines[:max_lines]:
        cursor = x
        for word in words:
            draw.text((cursor, y), word, fill=_title_color(word, fill), font=font)
            cursor += _text_width(draw, word + " ", font)
        y += line_height
    return y


def _draw_background_photo(img: Image.Image) -> None:
    if BACKGROUND_PATH.exists():
        photo = Image.open(BACKGROUND_PATH).convert("RGB")
        photo = ImageOps.fit(photo, (WIDTH, 780), method=Image.Resampling.LANCZOS, centering=(0.54, 0.48))
        photo = ImageOps.grayscale(photo).convert("RGB")
        photo = ImageEnhance.Contrast(photo).enhance(1.28)
        photo = ImageEnhance.Brightness(photo).enhance(1.04)
        photo = photo.filter(ImageFilter.GaussianBlur(radius=0.35))
        veil = Image.new("RGB", photo.size, "#F2EBDF")
        photo = Image.blend(photo, veil, 0.42)
        fade = Image.new("L", photo.size, 0)
        fade_px = fade.load()
        for y in range(photo.height):
            if y < 160:
                alpha = int(76 * y / 160)
            elif y > 640:
                alpha = max(0, int(76 * (photo.height - y) / 140))
            else:
                alpha = 76
            for x in range(photo.width):
                fade_px[x, y] = alpha
        img.paste(photo, (0, 430), fade)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 276, 10), fill="#173A59")
    draw.rectangle((276, 0, 620, 10), fill="#4F6272")
    draw.rectangle((620, 0, WIDTH, 10), fill="#C8A44D")


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
        font = _fit_font(draw, "inscrits", max_w - 8, 16, bold=True)
        line_1 = "non-"
        line_2 = "inscrits"
        y0 = center_y - 18
        for offset, line in enumerate((line_1, line_2)):
            bbox = draw.textbbox((0, 0), line, font=font)
            draw.text(
                (center_x - (bbox[2] - bbox[0]) / 2, y0 + offset * 18),
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


def _logo_box(sigle: str, slot_width: int) -> tuple[int, int]:
    max_w = max(48, min(74, slot_width - 4))
    max_h = 48
    if sigle in {"EPR", "DR", "RN", "UDR"}:
        max_h = 58
    if sigle in {"HOR", "ECOS"}:
        max_h = 34
    if sigle == "non-inscrits":
        max_w = max(48, min(68, slot_width - 6))
        max_h = 42
    return max_w, max_h


def draw_card(scrutin: dict[str, Any], output: str | Path, config_path: str | Path = "groupes_politiques.json") -> None:
    config = load_config(config_path)
    colors = config.vote_colors
    layout = config.layout_colors
    img = Image.new("RGB", (WIDTH, HEIGHT), layout["background"])
    draw = ImageDraw.Draw(img)

    small_font = _font(22, bold=True)
    meta_font = _font(30)
    footer_font = _font(21)

    # Paper-like grid.
    for x in range(0, WIDTH, 36):
        draw.line([(x, 0), (x, HEIGHT)], fill=layout["grid"], width=1)
    for y in range(0, HEIGHT, 36):
        draw.line([(0, y), (WIDTH, y)], fill=layout["grid"], width=1)
    _draw_background_photo(img)

    title_font, title_lines = _fit_wrapped_font(
        draw,
        _short_title(scrutin),
        WIDTH - 2 * MARGIN,
        max_lines=3,
        start_size=70,
        min_size=50,
        bold=True,
    )
    y = 66
    y = _draw_colored_title(
        draw,
        (MARGIN, y),
        " ".join(title_lines),
        title_font,
        layout["text"],
        WIDTH - 2 * MARGIN,
        title_font.size + 6,
        3,
    )

    underline_y = y + 8
    draw.rounded_rectangle((MARGIN, underline_y, min(WIDTH - MARGIN, MARGIN + 480), underline_y + 8), radius=4, fill=colors["pour"])
    draw.text(
        (MARGIN, underline_y + 28),
        f"Scrutin public n°{scrutin['numero']} · {_display_date(scrutin['date'])}",
        fill="#26313A",
        font=meta_font,
    )

    verdict = _result_word(scrutin)
    badge_y = underline_y + 76
    stage_font = _font(24, bold=True)
    stage_text = _stage_badge(scrutin)
    stage_w = _text_width(draw, stage_text, stage_font) + 36
    draw.rounded_rectangle((MARGIN, badge_y, MARGIN + stage_w, badge_y + 44), radius=6, fill="#0D3556")
    draw.text((MARGIN + 18, badge_y + 9), stage_text, fill="#FFFFFF", font=stage_font)

    stamp_font = _font(30, bold=True)
    stamp_w = _text_width(draw, verdict, stamp_font) + 52
    stamp_x = WIDTH - MARGIN - stamp_w
    draw.rounded_rectangle((stamp_x, badge_y - 4, WIDTH - MARGIN, badge_y + 42), radius=8, outline="#8A1028", width=3)
    draw.text((stamp_x + 26, badge_y + 5), verdict, fill="#8A1028", font=stamp_font)

    legend_y = badge_y + 72
    legend_x = MARGIN
    for key, label in (("pour", "POUR"), ("contre", "CONTRE"), ("abstention", "ABSTENTION")):
        draw.rectangle((legend_x, legend_y + 4, legend_x + 24, legend_y + 28), fill=colors[key])
        draw.rectangle((legend_x, legend_y + 4, legend_x + 24, legend_y + 28), outline=layout["text"], width=1)
        draw.text((legend_x + 36, legend_y), label, fill=layout["text"], font=small_font)
        legend_x += 218

    chart_top = 454
    chart_bottom = 1116
    axis_x = 76
    chart_left = 92
    chart_right = WIDTH - 36
    chart_height = chart_bottom - chart_top
    max_vote_total = max(
        group["pour"] + group["contre"] + group["abstention"]
        for group in scrutin["groups"]
    )
    y_max = max(20, _round_up_to_five(max_vote_total + 5))

    ticks = [0]
    if y_max > 35:
        ticks.append(_round_up_to_five(int(y_max / 2)))
    ticks.append(y_max)
    for tick in ticks:
        tick_y = chart_bottom - int((tick / y_max) * chart_height)
        draw.line((axis_x, tick_y, chart_right, tick_y), fill="#DDD2C2", width=2)
        label = str(tick)
        label_w = _text_width(draw, label, footer_font)
        draw.text((axis_x - label_w - 16, tick_y - 13), label, fill="#5E5144", font=footer_font)
    draw.line((axis_x, chart_bottom, chart_right, chart_bottom), fill=layout["text"], width=3)
    draw.line((axis_x, chart_top, axis_x, chart_bottom), fill=layout["text"], width=3)

    groups = scrutin["groups"]
    gap = 8
    bar_area = chart_right - chart_left
    bar_width = max(44, int((bar_area - gap * (len(groups) - 1)) / len(groups)))
    group_config_by_sigle = {group.sigle: group for group in config.groups}

    for index, group in enumerate(groups):
        x0 = chart_left + index * (bar_width + gap)
        x1 = x0 + bar_width
        logo_center_x = int(x0 + bar_width / 2)
        bottom = chart_bottom
        for key in ("pour", "contre", "abstention"):
            value = group[key]
            if value <= 0:
                continue
            h = int((value / y_max) * chart_height)
            y0 = bottom - h
            draw.rectangle((x0, y0, x1, bottom), fill=colors[key], outline=layout["text"], width=2)
            bottom = y0
        logo_max_w, logo_max_h = _logo_box(group["sigle"], bar_width + gap)
        _draw_logo_badge(
            img,
            draw,
            group_config_by_sigle,
            group["sigle"],
            center_x=logo_center_x,
            center_y=chart_bottom + 58,
            max_w=logo_max_w,
            max_h=logo_max_h,
        )

    footer_top = 1258
    draw.rectangle((0, footer_top, WIDTH, HEIGHT), fill="#111111")
    footer = f"Source : Assemblée nationale · scrutin n°{scrutin['numero']}"
    draw.text((MARGIN, footer_top + 28), footer, fill=layout["background"], font=footer_font)
    handle_font = _font(28, bold=True)
    handle_w = _text_width(draw, config.account_handle, handle_font)
    draw.text((WIDTH - MARGIN - handle_w, footer_top + 26), config.account_handle, fill=layout["background"], font=handle_font)

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
