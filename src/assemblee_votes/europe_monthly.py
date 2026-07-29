from __future__ import annotations

import calendar
import html
import json
import math
import os
import re
import textwrap
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


HOWTHEYVOTE_API = "https://howtheyvote.eu/api"
EP_OPEN_DATA_API = "https://data.europarl.europa.eu/api/v2"
OPENAI_URL = "https://api.openai.com/v1/responses"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

WIDTH = 1080
HEIGHT = 1350
SIZE = WIDTH
MARGIN = 72
PAPER = "#F2EBDF"
GRID = "#E3D9CA"
TEXT = "#111111"
EU_BLUE = "#073B7A"
EU_BLUE_2 = "#0E5AA3"
EU_GOLD = "#F2C230"
FOR = "#073B7A"
AGAINST = "#D9D0C2"
ABSTENTION = "#A87937"


@dataclass(frozen=True)
class EuropeVote:
    id: str
    date: str
    title: str
    raw_title: str
    result: str
    description: str
    vote_type: str
    reference: str
    procedure_reference: str
    procedure_stage: str
    topics: list[str]
    committees: list[str]
    totals: dict[str, int]
    group_votes: list[dict[str, Any]]
    sources: list[dict[str, str]]
    source_url: str


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return " ".join(self.parts)


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


def _request_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "lescrutin/1.0 (+https://brnjean.github.io/lescrutin)",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _plain_html(value: str | None) -> str:
    if not value:
        return ""
    parser = _HTMLText()
    parser.feed(value)
    return html.unescape(parser.text()).strip()


def _month_bounds(day: date) -> tuple[date, date]:
    start = day.replace(day=1)
    end = day.replace(day=calendar.monthrange(day.year, day.month)[1])
    return start, end


def _month_id(start: date) -> str:
    return f"europe-{start.strftime('%Y-%m')}"


def _month_label(start: date) -> str:
    months = [
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ]
    return f"{months[start.month - 1]} {start.year}"


def _fetch_vote_list(start: date, end: date) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "date[gte]": start.isoformat(),
            "date[lte]": end.isoformat(),
            "sort_by": "date",
            "sort_order": "desc",
            "page_size": "100",
        }
    )
    data = _request_json(f"{HOWTHEYVOTE_API}/votes?{params}")
    return list(data.get("results", []))


def _fetch_vote_detail(vote_id: str) -> dict[str, Any]:
    return _request_json(f"{HOWTHEYVOTE_API}/votes/{vote_id}")


def _ep_vote_results_url(vote: dict[str, Any]) -> str:
    day = vote["timestamp"][:10]
    meeting_id = f"MTG-PL-{day}"
    return f"{EP_OPEN_DATA_API}/meetings/{meeting_id}/vote-results"


