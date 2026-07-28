from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from assemblee_votes.fetch import SCRUTINS_JSON_ZIP_URL, _download_bytes
from assemblee_votes.weekly import create_weekly_carousel
from stage_weekly_carousel import main as stage_main


WEEKLY_AUTO_SINCE_DATE = os.getenv("WEEKLY_AUTO_SINCE_DATE", "2026-07-20")


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
    parser = argparse.ArgumentParser(description="Prepare automatiquement le carrousel hebdomadaire.")
    parser.add_argument("--url", default=SCRUTINS_JSON_ZIP_URL)
    parser.add_argument("--config", default="groupes_politiques.json")
    parser.add_argument("--published", default="published.json")
    parser.add_argument("--output-dir", default="outputs/weekly")
    parser.add_argument("--copy-dir", default="weekly_copy")
    parser.add_argument("--public-dir", default="public")
    parser.add_argument("--public-base-url", default=os.getenv("PUBLIC_BASE_URL", "https://brnjean.github.io/lescrutin"))
    parser.add_argument("--start-date", default=os.getenv("WEEKLY_START_DATE"))
    parser.add_argument("--end-date", default=os.getenv("WEEKLY_END_DATE"))
    parser.add_argument("--max-vote-slides", type=int, default=7)
    args = parser.parse_args()

    draft_path = create_weekly_carousel(
        _download_bytes(args.url),
        config_path=args.config,
        output_dir=args.output_dir,
        copy_dir=args.copy_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        max_vote_slides=args.max_vote_slides,
    )
    draft = json.loads(Path(draft_path).read_text(encoding="utf-8"))
    if draft["week_start"] < WEEKLY_AUTO_SINCE_DATE:
        print(f"Semaine ignoree avant la date de depart: {draft['week_id']}")
        _write_github_outputs({"has_carousel": "false"})
        return

    published = _load_published(args.published)
    if draft["week_id"] in published.get("weekly_carousels", {}):
        print(f"Carrousel deja publie: {draft['week_id']}")
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

    print(f"Carrousel hebdomadaire prepare: {draft_path}")
    _write_github_outputs(
        {
            "has_carousel": "true",
            "week_id": draft["week_id"],
            "draft_path": str(draft_path),
        }
    )


if __name__ == "__main__":
    main()
