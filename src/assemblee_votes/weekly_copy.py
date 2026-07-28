from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .programmescandidats import fetch_scrutin_explanation
from .stages import stage_label
from .titles import editorial_title


COPY_INSTRUCTIONS = (
    "Descriptions recuperees automatiquement depuis programmescandidats.fr. "
    "Ne pas modifier ce fichier pour le flux automatique."
)


def weekly_copy_path(copy_dir: str | Path, week_start: date) -> Path:
    return Path(copy_dir) / f"week-{week_start.isoformat()}.json"


def _existing_descriptions(copy: dict[str, Any]) -> dict[int, str]:
    descriptions: dict[int, str] = {}
    for item in copy.get("items", []):
        try:
            numero = int(item["numero"])
        except (KeyError, TypeError, ValueError):
            continue
        description = str(item.get("description") or "").strip()
        if description:
            descriptions[numero] = description
    return descriptions


def load_or_create_weekly_copy(
    copy_dir: str | Path,
    week_start: date,
    week_end: date,
    scrutins: list[dict[str, Any]],
) -> tuple[Path, dict[str, Any], list[int]]:
    path = weekly_copy_path(copy_dir, week_start)
    items = []
    missing: list[int] = []
    for scrutin in scrutins:
        numero = int(scrutin["numero"])
        explanation = fetch_scrutin_explanation(numero)
        description = explanation.description if explanation else ""
        if not description:
            missing.append(numero)
        items.append(
            {
                "numero": numero,
                "date": scrutin["date"],
                "title": editorial_title(scrutin),
                "stage_label": stage_label(scrutin.get("stage_id")),
                "source_url": scrutin["source_url"],
                "description_source": explanation.url if explanation else "",
                "description": description,
            }
        )

    copy = {
        "week_id": f"week-{week_start.isoformat()}",
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "instructions": COPY_INSTRUCTIONS,
        "items": items,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(copy, ensure_ascii=False, indent=2), encoding="utf-8")
    return path, copy, missing


def descriptions_by_numero(copy: dict[str, Any]) -> dict[int, str]:
    return _existing_descriptions(copy)
