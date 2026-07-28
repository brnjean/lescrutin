from __future__ import annotations

import io
import json
import textwrap
import zipfile
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from .fetch import _is_significant, _scrutin_number_from_name, normalize_scrutin
from .stages import STAGE_ORDER, stage_label
from .titles import editorial_title
from .verify import verify_scrutin
from .weekly_copy import descriptions_by_numero, load_or_create_weekly_copy


SIZE = 1080
MARGIN = 72
BACKGROUND_PATH = Path("assets/backgrounds/weekly-cover.png")
VOTE_COLORS = {
    "pour": "#7A1024",
    "contre": "#D8D0C4",
    "abstention": "#8B6C4D",
}
TEXT = "#111111"
PAPER = "#F2EBDF"
GRID = "#E3D9CA"
BLACK = "#111111"


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


def _wrap(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
    max_lines: int,
) -> list[str]:
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


def _draw_wrapped(
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
    for line in _wrap(draw, text, font, max_width, max_lines):
        draw.text((x, y), line, fill=fill, font=font)
        y += line_height
    return y


def _paper() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (SIZE, SIZE), PAPER)
    draw = ImageDraw.Draw(img)
    for x in range(0, SIZE, 36):
        draw.line([(x, 0), (x, SIZE)], fill=GRID, width=1)
    for y in range(0, SIZE, 36):
        draw.line([(0, y), (SIZE, y)], fill=GRID, width=1)
    return img, draw


def _format_date(value: str) -> str:
    return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")


def _week_bounds(day: date) -> tuple[date, date]:
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


def _week_id(start: date) -> str:
    return f"week-{start.isoformat()}"


def _week_label(start: date, end: date) -> str:
    return f"Du {start.strftime('%d/%m')} au {end.strftime('%d/%m/%Y')}"


def _result_word(scrutin: dict[str, Any]) -> str:
    sort = (scrutin.get("sort") or "").lower()
    if "adopt" in sort:
        return "Adopté"
    if "rejet" in sort:
        return "Rejeté"
    return "Vote"


def _vote_margin(scrutin: dict[str, Any]) -> int:
    return abs(int(scrutin["totals"]["pour"]) - int(scrutin["totals"]["contre"]))


def _sort_votes(scrutins: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        scrutins,
        key=lambda s: (
            s["date"],
            -STAGE_ORDER.get(s.get("stage_id") or "", 99),
            s["numero"],
        ),
        reverse=True,
    )


def select_latest_week(scrutins: list[dict[str, Any]]) -> tuple[date, date, list[dict[str, Any]]]:
    if not scrutins:
        raise ValueError("Aucun scrutin hebdomadaire disponible.")
    latest = max(datetime.strptime(scrutin["date"], "%Y-%m-%d").date() for scrutin in scrutins)
    start, end = _week_bounds(latest)
    weekly = [
        scrutin
        for scrutin in scrutins
        if start <= datetime.strptime(scrutin["date"], "%Y-%m-%d").date() <= end
    ]
    return start, end, _sort_votes(weekly)


def load_weekly_scrutins_from_zip(
    zip_bytes: bytes,
    config_path: str | Path,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[date, date, list[dict[str, Any]]]:
    candidates: list[tuple[str, dict[str, Any]]] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.startswith("json/") and name.endswith(".json")
        ]
        for name in sorted(names, key=_scrutin_number_from_name, reverse=True):
            doc = json.loads(archive.read(name))
            scrutin = doc["scrutin"]
            if not _is_significant(scrutin):
                continue
            raw_date = scrutin["dateScrutin"]
            if start_date and raw_date < start_date:
                continue
            if end_date and raw_date > end_date:
                continue
            candidates.append((name, doc))
        if start_date and end_date:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
            weekly_docs = candidates
        else:
            if not candidates:
                raise ValueError("Aucun scrutin hebdomadaire disponible.")
            latest = max(
                datetime.strptime(doc["scrutin"]["dateScrutin"], "%Y-%m-%d").date()
                for _, doc in candidates
            )
            start, end = _week_bounds(latest)
            weekly_docs = [
                (name, doc)
                for name, doc in candidates
                if start
                <= datetime.strptime(doc["scrutin"]["dateScrutin"], "%Y-%m-%d").date()
                <= end
            ]

        selected: list[dict[str, Any]] = []
        for _, doc in weekly_docs:
            normalized = asdict(normalize_scrutin(doc, config_path))
            verification = verify_scrutin(normalized)
            if not verification.passed:
                raise ValueError(
                    f"Verification source echouee pour le scrutin {normalized['numero']}: "
                    + "; ".join(verification.errors)
                )
            selected.append(normalized)
    if start_date and end_date:
        return start, end, _sort_votes(selected)
    return start, end, _sort_votes(selected)


