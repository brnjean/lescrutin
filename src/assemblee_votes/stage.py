from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class StagedAsset:
    numero: int
    uid: str
    image_path: str
    public_path: str
    public_url: str | None
    staged_at: str


def _load_draft(path: str | Path) -> dict[str, Any]:
    draft = json.loads(Path(path).read_text(encoding="utf-8"))
    if draft.get("status") != "approved_by_human":
        raise SystemExit("Mise en ligne bloquee: le brouillon n'est pas approuve.")
    return draft


def _public_url(public_base_url: str | None, public_path: str) -> str | None:
    if not public_base_url:
        return None
    return f"{public_base_url.rstrip('/')}/{public_path.lstrip('/')}"


def stage_draft(
    draft_path: str | Path,
    public_dir: str | Path = "public",
    public_base_url: str | None = None,
) -> StagedAsset:
    draft = _load_draft(draft_path)
    image_path = Path(draft["image_path"])
    if not image_path.exists():
        raise SystemExit(f"Image introuvable: {image_path}")

    numero = int(draft["scrutin"]["numero"])
    uid = draft["scrutin"]["uid"]
    public_dir = Path(public_dir)
    posts_dir = public_dir / "posts"
    posts_dir.mkdir(parents=True, exist_ok=True)

    public_image = posts_dir / f"scrutin-{numero}.png"
    shutil.copy2(image_path, public_image)

    relative_public_path = public_image.relative_to(public_dir).as_posix()
    asset = StagedAsset(
        numero=numero,
        uid=uid,
        image_path=image_path.as_posix(),
        public_path=relative_public_path,
        public_url=_public_url(public_base_url, relative_public_path),
        staged_at=datetime.now(timezone.utc).isoformat(),
    )

    manifest_path = public_dir / "manifest.json"
    manifest = {"posts": []}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    posts = [post for post in manifest.get("posts", []) if post.get("uid") != uid]
    posts.insert(0, asdict(asset))
    manifest["posts"] = posts
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return asset


def main() -> None:
    parser = argparse.ArgumentParser(description="Place une image approuvee dans le dossier public.")
    parser.add_argument("--draft", required=True, help="Fichier outputs/draft-scrutin-XXXX.json approuve.")
    parser.add_argument("--public-dir", default="public")
    parser.add_argument(
        "--public-base-url",
        default=os.getenv("PUBLIC_BASE_URL"),
        help="URL de base GitHub Pages, ex: https://user.github.io/repo",
    )
    args = parser.parse_args()

    asset = stage_draft(args.draft, args.public_dir, args.public_base_url)
    print(f"Image publique preparee: {asset.public_path}")
    if asset.public_url:
        print(f"URL publique prevue: {asset.public_url}")
    else:
        print("URL publique non calculee: definir PUBLIC_BASE_URL quand GitHub Pages sera active.")


if __name__ == "__main__":
    main()