def _text_from_response(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"].strip()
    parts: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def _openai_json(prompt: str) -> dict[str, str] | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    payload = {
        "model": OPENAI_MODEL,
        "input": prompt,
        "max_output_tokens": 500,
    }
    req = urllib.request.Request(
        OPENAI_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            raw = json.loads(response.read().decode("utf-8"))
        text = _text_from_response(raw)
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return None
        data = json.loads(match.group(0))
    except Exception as exc:
        print(f"Synthese OpenAI Europe indisponible: {exc}", flush=True)
        return None
    if not isinstance(data.get("title"), str) or not isinstance(data.get("description"), str):
        return None
    return {
        "title": " ".join(data["title"].split())[:90],
        "description": " ".join(data["description"].split())[:430],
    }


def _summarize_vote(detail: dict[str, Any]) -> tuple[str, str, bool]:
    snippet = _plain_html((detail.get("snippet") or {}).get("text"))
    topics = ", ".join(topic.get("label", "") for topic in detail.get("topics", []) if topic.get("label"))
    committees = ", ".join(item.get("abbreviation", "") for item in detail.get("responsible_committees", []) if item.get("abbreviation"))
    sources = "\n".join(f"- {item.get('name')}: {item.get('url')}" for item in detail.get("sources", []))
    prompt = f"""
Tu rédiges pour un compte Instagram neutre qui explique les votes du Parlement européen.
À partir des sources ci-dessous, produis un JSON strict avec deux champs:
"title": titre français court, concret, sans jugement, 55 caractères maximum.
"description": 3 phrases maximum en français, neutres, qui expliquent ce qui est voté, les enjeux et le statut institutionnel si visible.
Ne parle pas du score du vote. Ne donne aucun avis politique.

Titre source: {detail.get('display_title')}
Type de vote: {detail.get('description')}
Résultat: {detail.get('result')}
Procédure: {detail.get('procedure')}
Thèmes: {topics}
Commissions: {committees}
Résumé/source: {snippet}
Sources:
{sources}
""".strip()
    generated = _openai_json(prompt)
    if generated:
        return generated["title"], generated["description"], True
    return detail.get("display_title", "Vote européen")[:80], "", False


def _result_word(value: str) -> str:
    if value == "ADOPTED":
        return "Adopté"
    if value == "REJECTED":
        return "Rejeté"
    return value.title() if value else "Vote"


def _score_vote(vote: dict[str, Any]) -> tuple[int, str]:
    score = 0
    if vote.get("is_main"):
        score += 50
    description = (vote.get("description") or "").lower()
    if "ensemble" in description or "final" in description or "interinstitutionnelles" in description:
        score += 20
    if vote.get("result") in {"ADOPTED", "REJECTED"}:
        score += 10
    if vote.get("topics"):
        score += 5
    return score, str(vote.get("timestamp", ""))


def _select_votes(votes: list[dict[str, Any]], max_votes: int) -> list[dict[str, Any]]:
    candidates = [
        vote
        for vote in votes
        if vote.get("is_main")
        and vote.get("result") in {"ADOPTED", "REJECTED"}
        and not vote.get("amendment_number")
    ]
    return sorted(candidates, key=_score_vote, reverse=True)[:max_votes]


def _has_official_ep_source(detail: dict[str, Any]) -> bool:
    for source in detail.get("sources", []):
        url = str(source.get("url") or "")
        if "europarl.europa.eu" in url:
            return True
    return False


def _manual_copy_by_id(copy_path: Path) -> dict[str, dict[str, str]]:
    if not copy_path.exists():
        return {}
    data = json.loads(copy_path.read_text(encoding="utf-8"))
    copy: dict[str, dict[str, str]] = {}
    for item in data.get("items", []):
        vote_id = str(item.get("id") or item.get("numero") or "").strip()
        description = " ".join(str(item.get("description") or "").split())
        if vote_id and description:
            copy[vote_id] = {
                "title": " ".join(str(item.get("title") or "").split()),
                "description": description,
            }
    return copy


def load_monthly_europe_votes(
    start: date,
    end: date,
    max_votes: int = 7,
    manual_copy: dict[str, dict[str, str]] | None = None,
) -> list[EuropeVote]:
    selected = _select_votes(_fetch_vote_list(start, end), max_votes)
    votes: list[EuropeVote] = []
    for item in selected:
        detail = _fetch_vote_detail(str(item["id"]))
        if not _has_official_ep_source(detail):
            print(f"Vote Europe ignore sans source officielle Parlement europeen: {item['id']}", flush=True)
            continue
        override = (manual_copy or {}).get(str(detail["id"]), {})
        if override.get("description"):
            title = override.get("title") or detail.get("display_title", "Vote européen")
            description = override["description"]
            has_summary = True
        else:
            title, description, has_summary = _summarize_vote(detail)
        stats = detail.get("stats") or {}
        totals = stats.get("total") or {}
        source_list = list(detail.get("sources", []))
        source_list.insert(
            0,
            {
                "name": "European Parliament Open Data vote results",
                "url": _ep_vote_results_url(detail),
            },
        )
        votes.append(
            EuropeVote(
                id=str(detail["id"]),
                date=str(detail["timestamp"])[:10],
                title=title,
                raw_title=detail.get("display_title", ""),
                result=_result_word(detail.get("result", "")),
                description=description if has_summary else "",
                vote_type=detail.get("description") or "",
                reference=detail.get("reference") or "",
                procedure_reference=(detail.get("procedure") or {}).get("reference") or "",
                procedure_stage=(detail.get("procedure") or {}).get("stage") or "",
                topics=[topic.get("label", "") for topic in detail.get("topics", []) if topic.get("label")],
                committees=[
                    item.get("abbreviation", "")
                    for item in detail.get("responsible_committees", [])
                    if item.get("abbreviation")
                ],
                totals={
                    "pour": int(totals.get("FOR") or 0),
                    "contre": int(totals.get("AGAINST") or 0),
                    "abstention": int(totals.get("ABSTENTION") or 0),
                    "non_votant": int(totals.get("DID_NOT_VOTE") or 0),
                },
                group_votes=list((stats.get("by_group") or [])),
                sources=source_list,
                source_url=f"https://howtheyvote.eu/votes/{detail['id']}",
            )
        )
    return votes


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


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


def _fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int, min_size: int, bold: bool = True) -> ImageFont.ImageFont:
    for size in range(start_size, min_size - 1, -2):
        font = _font(size, bold=bold)
        if _text_width(draw, text, font) <= max_width:
            return font
    return _font(min_size, bold=bold)


def _sentence_limit(text: str, max_words: int = 40, max_sentences: int = 2) -> str:
    clean = " ".join(text.split())
    if not clean:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", clean)
    selected = " ".join(sentence for sentence in sentences[:max_sentences] if sentence)
    words = selected.split()
    if len(words) > max_words:
        selected = " ".join(words[:max_words]).rstrip(" ,;:") + "..."
    return selected


def _paper() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    draw = ImageDraw.Draw(img)
    for x in range(0, WIDTH, 36):
        draw.line([(x, 0), (x, HEIGHT)], fill=GRID, width=1)
    for y in range(0, HEIGHT, 36):
        draw.line([(0, y), (WIDTH, y)], fill=GRID, width=1)
    return img, draw


def _footer(draw: ImageDraw.ImageDraw, slide_number: int, total: int, dark: bool = False) -> None:
    fill = PAPER if dark else TEXT
    font = _font(20, bold=True)
    draw.text((MARGIN, HEIGHT - 64), "@lescrutin", fill=fill, font=font)
    page = f"{slide_number}/{total}"
    draw.text((WIDTH - MARGIN - _text_width(draw, page, font), HEIGHT - 64), page, fill=fill, font=font)


def draw_cover(output: str | Path, start: date, end: date, vote_count: int, total_slides: int) -> None:
    img = Image.new("RGB", (WIDTH, HEIGHT), EU_BLUE)
    draw = ImageDraw.Draw(img)
    for x in range(-HEIGHT, WIDTH * 2, 58):
        draw.line([(x, 0), (x + HEIGHT, HEIGHT)], fill="#124D8E", width=2)
    for y in range(92, HEIGHT - 160, 92):
        draw.line((MARGIN, y, WIDTH - MARGIN, y), fill="#0B4482", width=1)
    for i in range(12):
        angle = i * 30
        cx = WIDTH - 232 + int(120 * math.cos(math.radians(angle)))
        cy = 228 + int(120 * math.sin(math.radians(angle)))
        draw.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=EU_GOLD)
    draw.rectangle((0, 0, WIDTH, 16), fill=EU_GOLD)
    eyebrow = _font(25, bold=True)
    title = _font(76, bold=True)
    subtitle = _font(33)
    sentence = _font(39, bold=True)
    draw.text((MARGIN, 104), "LE SCRUTIN · EUROPE", fill=EU_GOLD, font=eyebrow)
    y = 246
    for line in ("Ce mois-ci", "au Parlement", "européen"):
        draw.text((MARGIN, y), line, fill="#FFFFFF", font=title)
        y += 88
    draw.rounded_rectangle((MARGIN, y + 16, MARGIN + 610, y + 26), radius=5, fill=EU_GOLD)
    y += 94
    draw.text((MARGIN, y), f"Les votes à retenir · {_month_label(start)}", fill="#FFFFFF", font=subtitle)
    y += 82
    _draw_wrapped(draw, (MARGIN, y), "Ce que l'Europe a décidé, soutenu ou rejeté.", sentence, "#FFFFFF", WIDTH - 2 * MARGIN, 48, 2)
    draw.rounded_rectangle((MARGIN, HEIGHT - 210, WIDTH - MARGIN, HEIGHT - 134), radius=10, outline=EU_GOLD, width=3)
    draw.text((MARGIN + 28, HEIGHT - 190), f"{vote_count} votes européens sélectionnés", fill="#FFFFFF", font=_font(29, bold=True))
    _footer(draw, 1, total_slides, dark=True)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    img.save(output)