def _draw_footer(draw: ImageDraw.ImageDraw, slide_number: int, total: int, dark: bool = False) -> None:
    fill = "#F2EBDF" if dark else TEXT
    small = _font(20, bold=True)
    draw.text((MARGIN, SIZE - 58), "@lescrutin", fill=fill, font=small)
    page = f"{slide_number}/{total}"
    draw.text((SIZE - MARGIN - _text_width(draw, page, small), SIZE - 58), page, fill=fill, font=small)


def draw_cover(
    output: str | Path,
    start: date,
    end: date,
    total_slides: int,
) -> None:
    if BACKGROUND_PATH.exists():
        img = Image.open(BACKGROUND_PATH).convert("RGB").resize((SIZE, SIZE))
    else:
        img, _ = _paper()
    img = ImageEnhance.Contrast(img).enhance(1.12)
    img = img.filter(ImageFilter.GaussianBlur(radius=0.4))
    overlay = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 108))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    eyebrow = _font(26, bold=True)
    title = _font(78, bold=True)
    subtitle = _font(30)
    draw.text((MARGIN, 86), "LA SEMAINE POLITIQUE", fill="#F2EBDF", font=eyebrow)
    y = 178
    for line in ("CETTE SEMAINE", "À L'ASSEMBLÉE"):
        draw.text((MARGIN, y), line, fill="#FFFFFF", font=title)
        y += 86
    draw.rounded_rectangle((MARGIN, y + 10, MARGIN + 470, y + 18), radius=4, fill="#8A1028")
    y += 62
    _draw_wrapped(
        draw,
        (MARGIN, y),
        _week_label(start, end),
        subtitle,
        "#F2EBDF",
        SIZE - 2 * MARGIN,
        40,
        2,
    )
    _draw_footer(draw, 1, total_slides, dark=True)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    img.save(output)


def draw_vote_slide(
    scrutin: dict[str, Any],
    output: str | Path,
    slide_number: int,
    total_slides: int,
    description: str,
) -> None:
    img, draw = _paper()
    stage = stage_label(scrutin.get("stage_id")).upper()
    title = editorial_title(scrutin)
    badge_font = _font(24, bold=True)
    title_font = _font(58, bold=True)
    body_font = _font(28)
    small_font = _font(23)
    stat_font = _font(30, bold=True)

    draw.rounded_rectangle((MARGIN, 72, MARGIN + 310, 118), radius=6, fill=BLACK)
    draw.text((MARGIN + 18, 82), stage, fill=PAPER, font=badge_font)
    draw.text((MARGIN, 144), f"Scrutin n°{scrutin['numero']} · {_format_date(scrutin['date'])}", fill=TEXT, font=small_font)

    y = _draw_wrapped(draw, (MARGIN, 202), title.upper(), title_font, TEXT, SIZE - 2 * MARGIN, 64, 3)
    draw.rounded_rectangle((MARGIN, y + 10, MARGIN + 390, y + 18), radius=4, fill=VOTE_COLORS["pour"])
    y += 60

    result = _result_word(scrutin)
    draw.text((MARGIN, y), result, fill=TEXT, font=stat_font)
    y += 58

    totals = scrutin["totals"]
    total_votes = max(1, totals["pour"] + totals["contre"] + totals["abstention"])
    bar_x0 = MARGIN
    bar_y0 = y + 22
    bar_w = SIZE - 2 * MARGIN
    bar_h = 34
    cursor = bar_x0
    for key in ("pour", "contre", "abstention"):
        width = int(bar_w * totals[key] / total_votes)
        draw.rectangle((cursor, bar_y0, cursor + width, bar_y0 + bar_h), fill=VOTE_COLORS[key])
        cursor += width
    draw.rectangle((bar_x0, bar_y0, bar_x0 + bar_w, bar_y0 + bar_h), outline=TEXT, width=2)
    y = bar_y0 + 64

    stat_line = f"{totals['pour']} pour / {totals['contre']} contre / {totals['abstention']} abst."
    draw.text((MARGIN, y), stat_line, fill=TEXT, font=stat_font)
    y += 58
    margin = _vote_margin(scrutin)
    draw.text((MARGIN, y), f"Écart pour/contre : {margin} voix", fill="#5E5144", font=small_font)
    y += 62

    text = description.strip() or "Texte à compléter avant publication."
    _draw_wrapped(draw, (MARGIN, y), text, body_font, TEXT, SIZE - 2 * MARGIN, 35, 6)

    source = f"Source : Assemblée nationale, scrutin public n°{scrutin['numero']}"
    draw.text((MARGIN, SIZE - 104), source, fill="#5E5144", font=small_font)
    _draw_footer(draw, slide_number, total_slides)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    img.save(output)


