from __future__ import annotations

import argparse
import io
import json
import re
import sys
import unicodedata
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import load_config


SCRUTINS_JSON_ZIP_URL = (
    "https://data.assemblee-nationale.fr/static/openData/repository/17/loi/"
    "scrutins/Scrutins.json.zip"
)


FINAL_READING_PATTERN = "lecture definitive"
WHOLE_TEXT_PATTERNS = (
    "ensemble du projet de loi",
    "ensemble de la proposition de loi",
    "ensemble d'une proposition de loi",
    "ensemble de la proposition de loi organique",
    "ensemble du projet de loi organique",
)


@dataclass(frozen=True)
class GroupVote:
    id: str
    sigle: str
    nom: str
    membres: int
    pour: int
    contre: int
    abstention: int
    non_votant: int
    position_majoritaire: str | None


@dataclass(frozen=True)
class ScrutinSummary:
    uid: str
    numero: int
    date: str
    titre: str
    objet: str
    dossier: str | None
    type_vote: str
    type_vote_code: str
    sort: str
    source_url: str
    significant: bool
    totals: dict[str, int]
    groups: list[GroupVote]


def _download_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "vote-card-bot/0.1"})
    with urllib.request.urlopen(req, timeout=90) as response:
        return response.read()


def _to_int(value: Any) -> int:
    if value is None:
        return 0
    return int(value)


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _scrutin_number_from_name(name: str) -> int:
    match = re.search(r"V(\d+)\.json$", name)
    if not match:
        raise ValueError(f"Impossible de lire le numero du scrutin depuis {name}")
    return int(match.group(1))


def _normalized_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text.replace("’", "'")


def _is_significant(scrutin: dict[str, Any]) -> bool:
    title = _normalized_text(
        f"{scrutin.get('titre', '')} {scrutin.get('objet', {}).get('libelle', '')}"
    )
    return FINAL_READING_PATTERN in title and any(
        pattern in title for pattern in WHOLE_TEXT_PATTERNS
    )


def normalize_scrutin(scrutin_doc: dict[str, Any], config_path: str | Path) -> ScrutinSummary:
    scrutin = scrutin_doc["scrutin"]
    config = load_config(config_path)
    groups_by_id = config.groups_by_id
    raw_groups = _as_list(scrutin["ventilationVotes"]["organe"]["groupes"].get("groupe"))
    raw_groups_by_id = {group["organeRef"]: group for group in raw_groups}

    groups: list[GroupVote] = []
    for group_config in config.groups:
        raw = raw_groups_by_id.get(group_config.id)
        if not raw:
            if not group_config.optional:
                print(
                    f"Attention: groupe absent du scrutin {scrutin['numero']}: "
                    f"{group_config.sigle} ({group_config.id})",
                    file=sys.stderr,
                )
            continue
        counts = raw["vote"]["decompteVoix"]
        non_votant = _to_int(counts.get("nonVotants")) + _to_int(
            counts.get("nonVotantsVolontaires")
        )
        groups.append(
            GroupVote(
                id=group_config.id,
                sigle=group_config.sigle,
                nom=group_config.nom,
                membres=_to_int(raw.get("nombreMembresGroupe")),
                pour=_to_int(counts.get("pour")),
                contre=_to_int(counts.get("contre")),
                abstention=_to_int(counts.get("abstentions")),
                non_votant=non_votant,
                position_majoritaire=raw["vote"].get("positionMajoritaire"),
            )
        )

    unknown = sorted(set(raw_groups_by_id) - set(groups_by_id))
    if unknown:
        print(
            f"Attention: groupes non configures dans le scrutin {scrutin['numero']}: "
            + ", ".join(unknown),
            file=sys.stderr,
        )

    decompte = scrutin["syntheseVote"]["decompte"]
    numero = int(scrutin["numero"])
    dossier = scrutin.get("objet", {}).get("dossierLegislatif") or {}
    return ScrutinSummary(
        uid=scrutin["uid"],
        numero=numero,
        date=scrutin["dateScrutin"],
        titre=scrutin["titre"],
        objet=scrutin.get("objet", {}).get("libelle") or scrutin["titre"],
        dossier=dossier.get("libelle"),
        type_vote=scrutin["typeVote"].get("libelleTypeVote") or "",
        type_vote_code=scrutin["typeVote"].get("codeTypeVote") or "",
        sort=scrutin["sort"].get("libelle") or "",
        source_url=f"https://www.assemblee-nationale.fr/dyn/17/scrutins/{numero}",
        significant=_is_significant(scrutin),
        totals={
            "votants": _to_int(scrutin["syntheseVote"].get("nombreVotants")),
            "exprimes": _to_int(scrutin["syntheseVote"].get("suffragesExprimes")),
            "pour": _to_int(decompte.get("pour")),
            "contre": _to_int(decompte.get("contre")),
            "abstention": _to_int(decompte.get("abstentions")),
            "non_votant": _to_int(decompte.get("nonVotants"))
            + _to_int(decompte.get("nonVotantsVolontaires")),
        },
        groups=groups,
    )


