from __future__ import annotations

import re
import unicodedata
from typing import Any


TITLE_OVERRIDES = (
    ("fin de vie", "Créer un droit à l'aide à mourir"),
    ("patrimoine immobilier de l'etat", "Moderniser le patrimoine immobilier de l'État"),
    ("ordre public", "Répondre aux troubles à l'ordre public"),
    ("reseaux sociaux", "Protéger les mineurs sur les réseaux sociaux"),
    ("protection des enfants", "Renforcer la protection des enfants"),
    ("souverainete agricole", "Protéger la souveraineté agricole"),
    ("souverainete agricoles", "Protéger la souveraineté agricole"),
    ("montagne vivante", "Adapter la loi aux territoires de montagne"),
    ("cardio-neuro-vasculaire", "Lutter contre les maladies cardio-neuro-vasculaires"),
    ("sport professionnel", "Organiser le sport professionnel"),
    ("conseil de paris", "Réformer les élections à Paris, Lyon et Marseille"),
)


PHASE_PATTERNS = (
    r"\s*\([^)]*lecture[^)]*\)",
    r"\s*\(texte de la commission mixte paritaire\)",
)


def _normalized_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text.replace("’", "'")


def _strip_phase(value: str) -> str:
    title = value.strip().rstrip(".")
    for pattern in PHASE_PATTERNS:
        title = re.sub(pattern, "", title, flags=re.IGNORECASE)
    return title.strip()


def _strip_legal_boilerplate(value: str) -> str:
    title = _strip_phase(value)
    replacements = (
        r"^l['’]ensemble\s+",
        r"^du\s+",
        r"^de la\s+",
        r"^de l['’]\s*",
        r"^d['’]\s*",
        r"^projet de loi organique\s+",
        r"^proposition de loi organique\s+",
        r"^projet de loi\s+",
        r"^proposition de loi\s+",
        r"^visant à\s+",
        r"^visant a\s+",
        r"^relative à\s+",
        r"^relative a\s+",
        r"^relatif à\s+",
        r"^relatif a\s+",
        r"^pour\s+",
        r"^d['’]urgence pour\s+",
    )
    for pattern in replacements:
        title = re.sub(pattern, "", title, flags=re.IGNORECASE)
    return title[:1].upper() + title[1:]


def editorial_title(scrutin: dict[str, Any]) -> str:
    official_title = scrutin.get("titre") or ""
    dossier = scrutin.get("dossier") or ""
    search = _normalized_text(f"{dossier} {official_title} {scrutin.get('objet', '')}")
    for needle, title in TITLE_OVERRIDES:
        if needle in search:
            return title
    if dossier:
        return _strip_legal_boilerplate(dossier)
    return _strip_legal_boilerplate(official_title)


def image_title(scrutin: dict[str, Any]) -> str:
    return editorial_title(scrutin).upper()