def draw_definitions(output: str | Path, slide_number: int, total_slides: int) -> None:
    img, draw = _paper()
    title_font = _font(62, bold=True)
    heading_font = _font(30, bold=True)
    body_font = _font(27)
    draw.text((MARGIN, 78), "COMPRENDRE", fill=TEXT, font=title_font)
    draw.text((MARGIN, 144), "LES ÉTAPES", fill=TEXT, font=title_font)
    draw.rounded_rectangle((MARGIN, 222, MARGIN + 430, 230), radius=4, fill=VOTE_COLORS["pour"])
    y = 286
    items = [
        ("Lecture définitive", "Le dernier vote parlementaire sur le texte."),
        ("Texte de CMP", "Un compromis entre députés et sénateurs. La loi n'est définitive que si les deux chambres adoptent le même texte."),
        ("Nouvelle lecture", "Le texte revient à l'Assemblée après un désaccord entre les deux chambres."),
    ]
    for heading, body in items:
        draw.text((MARGIN, y), heading.upper(), fill=TEXT, font=heading_font)
        y += 42
        y = _draw_wrapped(draw, (MARGIN, y), body, body_font, TEXT, SIZE - 2 * MARGIN, 34, 3)
        y += 54
    _draw_footer(draw, slide_number, total_slides)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    img.save(output)


def draw_cta(output: str | Path, slide_number: int, total_slides: int) -> None:
    img, draw = _paper()
    title_font = _font(64, bold=True)
    body_font = _font(31)
    handle_font = _font(42, bold=True)
    y = 124
    for line in ("SUIVRE LA", "POLITIQUE", "SANS SE PERDRE"):
        draw.text((MARGIN, y), line, fill=TEXT, font=title_font)
        y += 72
    draw.rounded_rectangle((MARGIN, y + 8, MARGIN + 430, y + 16), radius=4, fill=VOTE_COLORS["pour"])
    y += 84
    y = _draw_wrapped(
        draw,
        (MARGIN, y),
        "Abonnez-vous pour suivre les votes clés à l'Assemblée nationale.",
        body_font,
        TEXT,
        SIZE - 2 * MARGIN,
        42,
        3,
    )
    y += 54
    y = _draw_wrapped(
        draw,
        (MARGIN, y),
        "Le projet est indépendant, sourcé et construit pour rendre la politique plus lisible.",
        body_font,
        TEXT,
        SIZE - 2 * MARGIN,
        42,
        4,
    )
    draw.text((MARGIN, 760), "@lescrutin", fill=VOTE_COLORS["pour"], font=handle_font)
    draw.text((MARGIN, 828), "Partager · commenter · soutenir", fill=TEXT, font=body_font)
    _draw_footer(draw, slide_number, total_slides)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    img.save(output)