def _group_majorities(vote: EuropeVote) -> tuple[list[str], list[str], list[str]]:
    buckets = {"pour": [], "contre": [], "abstention": []}
    for group in vote.group_votes:
        stats = group.get("stats") or {}
        label = ((group.get("group") or {}).get("short_label") or "").strip()
        if label in {"NI", "Non-attached"}:
            label = "non-inscrits"
        values = {
            "pour": int(stats.get("FOR") or 0),
            "contre": int(stats.get("AGAINST") or 0),
            "abstention": int(stats.get("ABSTENTION") or 0),
        }
        key = max(values, key=values.get)
        if values[key] > 0 and label:
            buckets[key].append(label)
    return buckets["pour"], buckets["contre"], buckets["abstention"]


def draw_vote_slide(vote: EuropeVote, output: str | Path, slide_number: int, total_slides: int) -> None:
    img, draw = _paper()
    draw.rectangle((0, 0, WIDTH, 14), fill=EU_BLUE)
    draw.rectangle((0, 14, WIDTH, 20), fill=EU_GOLD)
    badge = _font(22, bold=True)
    title_font = _font(55, bold=True)
    context_font = _font(23)
    body_font = _font(26)
    small = _font(22)
    stat = _font(35, bold=True)
    draw.rounded_rectangle((MARGIN, 66, MARGIN + 300, 110), radius=6, fill=EU_BLUE)
    draw.text((MARGIN + 18, 76), "Parlement européen", fill="#FFFFFF", font=badge)
    date_label = datetime.strptime(vote.date, "%Y-%m-%d").strftime("%d/%m/%Y")
    draw.text((MARGIN, 136), f"Vote n°{vote.id} · {date_label}", fill="#5E5144", font=small)
    y = _draw_wrapped(draw, (MARGIN, 188), vote.title, title_font, TEXT, WIDTH - 2 * MARGIN, 62, 3)
    y += 18
    status = vote.result.upper()
    status_font = _fit_font(draw, status, 260, 36, 28, bold=True)
    status_w = _text_width(draw, status, status_font) + 54
    draw.rounded_rectangle((MARGIN, y, MARGIN + status_w, y + 52), radius=8, fill=EU_GOLD, outline=TEXT, width=2)
    draw.text((MARGIN + 27, y + 9), status, fill=TEXT, font=status_font)
    context = "Ce vote fixe la position du Parlement, ce n'est pas encore une adoption définitive."
    _draw_wrapped(draw, (MARGIN + status_w + 28, y + 2), context, context_font, "#4D5660", WIDTH - 2 * MARGIN - status_w - 28, 30, 2)
    y += 104
    totals = vote.totals
    total_votes = max(1, totals["pour"] + totals["contre"] + totals["abstention"])
    x = MARGIN
    bar_y = y
    bar_w = WIDTH - 2 * MARGIN
    for key, color in (("pour", FOR), ("contre", AGAINST), ("abstention", ABSTENTION)):
        width = int(bar_w * totals[key] / total_votes)
        draw.rectangle((x, bar_y, x + width, bar_y + 52), fill=color)
        x += width
    draw.rectangle((MARGIN, bar_y, MARGIN + bar_w, bar_y + 52), outline=TEXT, width=2)
    legend_y = bar_y + 68
    legend_font = _font(20, bold=True)
    lx = MARGIN
    for key, label in (("pour", "POUR"), ("contre", "CONTRE"), ("abstention", "ABST.")):
        draw.rectangle((lx, legend_y + 5, lx + 22, legend_y + 27), fill={"pour": FOR, "contre": AGAINST, "abstention": ABSTENTION}[key], outline=TEXT, width=1)
        draw.text((lx + 32, legend_y), label, fill=TEXT, font=legend_font)
        lx += 156
    y = legend_y + 58
    score = f"{totals['pour']} pour · {totals['contre']} contre · {totals['abstention']} abst."
    draw.text((MARGIN, y), score, fill=TEXT, font=stat)
    y += 82
    pour, contre, abst = _group_majorities(vote)
    col_w = (WIDTH - 2 * MARGIN - 26) // 2
    box_h = 128
    draw.rounded_rectangle((MARGIN, y, MARGIN + col_w, y + box_h), radius=8, fill="#FFFFFF", outline=GRID, width=2)
    draw.rounded_rectangle((MARGIN + col_w + 26, y, WIDTH - MARGIN, y + box_h), radius=8, fill="#FFFFFF", outline=GRID, width=2)
    draw.text((MARGIN + 22, y + 18), "Majorité pour", fill=FOR, font=_font(22, bold=True))
    _draw_wrapped(draw, (MARGIN + 22, y + 54), ", ".join(pour[:4]) or "-", small, TEXT, col_w - 44, 28, 2)
    draw.text((MARGIN + col_w + 48, y + 18), "Majorité contre", fill="#6F5F4F", font=_font(22, bold=True))
    _draw_wrapped(draw, (MARGIN + col_w + 48, y + 54), ", ".join(contre[:4]) or "-", small, TEXT, col_w - 44, 28, 2)
    y += box_h + 52
    draw.text((MARGIN, y), "À retenir", fill=EU_BLUE, font=_font(25, bold=True))
    y += 38
    _draw_wrapped(draw, (MARGIN, y), _sentence_limit(vote.description), body_font, TEXT, WIDTH - 2 * MARGIN, 34, 4)
    source = "Sources : Parlement européen · OEIL · HowTheyVote"
    draw.text((MARGIN, HEIGHT - 118), source, fill="#5E5144", font=small)
    _footer(draw, slide_number, total_slides)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    img.save(output)


