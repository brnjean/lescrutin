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

## Publication automatique

GitHub Actions lance le robot automatiquement tous les 3 jours a `06:30 UTC`, soit environ `08:30` en France l'ete. Ton ordinateur peut etre ferme: GitHub execute le robot sur ses propres serveurs.

Le robot:

- cherche le dernier scrutin publiable non publie;
- accepte trois niveaux: lecture definitive, texte de CMP, nouvelle lecture;
- ignore les scrutins anterieurs au `28 juillet 2026`, pour ne pas publier l'ancien historique;
- verifie les chiffres avec la source officielle;
- genere l'image et la legende;
- met l'image en ligne;
- publie sur Instagram;
- marque le scrutin comme publie dans `published.json`.

Tu peux aussi lancer le controle manuellement depuis GitHub: onglet `Actions`, workflow `Auto publish key votes`, bouton `Run workflow`.

Secrets GitHub necessaires:

- `META_IG_USER_ID`
- `META_ACCESS_TOKEN`

## Carrousel hebdomadaire

Le carrousel hebdomadaire est semi-automatique: le robot choisit les votes cles, puis tu ecris les textes de chaque loi.

- couverture editoriale;
- une slide par texte;
- une slide de definition des etapes;
- une slide d'abonnement et de soutien.

Il garde les memes trois niveaux que les posts individuels: lecture definitive, texte de CMP, nouvelle lecture.

Generation locale:

```bash
PYTHONPATH=src python prepare_weekly_carousel.py
```

Cette commande cree aussi un fichier du type:

```text
weekly_copy/week-YYYY-MM-DD.json
```

Dans ce fichier, remplis chaque champ `description` avec tes 2-3 lignes. Puis regenere le carrousel pour intégrer tes textes:

```bash
PYTHONPATH=src python prepare_weekly_carousel.py
PYTHONPATH=src python stage_weekly_carousel.py \
  --draft outputs/weekly/week-YYYY-MM-DD/draft-week-YYYY-MM-DD.json \
  --public-base-url https://brnjean.github.io/lescrutin
```

Publication locale:

```bash
PYTHONPATH=src python publish_instagram_carousel.py \
  --draft outputs/weekly/week-YYYY-MM-DD/draft-week-YYYY-MM-DD.json
```

Le robot bloque la mise en ligne si une description est vide. Le workflow GitHub `Prepare/publish weekly carousel` se lance manuellement depuis l'onglet `Actions`.

## Publication Instagram

Voir [docs/instagram_setup.md](docs/instagram_setup.md).

Tester une cle Meta/Instagram sans l'ecrire dans le depot:

```bash
export META_ACCESS_TOKEN="COLLER_LE_TOKEN_ICI"
PYTHONPATH=src python inspect_instagram_token.py
```

URL de redirection Instagram:

```text
https://brnjean.github.io/lescrutin/instagram-callback.html
```

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
- Titres courts: verbe clair + objet concret de la loi, sans jugement politique.
- Filtre editorial: publication automatique pour les votes sur l'ensemble du texte en lecture definitive, texte de CMP ou nouvelle lecture.
- Chaque post affiche l'etape du texte et la legende explique si le vote n'est pas encore une adoption definitive.
- Les premieres lectures, deuxiemes lectures, motions, amendements et votes d'article sont ignores par defaut.
- Etat anti-doublon: `published.json`.
- Garde-fou avant publication: `verify_sources.py` compare les totaux locaux avec la page officielle du scrutin sur assemblee-nationale.fr et bloque la suite en cas d'ecart.

## Prochaines etapes

1. Valider le style visuel et le nom du compte.
2. Ameliorer la generation du titre et du sous-titre avec une validation humaine.
3. Brancher l'hebergement public de l'image.
4. Brancher Instagram Graph API avec `META_IG_USER_ID` et `META_ACCESS_TOKEN`.
5. Activer GitHub Actions.
