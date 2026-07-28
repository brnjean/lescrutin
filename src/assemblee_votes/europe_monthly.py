from __future__ import annotations

import calendar
import html
import json
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

SIZE = 1080
MARGIN = 72
PAPER = "#F2EBDF"
GRID = "#E3D9CA"
TEXT = "#111111"
EU_BLUE = "#164A7A"
EU_GOLD = "#D6A400"
FOR = "#164A7A"
AGAINST = "#D8D0C4"
ABSTENTION = "#8B6C4D"


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


def _paper() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (SIZE, SIZE), PAPER)
    draw = ImageDraw.Draw(img)
    for x in range(0, SIZE, 36):
        draw.line([(x, 0), (x, SIZE)], fill=GRID, width=1)
    for y in range(0, SIZE, 36):
        draw.line([(0, y), (SIZE, y)], fill=GRID, width=1)
    return img, draw


def _footer(draw: ImageDraw.ImageDraw, slide_number: int, total: int, dark: bool = False) -> None:
    fill = PAPER if dark else TEXT
    font = _font(20, bold=True)
    draw.text((MARGIN, SIZE - 58), "@lescrutin", fill=fill, font=font)
    page = f"{slide_number}/{total}"
    draw.text((SIZE - MARGIN - _text_width(draw, page, font), SIZE - 58), page, fill=fill, font=font)


def draw_cover(output: str | Path, start: date, end: date, vote_count: int, total_slides: int) -> None:
    img = Image.new("RGB", (SIZE, SIZE), EU_BLUE)
    draw = ImageDraw.Draw(img)
    for x in range(-SIZE, SIZE * 2, 64):
        draw.line([(x, 0), (x + SIZE, SIZE)], fill="#1E5F97", width=2)
    title = _font(76, bold=True)
    subtitle = _font(30)
    eyebrow = _font(26, bold=True)
    draw.text((MARGIN, 92), "LE MOIS EUROPÉEN", fill=EU_GOLD, font=eyebrow)
    y = 188
    for line in ("CE MOIS-CI", "AU PARLEMENT", "EUROPÉEN"):
        draw.text((MARGIN, y), line, fill="#FFFFFF", font=title)
        y += 84
    draw.rounded_rectangle((MARGIN, y + 14, MARGIN + 470, y + 24), radius=5, fill=EU_GOLD)
    y += 82
    _draw_wrapped(
        draw,
        (MARGIN, y),
        f"{_month_label(start)} · {vote_count} votes principaux",
        subtitle,
        "#FFFFFF",
        SIZE - 2 * MARGIN,
        40,
        2,
    )
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
    badge = _font(24, bold=True)
    title_font = _font(56, bold=True)
    body_font = _font(27)
    small = _font(23)
    stat = _font(30, bold=True)
    draw.rounded_rectangle((MARGIN, 72, MARGIN + 360, 118), radius=6, fill=EU_BLUE)
    draw.text((MARGIN + 18, 82), "PARLEMENT EUROPÉEN", fill="#FFFFFF", font=badge)
    draw.text((MARGIN, 144), f"Vote n°{vote.id} · {datetime.strptime(vote.date, '%Y-%m-%d').strftime('%d/%m/%Y')}", fill=TEXT, font=small)
    y = _draw_wrapped(draw, (MARGIN, 202), vote.title.upper(), title_font, TEXT, SIZE - 2 * MARGIN, 62, 3)
    draw.rounded_rectangle((MARGIN, y + 10, MARGIN + 390, y + 18), radius=4, fill=EU_GOLD)
    y += 60
    draw.text((MARGIN, y), vote.result, fill=TEXT, font=stat)
    y += 58
    totals = vote.totals
    total_votes = max(1, totals["pour"] + totals["contre"] + totals["abstention"])
    x = MARGIN
    bar_y = y + 20
    bar_w = SIZE - 2 * MARGIN
    for key, color in (("pour", FOR), ("contre", AGAINST), ("abstention", ABSTENTION)):
        width = int(bar_w * totals[key] / total_votes)
        draw.rectangle((x, bar_y, x + width, bar_y + 34), fill=color)
        x += width
    draw.rectangle((MARGIN, bar_y, MARGIN + bar_w, bar_y + 34), outline=TEXT, width=2)
    y = bar_y + 66
    draw.text((MARGIN, y), f"{totals['pour']} pour / {totals['contre']} contre / {totals['abstention']} abst.", fill=TEXT, font=stat)
    y += 58
    pour, contre, abst = _group_majorities(vote)
    group_line = f"Majorités groupes · Pour : {', '.join(pour[:5]) or '-'} / Contre : {', '.join(contre[:4]) or '-'}"
    y = _draw_wrapped(draw, (MARGIN, y), group_line, small, "#5E5144", SIZE - 2 * MARGIN, 31, 2)
    y += 32
    _draw_wrapped(draw, (MARGIN, y), vote.description, body_font, TEXT, SIZE - 2 * MARGIN, 34, 6)
    source = "Sources : Parlement européen / HowTheyVote"
    draw.text((MARGIN, SIZE - 104), source, fill="#5E5144", font=small)
    _footer(draw, slide_number, total_slides)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    img.save(output)


def draw_definitions(output: str | Path, slide_number: int, total_slides: int) -> None:
    img, draw = _paper()
    title = _font(62, bold=True)
    heading = _font(29, bold=True)
    body = _font(26)
    draw.text((MARGIN, 80), "COMPRENDRE", fill=TEXT, font=title)
    draw.text((MARGIN, 146), "L'EUROPE", fill=TEXT, font=title)
    draw.rounded_rectangle((MARGIN, 224, MARGIN + 420, 232), radius=4, fill=EU_GOLD)
    y = 292
    items = [
        ("Règlement", "Texte applicable directement dans les États membres une fois adopté."),
        ("Directive", "Objectif commun européen que chaque État doit transposer dans son droit national."),
        ("Résolution", "Position politique du Parlement européen. Elle peut peser, sans être toujours une loi."),
        ("Trilogues", "Négociations entre Parlement, Conseil et Commission pour parvenir à un texte commun."),
    ]
    for h, b in items:
        draw.text((MARGIN, y), h.upper(), fill=TEXT, font=heading)
        y += 38
        y = _draw_wrapped(draw, (MARGIN, y), b, body, TEXT, SIZE - 2 * MARGIN, 32, 2)
        y += 34
    _footer(draw, slide_number, total_slides)
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    img.save(output)


def draw_cta(output: str | Path, slide_number: int, total_slides: int) -> None:
    img, draw = _paper()
    title = _font(64, bold=True)
    body = _font(31)
    y = 126
    for line in ("SUIVRE", "CE QUI SE VOTE", "SANS SE PERDRE"):
        draw.text((MARGIN, y), line, fill=TEXT, font=title)
        y += 72
    draw.rounded_rectangle((MARGIN, y + 8, MARGIN + 430, y + 16), radius=4, fill=EU_GOLD)
    y += 84
    y = _draw_wrapped(draw, (MARGIN, y), "Chaque mois, un résumé sourcé des votes importants au Parlement européen.", body, TEXT, SIZE - 2 * MARGIN, 42, 4)
    y += 54
    _draw_wrapped(draw, (MARGIN, y), "Projet bénévole, neutre et automatisé. Abonnez-vous pour le soutenir.", body, TEXT, SIZE - 2 * MARGIN, 42, 4)
    draw.text((MARGIN, 790), "@lescrutin", fill=EU_BLUE, font=_font(42, bold=True))
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