def draw_definitions(output: str | Path, slide_number: int, total_slides: int) -> None:
    img, draw = _paper()
    draw.rectangle((0, 0, WIDTH, 14), fill=EU_BLUE)
    draw.rectangle((0, 14, WIDTH, 20), fill=EU_GOLD)
    title = _font(65, bold=True)
    heading = _font(31, bold=True)
    body = _font(25)
    draw.text((MARGIN, 94), "Comprendre", fill=TEXT, font=title)
    draw.text((MARGIN, 166), "les mots de l'Europe", fill=EU_BLUE, font=title)
    draw.rounded_rectangle((MARGIN, 260, MARGIN + 510, 270), radius=4, fill=EU_GOLD)
    y = 336
    items = [
        ("Règlement", "Une règle européenne directement applicable dans les États membres."),
        ("Directive", "Un objectif commun que chaque État doit transposer dans son droit."),
        ("Résolution", "Une position politique du Parlement, pas toujours une loi."),
        ("Trilogue", "Une négociation entre Parlement, Conseil et Commission."),
    ]
    for h, b in items:
        draw.rounded_rectangle((MARGIN, y, WIDTH - MARGIN, y + 132), radius=8, fill="#FFFFFF", outline=GRID, width=2)
        draw.text((MARGIN + 26, y + 22), h, fill=EU_BLUE, font=heading)
        _draw_wrapped(draw, (MARGIN + 26, y + 66), b, body, TEXT, WIDTH - 2 * MARGIN - 52, 32, 1)
        y += 160
    _footer(draw, slide_number, total_slides)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    img.save(output)


