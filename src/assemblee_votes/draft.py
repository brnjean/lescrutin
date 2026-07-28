from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .verify import verify_scrutin
from .visual import draw_card


def editorial_title(scrutin: dict[str, Any]) -> str:
    dossier = scrutin.get("dossier")
    if dossier and dossier.lower() == "fin de vie":
        return "Créer un droit à l'aide à mourir"
    return dossier or scrutin.get("objet") or scrutin["titre"]


def build_caption(scrutin: dict[str, Any]) -> str:
    result = (
        f"Le scrutin a été adopté avec {scrutin['totals']['pour']} voix pour, "
        f"{scrutin['totals']['contre']} contre et {scrutin['totals']['abstention']} abstention(s)."
    )
    title = editorial_title(scrutin)
    return "\n\n".join(
        [
            result,
            f"Scrutin n°{scrutin['numero']} - {scrutin['date']}",
            title,
            f"Source : Assemblée nationale - {scrutin['source_url']}",
            "@lescrutin",
            "#AssembleeNationale #Politique #Datajournalisme #Vote #France",
        ]
    )


def create_draft(
    scrutin: dict[str, Any],
    output_dir: str | Path = "outputs",
    config_path: str | Path = "groupes_politiques.json",
) -> Path:
    verification = verify_scrutin(scrutin)
    if not verification.passed:
        raise ValueError(
            "Verification source echouee, brouillon non cree: "
            + "; ".join(verification.errors)
        )

    output_dir = Path(output_dir)
    image_path = output_dir / f"scrutin-{scrutin['numero']}.png"
    draw_card(scrutin, image_path, config_path)

    draft = {
        "status": "awaiting_human_approval",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "approved_at": None,
        "scrutin": {
            "uid": scrutin["uid"],
            "numero": scrutin["numero"],
            "date": scrutin["date"],
            "title_for_image": editorial_title(scrutin),
            "source_url": scrutin["source_url"],
            "totals": scrutin["totals"],
        },
        "image_path": str(image_path),
        "caption": build_caption(scrutin),
        "verification": asdict(verification),
        "human_review_checklist": [
            "Le titre est factuel et non trompeur.",
            "L'image est lisible.",
            "Les chiffres Pour / Contre / Abstention correspondent a la source.",
            "La source Assemblee nationale est presente.",
        ],
    }

    draft_path = output_dir / f"draft-scrutin-{scrutin['numero']}.json"
    output_dir.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    return draft_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Cree un brouillon verifie avant validation humaine.")
    parser.add_argument("--input", default="work/latest_scrutins.json")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--config", default="groupes_politiques.json")
    args = parser.parse_args()

    scrutins = json.loads(Path(args.input).read_text(encoding="utf-8"))
    if not scrutins:
        print("Aucun scrutin a preparer.")
        return
    for scrutin in scrutins:
        draft_path = create_draft(scrutin, args.output_dir, args.config)
        print(f"Brouillon cree: {draft_path}")


if __name__ == "__main__":
    main()
