from __future__ import annotations

import argparse

from .europe_monthly import create_europe_monthly_carousel


def main() -> None:
    parser = argparse.ArgumentParser(description="Genere un carrousel mensuel Europe Instagram.")
    parser.add_argument("--output-dir", default="outputs/europe-monthly")
    parser.add_argument("--copy-dir", default="europe_copy")
    parser.add_argument("--start-date", help="Debut du mois force, format YYYY-MM-DD.")
    parser.add_argument("--end-date", help="Fin du mois forcee, format YYYY-MM-DD.")
    parser.add_argument("--max-vote-slides", type=int, default=7)
    args = parser.parse_args()

    draft_path = create_europe_monthly_carousel(
        output_dir=args.output_dir,
        copy_dir=args.copy_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        max_vote_slides=args.max_vote_slides,
    )
    print(f"Carrousel Europe mensuel cree: {draft_path}")


if __name__ == "__main__":
    main()
