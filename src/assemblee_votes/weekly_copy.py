from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from .stages import stage_label
from .titles import editorial_title


COPY_INSTRUCTIONS = (
    "Remplis chaque champ description en 2-3 lignes simples. "
    "Explique concretement ce que fait le texte. "
    "Ne repete pas l'etape du vote: elle est deja expliquee dans le carrousel."
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
    existing: dict[str, Any] = {}
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    descriptions = _existing_descriptions(existing)

    items = []
    missing: list[int] = []
    for scrutin in scrutins:
        numero = int(scrutin["numero"])
        description = descriptions.get(numero, "")
        if not description:
            missing.append(numero)
        items.append(
            {
                "numero": numero,
                "date": scrutin["date"],
                "title": editorial_title(scrutin),
                "stage_label": stage_label(scrutin.get("stage_id")),
                "source_url": scrutin["source_url"],
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