def load_scrutins_from_zip(zip_bytes: bytes, config_path: str | Path) -> list[ScrutinSummary]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.startswith("json/") and name.endswith(".json")
        ]
        ordered_names = sorted(names, key=_scrutin_number_from_name, reverse=True)
        return [
            normalize_scrutin(json.loads(archive.read(name)), config_path)
            for name in ordered_names
        ]


def select_scrutins_from_zip(
    zip_bytes: bytes,
    config_path: str | Path,
    published: set[str],
    limit: int,
    include_already_published: bool = False,
    numero: int | None = None,
    since_date: str | None = None,
) -> list[ScrutinSummary]:
    selected: list[ScrutinSummary] = []
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.startswith("json/") and name.endswith(".json")
        ]
        ordered_names = sorted(names, key=_scrutin_number_from_name, reverse=True)
        for name in ordered_names:
            doc = json.loads(archive.read(name))
            scrutin = doc["scrutin"]
            if numero is not None and int(scrutin["numero"]) != numero:
                continue
            if numero is None:
                if since_date and scrutin["dateScrutin"] < since_date:
                    continue
                if scrutin["uid"] in published and not include_already_published:
                    continue
                if not _is_significant(scrutin):
                    continue
            selected.append(normalize_scrutin(doc, config_path))
            if numero is not None or len(selected) >= limit:
                break
    return selected


def load_published(path: str | Path) -> set[str]:
    path = Path(path)
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    return set(data.get("published", []))


def select_new_scrutins(
    scrutins: list[ScrutinSummary], published: set[str], limit: int
) -> list[ScrutinSummary]:
    selected = [
        scrutin
        for scrutin in scrutins
        if scrutin.uid not in published and scrutin.significant
    ]
    return selected[:limit]


def main() -> None:
    parser = argparse.ArgumentParser(description="Recupere les derniers scrutins officiels.")
    parser.add_argument("--url", default=SCRUTINS_JSON_ZIP_URL)
    parser.add_argument("--config", default="groupes_politiques.json")
    parser.add_argument("--published", default="published.json")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--output", default="work/latest_scrutins.json")
    parser.add_argument("--include-already-published", action="store_true")
    parser.add_argument("--numero", type=int, help="Force un numero de scrutin precis.")
    parser.add_argument("--since-date", help="Ignore les scrutins anterieurs a cette date YYYY-MM-DD.")
    args = parser.parse_args()

    selected = select_scrutins_from_zip(
        _download_bytes(args.url),
        args.config,
        load_published(args.published),
        args.limit,
        include_already_published=args.include_already_published,
        numero=args.numero,
        since_date=args.since_date,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps([asdict(scrutin) for scrutin in selected], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"{len(selected)} scrutin(s) ecrit(s) dans {output}")
    for scrutin in selected:
        print(f"- n°{scrutin.numero} | {scrutin.date} | {scrutin.type_vote} | {scrutin.titre}")


if __name__ == "__main__":
    main()
