# Compte Instagram automatise de suivi des votes

Pipeline local pour transformer les scrutins publics de l'Assemblee nationale en cartes Instagram factuelles.

Compte Instagram cible: `@lescrutin`.

## Etape 1 - Recuperation et visuel local

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python fetch_scrutins.py --limit 1
PYTHONPATH=src python verify_sources.py
PYTHONPATH=src python prepare_post.py
```

Les images et brouillons sont exportes dans `outputs/`.

## Validation humaine

Le mode recommande au debut est volontairement semi-automatique:

```bash
PYTHONPATH=src python fetch_scrutins.py --limit 1
PYTHONPATH=src python verify_sources.py
PYTHONPATH=src python prepare_post.py
```

Puis verifier:

- l'image `outputs/scrutin-XXXX.png`
- le brouillon `outputs/draft-scrutin-XXXX.json`
- le titre
- la legende
- la source officielle

Si tout est bon:

```bash
python approve_post.py outputs/draft-scrutin-XXXX.json
```

La publication Instagram refusera de partir tant que le brouillon n'a pas le statut `approved_by_human`.

Puis preparer l'image pour une URL publique:

```bash
PYTHONPATH=src python stage_public_asset.py \
  --draft outputs/draft-scrutin-XXXX.json \
  --public-base-url https://ton-utilisateur.github.io/ton-repo
```

## Publication Instagram

Voir [docs/instagram_setup.md](docs/instagram_setup.md).

Resume: Instagram ne peut pas publier directement `outputs/scrutin-XXXX.png` depuis ton ordinateur. Il faut d'abord une URL publique HTTPS pour l'image, puis:

```bash
PYTHONPATH=src python publish_instagram.py \
  --draft outputs/draft-scrutin-XXXX.json \
  --image-url https://example.com/scrutin-XXXX.png
```

## Sources

- Scrutins officiels: `https://data.assemblee-nationale.fr/static/openData/repository/17/loi/scrutins/Scrutins.json.zip`
- Page source d'un scrutin: `https://www.assemblee-nationale.fr/dyn/17/scrutins/<numero>`
- Groupes politiques: export AMO40 de l'Assemblee nationale, utilise pour verifier les identifiants `PO...`.

## Regles editoriales encodees

- Couleurs fixes: pour, contre, abstention.
- Ordre gauche-droite centralise dans `groupes_politiques.json`.
- Filtre de significativite initial: scrutins publics solennels, votes sur l'ensemble, CMP, motions de censure ou de rejet.
- Etat anti-doublon: `published.json`.
- Garde-fou avant publication: `verify_sources.py` compare les totaux locaux avec la page officielle du scrutin sur assemblee-nationale.fr et bloque la suite en cas d'ecart.

## Prochaines etapes

1. Valider le style visuel et le nom du compte.
2. Ameliorer la generation du titre et du sous-titre avec une validation humaine.
3. Brancher l'hebergement public de l'image.
4. Brancher Instagram Graph API avec `META_IG_USER_ID` et `META_ACCESS_TOKEN`.
5. Activer GitHub Actions.
