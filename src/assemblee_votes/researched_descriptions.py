from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Any


OPENAI_URL = "https://api.openai.com/v1/responses"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")


@dataclass(frozen=True)
class ResearchedDescription:
    description: str
    sources: list[str]
    method: str


CURATED_DESCRIPTIONS: dict[int, ResearchedDescription] = {
    8434: ResearchedDescription(
        description=(
            "Le texte réforme la gestion des bureaux, bâtiments et terrains appartenant à l'État. "
            "Il crée une foncière publique chargée de gérer, rénover, louer, valoriser ou vendre une partie du patrimoine immobilier. "
            "L'enjeu est de rendre ce parc plus efficace, notamment sur les coûts, l'usage des locaux et la rénovation."
        ),
        sources=[
            "https://www.assemblee-nationale.fr/dyn/17/dossiers/DLR5L17N52746",
            "https://www.vie-publique.fr/loi/301991-gestion-du-patrimoine-immobilier-de-letat-proposition-de-loi",
        ],
        method="curated_from_sources",
    ),
    8433: ResearchedDescription(
        description=(
            "Le projet de loi RIPOST vise à répondre plus vite à certains faits troublant l'ordre public, la sécurité ou la tranquillité. "
            "Il renforce l'arsenal juridique autour de sanctions, procédures et moyens d'action des autorités. "
            "L'enjeu est l'équilibre entre efficacité de la réponse publique et garanties attachées aux libertés individuelles."
        ),
        sources=[
            "https://www.assemblee-nationale.fr/dyn/17/dossiers/DLR5L17N53980",
            "https://www.vie-publique.fr/loi/302565-projet-de-loi-ripost-ordre-public-securite-et-tranquillite",
            "https://www.interieur.gouv.fr/actualites/dossiers-de-presse/presentation-du-projet-de-loi-ripost",
        ],
        method="curated_from_sources",
    ),
    8431: ResearchedDescription(
        description=(
            "Le texte vise à limiter l'exposition des mineurs aux risques liés aux réseaux sociaux. "
            "Il encadre l'accès des plus jeunes, les usages des adolescents et certaines pratiques publicitaires ciblant les mineurs. "
            "L'enjeu est de renforcer la protection des enfants tout en imposant de nouvelles obligations aux plateformes."
        ),
        sources=[
            "https://www.assemblee-nationale.fr/dyn/17/dossiers/proteger_mineurs_reseaux_sociaux_17e",
            "https://www.vie-publique.fr/loi/301799-proteger-les-mineurs-risques-des-reseaux-sociaux-proposition-de-loi",
            "https://www.senat.fr/travaux-parlementaires/textes-legislatifs/la-loi-en-clair/proposition-de-loi-visant-a-proteger-les-mineurs-des-risques-auxquels-les-expose-lutilisation-des-reseaux-sociaux.html",
        ],
        method="curated_from_sources",
    ),
    8427: ResearchedDescription(
        description=(
            "Ce projet de loi d'urgence porte sur la protection de la souveraineté agricole et alimentaire. "
            "Il cherche à soutenir les filières, sécuriser certaines productions et répondre aux difficultés économiques ou réglementaires du monde agricole. "
            "L'enjeu est de renforcer la capacité de production française tout en arbitrant entre compétitivité, normes et protection de l'environnement."
        ),
        sources=[
            "https://www.assemblee-nationale.fr/dyn/17/dossiers/projet_loi_urgence_pour_protection_et_souverainete_agricoles",
            "https://www.senat.fr/travaux-parlementaires/textes-legislatifs/la-loi-en-clair/urgence-agricole.html",
            "https://agriculture.gouv.fr/lassemblee-nationale-adopte-le-projet-de-loi-durgence-agricole",
        ],
        method="curated_from_sources",
    ),
    8421: ResearchedDescription(
        description=(
            "La proposition actualise la loi Montagne pour l'adapter aux réalités actuelles des territoires d'altitude. "
            "Elle touche à l'accès aux services publics, à l'urbanisme, à l'eau, à l'agriculture, à la forêt et au tourisme. "
            "L'enjeu est de maintenir des territoires habités et actifs tout en tenant compte des contraintes climatiques et environnementales."
        ),
        sources=[
            "https://www.assemblee-nationale.fr/dyn/17/dossiers/DLR5L17N54006",
            "https://www.senat.fr/travaux-parlementaires/textes-legislatifs/la-loi-en-clair/proposition-de-loi-pour-une-montagne-vivante-et-souveraine.html",
        ],
        method="curated_from_sources",
    ),
    8419: ResearchedDescription(
        description=(
            "Le texte crée une stratégie nationale contre les maladies cardio-neuro-vasculaires, comme les infarctus ou AVC. "
            "Il met l'accent sur la prévention, les dépistages à différents âges de la vie et le rôle de plusieurs professionnels de santé. "
            "L'enjeu est d'agir plus tôt sur des maladies fréquentes, coûteuses et souvent évitables."
        ),
        sources=[
            "https://www.assemblee-nationale.fr/dyn/17/dossiers/DLR5L17N53426",
            "https://www.senat.fr/cra/s20260709/s20260709_3.html",
            "https://www.vie-publique.fr/loi/303718-prevention-maladies-cardio-neuro-vasculaire-loi-neuder-27-juillet-2026",
        ],
        method="curated_from_sources",
    ),
    8418: ResearchedDescription(
        description=(
            "La proposition de loi porte sur l'organisation, la gestion et le financement du sport professionnel. "
            "Elle vise notamment la gouvernance des clubs et des ligues, ainsi que l'encadrement de certains équilibres économiques. "
            "L'enjeu est de mieux structurer le sport professionnel sans le réduire au seul football."
        ),
        sources=[
            "https://www.assemblee-nationale.fr/dyn/17/dossiers/DLR5L17N51732",
            "https://www.vie-publique.fr/loi/298987-sport-professionnel-foot-organisation-et-financement-proposition-de-loi",
        ],
        method="curated_from_sources",
    ),
}


