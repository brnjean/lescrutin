from __future__ import annotations

import unicodedata
from typing import Any


STAGE_ORDER = {
    "lecture_definitive": 1,
    "texte_cmp": 2,
    "nouvelle_lecture": 3,
}

STAGE_LABELS = {
    "lecture_definitive": "Lecture définitive",
    "texte_cmp": "Texte de CMP",
    "nouvelle_lecture": "Nouvelle lecture",
}

STAGE_NOTES = {
    "lecture_definitive": (
        "Lecture définitive : ce vote correspond au dernier mot du Parlement sur ce texte. "
        "La loi peut encore devoir être promulguée et, le cas échéant, contrôlée par le Conseil constitutionnel."
    ),
    "texte_cmp": (
        "Texte de CMP : députés et sénateurs ont cherché un compromis sur une version commune. "
        "Ce vote est important, mais la loi n'est définitivement adoptée que si les deux chambres adoptent le même texte."
    ),
    "nouvelle_lecture": (
        "Nouvelle lecture : le texte revient à l'Assemblée après un désaccord dans la navette parlementaire. "
        "Ce vote est important, mais ce n'est pas encore l'adoption définitive de la loi."
    ),
}


def normalized_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return text.replace("’", "'")


def combined_scrutin_text(scrutin: dict[str, Any]) -> str:
    return normalized_text(
        f"{scrutin.get('titre', '')} {scrutin.get('objet', {}).get('libelle', '')}"
    )


def stage_id(scrutin: dict[str, Any]) -> str | None:
    text = combined_scrutin_text(scrutin)
    if "lecture definitive" in text:
        return "lecture_definitive"
    if "texte de la commission mixte paritaire" in text:
        return "texte_cmp"
    if "nouvelle lecture" in text:
        return "nouvelle_lecture"
    return None


def stage_label(stage: str | None) -> str:
    if not stage:
        return "Étape non classée"
    return STAGE_LABELS.get(stage, "Étape non classée")


def stage_note(stage: str | None) -> str:
    if not stage:
        return ""
    return STAGE_NOTES.get(stage, "")