def build_weekly_caption(start: date, end: date, scrutins: list[dict[str, Any]]) -> str:
    lines = [
        f"Cette semaine à l'Assemblée · {_week_label(start, end)}",
        "",
        "Au programme :",
    ]
    for scrutin in scrutins:
        totals = scrutin["totals"]
        lines.append(
            f"- {stage_label(scrutin.get('stage_id'))} · {editorial_title(scrutin)} "
            f"({totals['pour']} pour / {totals['contre']} contre / {totals['abstention']} abst.)"
        )
    lines.extend(
        [
            "",
            "Un vote clé ne signifie pas toujours que la loi est définitivement adoptée : l'étape est indiquée sur chaque slide.",
            "",
            "Sources : Assemblée nationale et sources publiques indiquées dans le projet",
            "@lescrutin",
            "#AssembleeNationale #Politique #France #Datajournalisme #Parlement",
        ]
    )
    return "\n".join(lines)


def create_weekly_carousel(
    zip_bytes: bytes,
    config_path: str | Path = "groupes_politiques.json",
    output_dir: str | Path = "outputs/weekly",
    copy_dir: str | Path = "weekly_copy",
    start_date: str | None = None,
    end_date: str | None = None,
    max_vote_slides: int = 7,
) -> Path:
    start, end, scrutins = load_weekly_scrutins_from_zip(zip_bytes, config_path, start_date, end_date)
    if not scrutins:
        raise ValueError("Aucun vote clé pour cette semaine.")
    scrutins = scrutins[:max_vote_slides]
    total_slides = len(scrutins) + 3
    week = _week_id(start)
    out_dir = Path(output_dir) / week
    out_dir.mkdir(parents=True, exist_ok=True)
    copy_path, copy, missing_copy = load_or_create_weekly_copy(copy_dir, start, end, scrutins)
    descriptions = descriptions_by_numero(copy)

    slides: list[dict[str, Any]] = []
    cover = out_dir / "slide-01-cover.png"
    draw_cover(cover, start, end, total_slides)
    slides.append({"kind": "cover", "path": cover.as_posix()})
    for index, scrutin in enumerate(scrutins, start=2):
        path = out_dir / f"slide-{index:02d}-scrutin-{scrutin['numero']}.png"
        description = descriptions.get(int(scrutin["numero"]), "")
        draw_vote_slide(scrutin, path, index, total_slides, description)
        slides.append(
            {
                "kind": "vote",
                "numero": scrutin["numero"],
                "uid": scrutin["uid"],
                "path": path.as_posix(),
                "description": description,
            }
        )
    definitions_path = out_dir / f"slide-{total_slides - 1:02d}-definitions.png"
    draw_definitions(definitions_path, total_slides - 1, total_slides)
    slides.append({"kind": "definitions", "path": definitions_path.as_posix()})
    cta_path = out_dir / f"slide-{total_slides:02d}-subscribe.png"
    draw_cta(cta_path, total_slides, total_slides)
    slides.append({"kind": "cta", "path": cta_path.as_posix()})

    draft = {
        "status": "approved_by_human" if not missing_copy else "needs_human_copy",
        "approval_mode": "manual_weekly_copy",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "week_id": week,
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "copy_path": copy_path.as_posix(),
        "missing_copy": missing_copy,
        "caption": build_weekly_caption(start, end, scrutins),
        "slides": slides,
        "scrutins": [
            {
                "uid": scrutin["uid"],
                "numero": scrutin["numero"],
                "date": scrutin["date"],
                "title": editorial_title(scrutin),
                "description": descriptions.get(int(scrutin["numero"]), ""),
                "description_sources": next(
                    (
                        item.get("description_sources", [])
                        for item in copy.get("items", [])
                        if int(item.get("numero", 0)) == int(scrutin["numero"])
                    ),
                    [],
                ),
                "stage_id": scrutin.get("stage_id"),
                "stage_label": stage_label(scrutin.get("stage_id")),
                "source_url": scrutin["source_url"],
                "totals": scrutin["totals"],
            }
            for scrutin in scrutins
        ],
    }
    draft_path = out_dir / f"draft-{week}.json"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return draft_path
