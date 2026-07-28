from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from publish_instagram import (
    GRAPH_BASE_URL,
    _clean_secret,
    _download_bytes,
    _post_json,
    publish_container,
    wait_until_container_ready,
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: str | Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def _load_draft(path: str | Path) -> dict[str, Any]:
    draft = json.loads(Path(path).read_text(encoding="utf-8"))
    if draft.get("status") != "approved_by_human":
        raise SystemExit("Publication bloquee: le carrousel doit etre approuve.")
    return draft


def _verify_public_slides(draft: dict[str, Any], attempts: int = 24, delay_seconds: int = 5) -> None:
    for slide in draft["slides"]:
        local_path = slide["path"]
        public_url = slide.get("public_url")
        if not public_url:
            raise SystemExit(f"URL publique manquante pour {local_path}.")
        local_hash = _sha256_file(local_path)
        last_error = ""
        for attempt in range(1, attempts + 1):
            try:
                public_hash = _sha256_bytes(_download_bytes(public_url))
                if public_hash == local_hash:
                    break
                last_error = "hash public different du fichier local"
            except RuntimeError as exc:
                last_error = str(exc)
            if attempt < attempts:
                time.sleep(delay_seconds)
        else:
            raise SystemExit(
                f"Publication bloquee: slide publique non validee pour {public_url}. "
                f"Derniere erreur: {last_error}"
            )


def create_carousel_item(ig_user_id: str, access_token: str, image_url: str) -> str:
    response = _post_json(
        f"{GRAPH_BASE_URL}/{ig_user_id}/media",
        {
            "image_url": image_url,
            "is_carousel_item": "true",
        },
        access_token,
    )
    container_id = response.get("id")
    if not container_id:
        raise RuntimeError(f"Meta n'a pas retourne d'id de slide carrousel: {response}")
    return str(container_id)


def create_carousel_container(
    ig_user_id: str,
    access_token: str,
    children: list[str],
    caption: str,
) -> str:
    response = _post_json(
        f"{GRAPH_BASE_URL}/{ig_user_id}/media",
        {
            "media_type": "CAROUSEL",
            "children": ",".join(children),
            "caption": caption,
        },
        access_token,
    )
    container_id = response.get("id")
    if not container_id:
        raise RuntimeError(f"Meta n'a pas retourne d'id de carrousel: {response}")
    return str(container_id)


def _mark_weekly_published(path: str | Path, week_id: str, media_id: str) -> None:
    path = Path(path)
    data = {"published": []}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    weekly = data.setdefault("weekly_carousels", {})
    weekly[week_id] = media_id
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Publie un carrousel hebdomadaire sur Instagram.")
    parser.add_argument("--draft", required=True)
    parser.add_argument("--published", default="published.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    draft = _load_draft(args.draft)
    slides = draft["slides"]
    if not 2 <= len(slides) <= 10:
        raise SystemExit(f"Instagram accepte 2 a 10 slides par carrousel, recu: {len(slides)}.")

    _verify_public_slides(draft)

    ig_user_id = _clean_secret(os.getenv("META_IG_USER_ID"))
    access_token = _clean_secret(os.getenv("META_ACCESS_TOKEN"))
    if args.dry_run:
        print("Dry-run OK: carrousel approuve, slides publiques synchronisees, publication non envoyee.")
        print(f"Endpoint Meta: {GRAPH_BASE_URL}")
        print(f"Slides: {len(slides)}")
        print(f"Caption:\n{draft['caption']}")
        return
    if not ig_user_id or not access_token:
        raise SystemExit("Variables manquantes: META_IG_USER_ID et META_ACCESS_TOKEN.")

    children = []
    for slide in slides:
        child_id = create_carousel_item(ig_user_id, access_token, slide["public_url"])
        wait_until_container_ready(child_id, access_token)
        children.append(child_id)

    carousel_id = create_carousel_container(ig_user_id, access_token, children, draft["caption"])
    wait_until_container_ready(carousel_id, access_token)
    media_id = publish_container(ig_user_id, access_token, carousel_id)
    _mark_weekly_published(args.published, draft["week_id"], media_id)
    print(f"Publication carrousel Instagram OK: media_id={media_id}")


if __name__ == "__main__":
    main()
