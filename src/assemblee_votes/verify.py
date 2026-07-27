from __future__ import annotations

import argparse
import html
import json
import re
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class VerificationResult:
    numero: int
    passed: bool
    errors: list[str]
    warnings: list[str]
    official_counts: dict[str, int]
    local_counts: dict[str, int]
    source_url: str


def _download_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "vote-card-bot/0.1"})
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read().decode("utf-8", errors="replace")


def _page_text(html_text: str) -> str:
    text = re.sub(r"<script\b.*?</script>", " ", html_text, flags=re.I | re.S)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text)


def _extract_count(text: str, label: str) -> int | None:
    pattern = rf"{label}\s*:\s*(\d+)"
    match = re.search(pattern, text, flags=re.I)
    if not match:
        return None
    return int(match.group(1))


def fetch_official_counts(source_url: str) -> dict[str, int]:
    text = _page_text(_download_text(source_url))
    counts = {
        "pour": _extract_count(text, r"Pour l['’]adoption"),
        "contre": _extract_count(text, r"Contre"),
        "abstention": _extract_count(text, r"Abstention"),
    }
    missing = [key for key, value in counts.items() if value is None]
    if missing:
        raise ValueError(
            "Impossible de lire les compteurs officiels sur la page Assemblee: "
            + ", ".join(missing)
        )
    return {key: int(value) for key, value in counts.items() if value is not None}


def verify_scrutin(scrutin: dict[str, Any]) -> VerificationResult:
    errors: list[str] = []
    warnings: list[str] = []
    numero = int(scrutin["numero"])
    source_url = scrutin["source_url"]
    local_counts = {
        "pour": int(scrutin["totals"]["pour"]),
        "contre": int(scrutin["totals"]["contre"]),
        "abstention": int(scrutin["totals"]["abstention"]),
    }

    summed_counts = {
        key: sum(int(group[key]) for group in scrutin["groups"])
        for key in ("pour", "contre", "abstention")
    }
    if summed_counts != local_counts:
        errors.append(
            "Les totaux locaux ne correspondent pas a la somme des groupes: "
            f"totaux={local_counts}, groupes={summed_counts}"
        )

    if f"/scrutins/{numero}" not in source_url:
        errors.append(f"L'URL source ne semble pas pointer vers le scrutin n°{numero}: {source_url}")

    try:
        official_counts = fetch_official_counts(source_url)
    except Exception as exc:
        return VerificationResult(
            numero=numero,
            passed=False,
            errors=errors + [str(exc)],
            warnings=warnings,
            official_counts={},
            local_counts=local_counts,
            source_url=source_url,
        )

    if official_counts != local_counts:
        errors.append(
            "Les chiffres officiels Assemblee ne correspondent pas aux chiffres locaux: "
            f"officiel={official_counts}, local={local_counts}"
        )

    group_non_voters = sum(int(group["non_votant"]) for group in scrutin["groups"])
    total_non_voters = int(scrutin["totals"].get("non_votant", 0))
    if group_non_voters != total_non_voters:
        warnings.append(
            "Les non-votants par groupe ne correspondent pas exactement au total de synthese "
            f"({group_non_voters} vs {total_non_voters}). Ils ne sont pas affiches dans le total editorial."
        )

    return VerificationResult(
        numero=numero,
        passed=not errors,
        errors=errors,
        warnings=warnings,
        official_counts=official_counts,
        local_counts=local_counts,
        source_url=source_url,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verifie les scrutins avant generation/publication.")
    parser.add_argument("--input", default="work/latest_scrutins.json")
    parser.add_argument("--report", default="work/verification_report.json")
    args = parser.parse_args()

    scrutins = json.loads(Path(args.input).read_text(encoding="utf-8"))
    results = [verify_scrutin(scrutin) for scrutin in scrutins]
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    failed = [result for result in results if not result.passed]
    for result in results:
        status = "OK" if result.passed else "ECHEC"
        print(f"{status} scrutin n°{result.numero}: {result.source_url}")
        for warning in result.warnings:
            print(f"  avertissement: {warning}")
        for error in result.errors:
            print(f"  erreur: {error}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