def draw_cta(output: str | Path, slide_number: int, total_slides: int) -> None:
    img, draw = _paper()
    draw.rectangle((0, 0, WIDTH, 18), fill=EU_BLUE)
    title = _font(72, bold=True)
    body = _font(32)
    y = 138
    for line in ("Suivre", "ce qui se vote,", "sans se perdre."):
        draw.text((MARGIN, y), line, fill=TEXT if line != "sans se perdre." else EU_BLUE, font=title)
        y += 84
    draw.rounded_rectangle((MARGIN, y + 18, MARGIN + 540, y + 28), radius=4, fill=EU_GOLD)
    y += 108
    y = _draw_wrapped(draw, (MARGIN, y), "Projet bénévole, neutre et sourcé.", body, TEXT, WIDTH - 2 * MARGIN, 42, 2)
    y += 64
    _draw_wrapped(draw, (MARGIN, y), "Abonnez-vous pour suivre l'actualité politique française et européenne.", body, TEXT, WIDTH - 2 * MARGIN, 42, 3)
    draw.rounded_rectangle((MARGIN, HEIGHT - 248, WIDTH - MARGIN, HEIGHT - 152), radius=12, fill=EU_BLUE)
    draw.text((MARGIN + 34, HEIGHT - 222), "@lescrutin", fill="#FFFFFF", font=_font(40, bold=True))
    _footer(draw, slide_number, total_slides)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    img.save(output)