def _text_from_response(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"].strip()
    parts: list[str] = []
    for item in response.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def _validate_description(text: str) -> str:
    description = " ".join(text.split())
    if not description:
        raise ValueError("description vide")
    if len(description) > 430:
        raise ValueError("description trop longue")
    if re.search(r"\b(devrait|honteux|scandaleux|excellent|catastrophique)\b", description, re.I):
        raise ValueError("description non neutre")
    return description


def generate_ai_description(scrutin: dict[str, Any]) -> ResearchedDescription | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    official_sources = [
        scrutin["source_url"],
        f"https://www.assemblee-nationale.fr/dyn/17/dossiers/{scrutin.get('dossier_ref')}",
    ]
    source_text = "\n".join(
        [
            f"Titre du scrutin: {scrutin.get('titre')}",
            f"Objet du vote: {scrutin.get('objet')}",
            f"Dossier legislatif: {scrutin.get('dossier')}",
            f"Etape: {scrutin.get('stage_label')}",
        ]
    )
    prompt = (
        "Tu rediges pour un compte Instagram neutre qui explique les votes de l'Assemblee nationale. "
        "A partir des informations source ci-dessous, ecris une synthese en francais, neutre, claire, en 3 phrases maximum. "
        "Explique concretement ce que fait le texte et l'enjeu public. "
        "N'ajoute aucune opinion, aucun jugement de valeur, aucun appel politique. "
        "Ne parle pas du score du vote. Reponds uniquement avec le texte final.\n\n"
        + source_text
    )
    payload = {
        "model": OPENAI_MODEL,
        "input": prompt,
        "max_output_tokens": 220,
    }
    req = urllib.request.Request(
        OPENAI_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        data = json.loads(response.read().decode("utf-8"))
    return ResearchedDescription(
        description=_validate_description(_text_from_response(data)),
        sources=official_sources,
        method=f"openai:{OPENAI_MODEL}",
    )


def researched_description(scrutin: dict[str, Any]) -> ResearchedDescription | None:
    curated = CURATED_DESCRIPTIONS.get(int(scrutin["numero"]))
    if curated:
        return curated
    return generate_ai_description(scrutin)
