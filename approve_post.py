from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Marque un brouillon comme valide humainement.")
    parser.add_argument("draft", help="Chemin du fichier outputs/draft-scrutin-XXXX.json")
    args = parser.parse_args()

    path = Path(args.draft)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("status") != "awaiting_human_approval":
        raise SystemExit(f"Statut inattendu: {data.get('status')}")

    data["status"] = "approved_by_human"
    data["approved_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Brouillon approuve: {path}")


if __name__ == "__main__":
    main()
