from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from assemblee_votes.draft import create_draft
from assemblee_votes.fetch import (
    SCRUTINS_JSON_ZIP_URL,
    _download_bytes,
    load_published,
    select_scrutins_from_zip,
)
from assemblee_votes.stage import stage_draft


AUTO_PUBLISH_SINCE_DATE = os.getenv("AUTO_PUBLISH_SINCE_DATE", "2026-07-28")


def _approve_automatically(path: str | Path) -> None:
    draft_path = Path(path)
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    if draft.get("status") != "awaiting_human_approval":
        raise SystemExit(f"Statut inattendu: {draft.get('status')}")
    draft["status"] = "approved_by_human"
    draft["approved_at"] = datetime.now(timezone.utc).isoformat()
    draft["approval_mode"] = "automatic"
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_github_outputs(values: dict[str, str]) -> None:
    output_path = os.getenv("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare automatiquement le prochain post Instagram.")
    parser.add_argument("--url", default=SCRUTINS_JSON_ZIP_URL)
    parser.add_argument("--config", default="groupes_politiques.json")
    parser.add_argument("--published", default="published.json")
    parser.add_argument(
        "--since-date",
        default=AUTO_PUBLISH_SINCE_DATE,
        help="Ignore les scrutins anterieurs a cette date YYYY-MM-DD.",
    )
    parser.add_argument("--output", default="work/latest_scrutins.json")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--public-dir", default="public")
    parser.add_argument(
        "--public-base-url",
        default=os.getenv("PUBLIC_BASE_URL", "https://brnjean.github.io/lescrutin"),
    )
    parser.add_argument(
        "--publish-image-base-url",
        default=os.getenv(
            "PUBLISH_IMAGE_BASE_URL",
            "https://raw.githubusercontent.com/brnjean/lescrutin/main/public",
        ),
    )
    args = parser.parse_args()

    selected = select_scrutins_from_zip(
        _download_bytes(args.url),
        args.config,
        load_published(args.published),
        limit=1,
        since_date=args.since_date,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps([asdict(scrutin) for scrutin in selected], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if not selected:
        print(
            "Aucun nouveau scrutin en lecture définitive à publier "
            f"depuis le {args.since_date}."
        )
        _write_github_outputs({"has_post": "false"})
        return

    draft_path = create_draft(asdict(selected[0]), args.output_dir, args.config)
    _approve_automatically(draft_path)
    asset = stage_draft(draft_path, args.public_dir, args.public_base_url)
    image_url = f"{args.publish_image_base_url.rstrip('/')}/{asset.public_path}"

    print(f"Post automatique préparé pour le scrutin n°{asset.numero}.")
    print(f"Draft: {draft_path}")
    print(f"Image de publication: {image_url}")
    _write_github_outputs(
        {
            "has_post": "true",
            "numero": str(asset.numero),
            "draft_path": str(draft_path),
            "image_url": image_url,
        }
    )


if __name__ == "__main__":
    main()
