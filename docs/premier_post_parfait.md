# Plan du premier post parfait

Objectif: publier le premier post `@lescrutin` seulement quand l'image, le titre, la legende et les chiffres sont impeccables.

## 1. Repartir d'une base propre

```bash
cd /Users/jeanbironneau/Documents/Codex/2026-07-28/bon
source .venv/bin/activate
```

Verifier que les derniers changements sont bien la:

```bash
git status
```

## 2. Choisir le scrutin du premier post

Deux options:

- utiliser le dernier scrutin significatif disponible;
- choisir manuellement un scrutin precis si on veut un premier post plus fort editorialement.

Commandes:

```bash
PYTHONPATH=src python fetch_scrutins.py --limit 1
```

Ou, pour forcer un scrutin:

```bash
PYTHONPATH=src python fetch_scrutins.py --numero XXXX
```

## 3. Verifier les sources

```bash
PYTHONPATH=src python verify_sources.py
```

La publication est interdite si les chiffres officiels Assemblee ne correspondent pas.

## 4. Regenerer le brouillon

```bash
PYTHONPATH=src python prepare_post.py
```

Verifier:

- image dans `outputs/scrutin-XXXX.png`;
- brouillon dans `outputs/draft-scrutin-XXXX.json`;
- presence de `@lescrutin` sur l'image;
- ordre gauche-droite des groupes;
- lisibilite des logos;
- source officielle visible;
- titre factuel, non trompeur;
- legende neutre.

## 5. Corriger avant validation

Si l'image ou la legende ne sont pas parfaites:

- ajuster le code ou le brouillon;
- regenerer avec `prepare_post.py`;
- reverifier l'image localement.

Ne jamais publier une image non verifiee depuis GitHub Pages.

## 6. Valider humainement

```bash
python approve_post.py outputs/draft-scrutin-XXXX.json
```

## 7. Mettre l'image validee en public

```bash
PYTHONPATH=src python stage_public_asset.py \
  --draft outputs/draft-scrutin-XXXX.json \
  --public-base-url https://brnjean.github.io/lescrutin
```

Puis:

```bash
git add public published.json
git commit -m "Stage scrutin XXXX"
git push
```

Attendre que GitHub Actions soit vert.

## 8. Verifier l'image publique

Ouvrir:

```text
https://brnjean.github.io/lescrutin/posts/scrutin-XXXX.png
```

Controler une derniere fois:

- `@lescrutin` present;
- image nette;
- pas d'ancien fichier en cache;
- source et numero de scrutin corrects.

## 9. Tester Instagram sans publier

```bash
export META_IG_USER_ID="28335058006091227"
export META_ACCESS_TOKEN="TON_TOKEN_SECRET"
export META_GRAPH_HOST="graph.instagram.com"

PYTHONPATH=src python publish_instagram.py \
  --draft outputs/draft-scrutin-XXXX.json \
  --image-url https://brnjean.github.io/lescrutin/posts/scrutin-XXXX.png \
  --dry-run
```

## 10. Publier

Seulement si tout est valide:

```bash
PYTHONPATH=src python publish_instagram.py \
  --draft outputs/draft-scrutin-XXXX.json \
  --image-url https://brnjean.github.io/lescrutin/posts/scrutin-XXXX.png
```

## Principe long terme

Phase actuelle:

```text
Robot prepare -> humain valide -> robot publie
```

Phase future:

```text
Humain lance une commande -> robot prepare, verifie, publie si tout est conforme
```

Phase finale possible:

```text
Robot surveille les scrutins -> prepare automatiquement -> demande validation -> publie apres accord
```
