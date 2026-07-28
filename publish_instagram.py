from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from assemblee_votes.verify import verify_scrutin


GRAPH_VERSION = os.getenv("META_GRAPH_API_VERSION", "v22.0")
GRAPH_HOST = os.getenv("META_GRAPH_HOST", "graph.instagram.com")
GRAPH_BASE_URL = f"https://{GRAPH_HOST}/{GRAPH_VERSION}"


def _post_json(url: str, data: dict[str, str], access_token: str) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Erreur Meta API {exc.code}: {details}") from exc


def _get_json(url: str, params: dict[str, str], access_token: str) -> dict[str, Any]:
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        full_url,
        method="GET",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Erreur Meta API {exc.code}: {details}") from exc


def _load_draft(path: str | Path) -> dict[str, Any]:
    draft = json.loads(Path(path).read_text(encoding="utf-8"))
    if draft.get("status") != "approved_by_human":
        raise SystemExit(
            "Publication bloquee: le brouillon doit d'abord etre approuve avec approve_post.py."
        )
    return draft


def _load_scrutin_from_draft(draft: dict[str, Any], input_path: str | Path) -> dict[str, Any]:
    target_uid = draft["scrutin"]["uid"]
    scrutins = json.loads(Path(input_path).read_text(encoding="utf-8"))
    for scrutin in scrutins:
        if scrutin["uid"] == target_uid:
            return scrutin
    raise SystemExit(f"Publication bloquee: impossible de retrouver le scrutin {target_uid}.")


def _mark_published(path: str | Path, uid: str, media_id: str) -> None:
    path = Path(path)
    data = {"published": []}
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    published = data.setdefault("published", [])
    if uid not in published:
        published.append(uid)
    data.setdefault("instagram_media", {})[uid] = media_id
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def create_media_container(
    ig_user_id: str, access_token: str, image_url: str, caption: str
) -> str:
    response = _post_json(
        f"{GRAPH_BASE_URL}/{ig_user_id}/media",
        {
            "image_url": image_url,
            "caption": caption,
        },
        access_token,
    )
    container_id = response.get("id")
    if not container_id:
        raise RuntimeError(f"Meta n'a pas retourne d'id de container: {response}")
    return str(container_id)


def wait_until_container_ready(
    container_id: str, access_token: str, timeout_seconds: int = 180
) -> str:
    deadline = time.time() + timeout_seconds
    last_status = "UNKNOWN"
    while time.time() < deadline:
        response = _get_json(
            f"{GRAPH_BASE_URL}/{container_id}",
            {"fields": "status_code"},
            access_token,
        )
        last_status = response.get("status_code", "UNKNOWN")
        if last_status == "FINISHED":
            return last_status
        if last_status in {"ERROR", "EXPIRED"}:
            raise RuntimeError(f"Container Meta invalide: {response}")
        time.sleep(5)
    raise RuntimeError(f"Container Meta pas pret apres {timeout_seconds}s: {last_status}")


def publish_container(ig_user_id: str, access_token: str, container_id: str) -> str:
    response = _post_json(
        f"{GRAPH_BASE_URL}/{ig_user_id}/media_publish",
        {"creation_id": container_id},
        access_token,
    )
    media_id = response.get("id")
    if not media_id:
        raise RuntimeError(f"Meta n'a pas retourne d'id de media publie: {response}")
    return str(media_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Publie un brouillon approuve sur Instagram.")
    parser.add_argument("--draft", required=True, help="Fichier outputs/draft-scrutin-XXXX.json approuve.")
    parser.add_argument("--image-url", required=True, help="URL publique HTTPS de l'image a publier.")
    parser.add_argument("--input", default="work/latest_scrutins.json")
    parser.add_argument("--published", default="published.json")
    parser.add_argument("--dry-run", action="store_true", help="Verifie tout sans appeler l'API Meta.")
    args = parser.parse_args()

    ig_user_id = os.getenv("META_IG_USER_ID")
    access_token = os.getenv("META_ACCESS_TOKEN")
    if not args.dry_run and (not ig_user_id or not access_token):
        raise SystemExit("Variables manquantes: META_IG_USER_ID et META_ACCESS_TOKEN.")

    draft = _load_draft(args.draft)
    scrutin = _load_scrutin_from_draft(draft, args.input)
    verification = verify_scrutin(scrutin)
    if not verification.passed:
        raise SystemExit(
            "Publication bloquee: la verification source a echoue: "
            + "; ".join(verification.errors)
        )

    if args.dry_run:
        print("Dry-run OK: brouillon approuve, source verifiee, publication non envoyee.")
        print(f"Endpoint Meta: {GRAPH_BASE_URL}")
        print(f"Image publique: {args.image_url}")
        print(f"Caption:\n{draft['caption']}")
        return

    container_id = create_media_container(
        ig_user_id=ig_user_id,
        access_token=access_token,
        image_url=args.image_url,
        caption=draft["caption"],
    )
    wait_until_container_ready(container_id, access_token)
    media_id = publish_container(ig_user_id, access_token, container_id)
    _mark_published(args.published, scrutin["uid"], media_id)
    print(f"Publication Instagram OK: media_id={media_id}")


if __name__ == "__main__":
    main()
