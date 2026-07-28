from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from assemblee_votes.europe_monthly import create_europe_monthly_carousel
from stage_weekly_carousel import main as stage_main


def _write_github_outputs(values: dict[str, str]) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")


def _load_published(path: str | Path) -> dict:
    published_path = Path(path)
    if not published_path.exists():
        return {}
    return json.loads(published_path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare automatiquement le carrousel Europe mensuel.")
    parser.add_argument("--published", default="published.json")
    parser.add_argument("--output-dir", default="outputs/europe-monthly")
    parser.add_argument("--copy-dir", default="europe_copy")
    parser.add_argument("--public-dir", default="public")
    parser.add_argument("--public-base-url", default=os.getenv("PUBLIC_BASE_URL", "https://brnjean.github.io/lescrutin"))
    parser.add_argument("--start-date", default=os.getenv("EUROPE_MONTH_START_DATE"))
    parser.add_argument("--end-date", default=os.getenv("EUROPE_MONTH_END_DATE"))
    parser.add_argument("--max-vote-slides", type=int, default=7)
    args = parser.parse_args()

    draft_path = create_europe_monthly_carousel(
        output_dir=args.output_dir,
        copy_dir=args.copy_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        max_vote_slides=args.max_vote_slides,
    )
    draft = json.loads(Path(draft_path).read_text(encoding="utf-8"))
    carousel_id = draft["carousel_id"]
    if draft.get("missing_copy"):
        print(
            "Carrousel Europe non publiable: syntheses manquantes pour les votes "
            + ", ".join(str(numero) for numero in draft["missing_copy"])
        )
        _write_github_outputs({"has_carousel": "false"})
        return

    published = _load_published(args.published)
    if carousel_id in published.get("europe_monthly_carousels", {}):
        print(f"Carrousel Europe deja publie: {carousel_id}")
        _write_github_outputs({"has_carousel": "false"})
        return

    import sys

    old_argv = sys.argv
    try:
        sys.argv = [
            "stage_weekly_carousel.py",
            "--draft",
            str(draft_path),
            "--public-dir",
            args.public_dir,
            "--public-base-url",
            args.public_base_url,
        ]
        stage_main()
    finally:
        sys.argv = old_argv

    print(f"Carrousel Europe prepare: {draft_path}")
    _write_github_outputs(
        {
            "has_carousel": "true",
            "carousel_id": carousel_id,
            "draft_path": str(draft_path),
        }
    )


if __name__ == "__main__":
    main()
