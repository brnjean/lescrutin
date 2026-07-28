from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


def _public_url(public_base_url: str | None, public_path: str) -> str | None:
    if not public_base_url:
        return None
    return f"{public_base_url.rstrip('/')}/{public_path.lstrip('/')}"


def _missing_copy(draft: dict) -> list[int]:
    missing = [int(numero) for numero in draft.get("missing_copy", [])]
    for scrutin in draft.get("scrutins", []):
        description = str(scrutin.get("description") or "").strip()
        if not description:
            missing.append(int(scrutin.get("numero") or scrutin.get("id") or 0))
    return sorted(set(missing))


def main() -> None:
    parser = argparse.ArgumentParser(description="Place un carrousel hebdomadaire dans le dossier public.")
    parser.add_argument("--draft", required=True)
    parser.add_argument("--public-dir", default="public")
    parser.add_argument(
        "--public-base-url",
        default=os.getenv("PUBLIC_BASE_URL", "https://brnjean.github.io/lescrutin"),
    )
    args = parser.parse_args()

    draft_path = Path(args.draft)
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    missing = _missing_copy(draft)
    if missing:
        copy_path = draft.get("copy_path", "weekly_copy/week-YYYY-MM-DD.json")
        raise SystemExit(
            "Mise en ligne bloquee: textes hebdomadaires manquants pour les scrutins "
            + ", ".join(str(numero) for numero in missing)
            + f". Remplis les descriptions dans {copy_path}, puis regenere le carrousel."
        )
    if draft.get("status") != "approved_by_human":
        raise SystemExit("Mise en ligne bloquee: le brouillon hebdomadaire n'est pas approuve.")

    public_dir = Path(args.public_dir)
    week_id = draft.get("week_id") or draft.get("carousel_id")
    carousel_dir = public_dir / "carousels" / week_id
    carousel_dir.mkdir(parents=True, exist_ok=True)

    public_slides = []
    for index, slide in enumerate(draft["slides"], start=1):
        source = Path(slide["path"])
        public_path = carousel_dir / f"slide-{index:02d}.png"
        shutil.copy2(source, public_path)
        relative_path = public_path.relative_to(public_dir).as_posix()
        public_slides.append(
            {
                **slide,
                "public_path": relative_path,
                "public_url": _public_url(args.public_base_url, relative_path),
            }
        )

    manifest_path = public_dir / "manifest.json"
    manifest_key = draft.get("manifest_key", "weekly_carousels")
    manifest = {"posts": [], "weekly_carousels": [], manifest_key: []}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    carousels = [
        item
        for item in manifest.get(manifest_key, [])
        if item.get("week_id") != week_id and item.get("carousel_id") != week_id
    ]
    carousels.insert(
        0,
        {
            "carousel_id": week_id,
            "week_id": week_id,
            "week_start": draft["week_start"],
            "week_end": draft["week_end"],
            "draft_path": draft_path.as_posix(),
            "slides": public_slides,
            "staged_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    manifest[manifest_key] = carousels
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    staged_draft = {**draft, "slides": public_slides}
    draft_path.write_text(json.dumps(staged_draft, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Carrousel public prepare: carousels/{week_id}")
    for slide in public_slides:
        print(slide["public_url"])


if __name__ == "__main__":
    main()
