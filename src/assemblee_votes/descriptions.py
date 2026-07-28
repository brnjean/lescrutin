from __future__ import annotations

import re
from typing import Any

from .stages import normalized_text


DESCRIPTION_OVERRIDES = (
    (
        "patrimoine immobilier de l'etat",
        "Le texte vise à moderniser la gestion des biens immobiliers de l'État. Il porte sur la façon dont ce patrimoine est suivi, valorisé et utilisé.",
    ),
    (
        "ordre public",
        "Le texte prévoit des réponses plus rapides face à certains troubles à l'ordre public. Il touche aux questions de sécurité, de tranquillité publique et d'intervention des autorités.",
    ),
    (
        "reseaux sociaux",
        "Le texte vise à mieux protéger les mineurs face aux risques liés aux réseaux sociaux. Il concerne l'exposition des enfants, l'encadrement des usages et la responsabilité des plateformes.",
    ),
    (
        "souverainete agricole",
        "Le texte porte sur la protection de l'agriculture française et de sa capacité à produire. Il aborde la souveraineté alimentaire, les filières agricoles et les réponses d'urgence au secteur.",
    ),
    (
        "souverainete agricoles",
        "Le texte porte sur la protection de l'agriculture française et de sa capacité à produire. Il aborde la souveraineté alimentaire, les filières agricoles et les réponses d'urgence au secteur.",
    ),
    (
        "montagne vivante",
        "Le texte adapte plusieurs règles aux réalités des territoires de montagne. Il concerne leur développement, leurs contraintes particulières et leur capacité à rester habités et actifs.",
    ),
    (
        "cardio-neuro-vasculaire",
        "Le texte vise à renforcer la prévention des maladies cardio-neuro-vasculaires. Il cherche à structurer une stratégie nationale face à un risque sanitaire majeur.",
    ),
    (
        "sport professionnel",
        "Le texte traite de l'organisation, de la gestion et du financement du sport professionnel. Il concerne le fonctionnement économique et institutionnel des clubs et compétitions.",
    ),
    (
        "fin de vie",
        "Le texte porte sur la création d'un droit à l'aide à mourir. Il encadre les conditions dans lesquelles une personne pourrait demander cette aide.",
    ),
    (
        "conseil de paris",
        "Le texte réforme le mode d'élection à Paris, Lyon et Marseille. Il concerne l'organisation démocratique spécifique de ces grandes villes.",
    ),
)


def _strip_phase(value: str) -> str:
    title = value.strip().rstrip(".")
    title = re.sub(r"\s*\([^)]*\)", "", title)
    title = re.sub(r"^l['’]ensemble\s+", "", title, flags=re.IGNORECASE)
    return title.strip()


def law_description(scrutin: dict[str, Any]) -> str:
    haystack = normalized_text(
        f"{scrutin.get('dossier', '')} {scrutin.get('titre', '')} {scrutin.get('objet', '')}"
    )
    for needle, description in DESCRIPTION_OVERRIDES:
        if needle in haystack:
            return description
    title = _strip_phase(scrutin.get("dossier") or scrutin.get("objet") or scrutin.get("titre") or "ce texte")
    return f"Le vote porte sur {title}. Le détail complet du texte est disponible dans le dossier législatif de l'Assemblée nationale."