def build_caption(start: date, end: date, votes: list[EuropeVote]) -> str:
    lines = [
        f"Ce mois-ci au Parlement européen · {_month_label(start)}",
        "",
        "Au programme :",
    ]
    for vote in votes:
        lines.append(
            f"- {vote.result} · {vote.title} "
            f"({vote.totals['pour']} pour / {vote.totals['contre']} contre / {vote.totals['abstention']} abst.)"
        )
    lines.extend(
        [
            "",
            "Un vote du Parlement européen peut être une position politique, une étape de négociation ou une adoption en plénière. Le statut est indiqué sur chaque slide.",
            "",
            "Sources : Parlement européen, OEIL, résultats d'appel nominal, HowTheyVote",
            "@lescrutin",
            "#ParlementEuropeen #Europe #UnionEuropeenne #Politique #Datajournalisme",
        ]
    )
    return "\n".join(lines)


def create_europe_monthly_carousel(
    output_dir: str | Path = "outputs/europe-monthly",
    copy_dir: str | Path = "europe_copy",
    start_date: str | None = None,
    end_date: str | None = None,
    max_vote_slides: int = 7,
) -> Path:
    if start_date:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else _month_bounds(start)[1]
    else:
        start, end = _month_bounds(date.today())
    carousel_id = _month_id(start)
    copy_path = Path(copy_dir) / f"{carousel_id}.json"
    manual_copy = _manual_copy_by_id(copy_path)
    votes = load_monthly_europe_votes(start, end, max_votes=max_vote_slides, manual_copy=manual_copy)
    if not votes:
        raise ValueError("Aucun vote européen exploitable pour ce mois.")

    missing = [int(vote.id) for vote in votes if not vote.description.strip()]
    out_dir = Path(output_dir) / carousel_id
    out_dir.mkdir(parents=True, exist_ok=True)
    copy_path.parent.mkdir(parents=True, exist_ok=True)

    total_slides = len(votes) + 3
    slides: list[dict[str, Any]] = []
    cover = out_dir / "slide-01-cover.png"
    draw_cover(cover, start, end, len(votes), total_slides)
    slides.append({"kind": "cover", "path": cover.as_posix()})
    for index, vote in enumerate(votes, start=2):
        path = out_dir / f"slide-{index:02d}-europe-{vote.id}.png"
        draw_vote_slide(vote, path, index, total_slides)
        slides.append({"kind": "vote", "id": vote.id, "numero": int(vote.id), "path": path.as_posix(), "description": vote.description})
    definitions = out_dir / f"slide-{total_slides - 1:02d}-definitions.png"
    draw_definitions(definitions, total_slides - 1, total_slides)
    slides.append({"kind": "definitions", "path": definitions.as_posix()})
    cta = out_dir / f"slide-{total_slides:02d}-subscribe.png"
    draw_cta(cta, total_slides, total_slides)
    slides.append({"kind": "cta", "path": cta.as_posix()})

    trace = {
        "carousel_id": carousel_id,
        "month_start": start.isoformat(),
        "month_end": end.isoformat(),
        "instructions": "Trace des synthèses mensuelles Europe. Le flux automatique bloque si une description manque.",
        "items": [
            {
                "id": vote.id,
                "date": vote.date,
                "title": vote.title,
                "raw_title": vote.raw_title,
                "description": vote.description,
                "sources": vote.sources,
            }
            for vote in votes
        ],
    }
    copy_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")

    draft = {
        "status": "approved_by_human" if not missing else "needs_research",
        "approval_mode": "automatic_europe_monthly",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "carousel_id": carousel_id,
        "week_id": carousel_id,
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "manifest_key": "europe_monthly_carousels",
        "published_bucket": "europe_monthly_carousels",
        "copy_path": copy_path.as_posix(),
        "missing_copy": missing,
        "caption": build_caption(start, end, votes),
        "slides": slides,
        "scrutins": [
            {
                "id": vote.id,
                "numero": int(vote.id),
                "date": vote.date,
                "title": vote.title,
                "description": vote.description,
                "result": vote.result,
                "vote_type": vote.vote_type,
                "reference": vote.reference,
                "procedure_reference": vote.procedure_reference,
                "procedure_stage": vote.procedure_stage,
                "source_url": vote.source_url,
                "sources": vote.sources,
                "totals": vote.totals,
                "group_votes": vote.group_votes,
            }
            for vote in votes
        ],
    }
    draft_path = out_dir / f"draft-{carousel_id}.json"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return draft_path
