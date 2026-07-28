# Branchement Instagram

Objectif: publier seulement apres validation humaine.

## Le mecanisme

1. Le robot prepare l'image.
2. Le robot verifie les chiffres avec l'Assemblee nationale.
3. Le robot cree un brouillon.
4. Tu valides ou tu refuses.
5. Si tu valides, le robot peut appeler Instagram.

## Ce qu'il faut cote Instagram / Meta

1. Avoir un compte Instagram professionnel.
2. Le relier a une Page Facebook.
3. Creer une app sur Meta for Developers.
4. Activer Instagram Graph API / Instagram Platform selon le parcours Meta disponible.
5. Obtenir un identifiant de compte Instagram: `META_IG_USER_ID`.
6. Obtenir un token avec le droit de publier: `META_ACCESS_TOKEN`.
7. Mettre ces valeurs dans ton environnement local ou dans les secrets GitHub.

## Heberger l'image

Instagram exige une URL publique HTTPS. Le projet contient maintenant un dossier `public/` deployable avec GitHub Pages.

Apres validation humaine:

```bash
PYTHONPATH=src python stage_public_asset.py \
  --draft outputs/draft-scrutin-8434.json \
  --public-base-url https://ton-utilisateur.github.io/ton-repo
```

Cela copie l'image vers:

```text
public/posts/scrutin-8434.png
```

Quand GitHub Pages est actif, l'URL publique sera:

```text
https://ton-utilisateur.github.io/ton-repo/public/posts/scrutin-8434.png
```

Selon la configuration Pages choisie, si la racine publie directement le dossier `public`, l'URL peut etre:

```text
https://ton-utilisateur.github.io/ton-repo/posts/scrutin-8434.png
```

Le script accepte les deux modeles via `PUBLIC_BASE_URL`.

## Commandes locales

Tester le token:

```bash
export META_ACCESS_TOKEN="COLLER_LE_TOKEN_ICI"
PYTHONPATH=src python inspect_instagram_token.py
```

Preparation:

```bash
PYTHONPATH=src python fetch_scrutins.py --limit 1
PYTHONPATH=src python verify_sources.py
PYTHONPATH=src python prepare_post.py
```

Validation humaine:

```bash
python approve_post.py outputs/draft-scrutin-8434.json
```

Simulation de publication:

```bash
PYTHONPATH=src python publish_instagram.py \
  --draft outputs/draft-scrutin-8434.json \
  --image-url https://example.com/scrutin-8434.png \
  --dry-run
```

Publication reelle:

```bash
export META_IG_USER_ID="..."
export META_ACCESS_TOKEN="..."

PYTHONPATH=src python publish_instagram.py \
  --draft outputs/draft-scrutin-8434.json \
  --image-url https://ton-utilisateur.github.io/ton-repo/posts/scrutin-8434.png
```

Important: Instagram ne prend pas un fichier local. L'image doit etre disponible sur une URL HTTPS publique.
