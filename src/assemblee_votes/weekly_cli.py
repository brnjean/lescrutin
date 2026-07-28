from __future__ import annotations

import argparse

from .fetch import SCRUTINS_JSON_ZIP_URL, _download_bytes
from .weekly import create_weekly_carousel


def main() -> None:
    parser = argparse.ArgumentParser(description="Genere un carrousel hebdomadaire Instagram.")
    parser.add_argument("--url", default=SCRUTINS_JSON_ZIP_URL)
    parser.add_argument("--config", default="groupes_politiques.json")
    parser.add_argument("--output-dir", default="outputs/weekly")
    parser.add_argument("--start-date", help="Debut de semaine force, format YYYY-MM-DD.")
    parser.add_argument("--end-date", help="Fin de semaine forcee, format YYYY-MM-DD.")
    parser.add_argument("--max-vote-slides", type=int, default=7)
    args = parser.parse_args()

    draft_path = create_weekly_carousel(
        _download_bytes(args.url),
        config_path=args.config,
        output_dir=args.output_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        max_vote_slides=args.max_vote_slides,
    )
    print(f"Carrousel hebdomadaire cree: {draft_path}")


if __name__ == "__main__":
    main()
