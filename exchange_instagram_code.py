from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request


TOKEN_URL = "https://api.instagram.com/oauth/access_token"
LONG_LIVED_TOKEN_URL = "https://graph.instagram.com/access_token"


def post_form(url: str, data: dict[str, str]) -> dict:
    req = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data).encode("utf-8"),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Erreur API {exc.code}:\n{body}") from exc


def get_json(url: str, params: dict[str, str]) -> dict:
    req = urllib.request.Request(f"{url}?{urllib.parse.urlencode(params)}", method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Erreur API {exc.code}:\n{body}") from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Echange un code Instagram OAuth contre un token.")
    parser.add_argument("--code", required=True)
    parser.add_argument(
        "--redirect-uri",
        default=os.getenv("INSTAGRAM_REDIRECT_URI", "https://brnjean.github.io/lescrutin/instagram-callback.html"),
    )
    args = parser.parse_args()

    app_id = os.getenv("META_APP_ID") or os.getenv("INSTAGRAM_APP_ID")
    app_secret = os.getenv("META_APP_SECRET") or os.getenv("INSTAGRAM_APP_SECRET")
    if not app_id or not app_secret:
        raise SystemExit("Variables manquantes: META_APP_ID et META_APP_SECRET")

    short_token = post_form(
        TOKEN_URL,
        {
            "client_id": app_id,
            "client_secret": app_secret,
            "grant_type": "authorization_code",
            "redirect_uri": args.redirect_uri,
            "code": args.code,
        },
    )
    print("Token court recu. Ne le partage pas.")
    print(json.dumps({key: short_token.get(key) for key in ("user_id", "permissions")}, indent=2))

    access_token = short_token["access_token"]
    long_token = get_json(
        LONG_LIVED_TOKEN_URL,
        {
            "grant_type": "ig_exchange_token",
            "client_secret": app_secret,
            "access_token": access_token,
        },
    )
    print("\nToken longue duree:")
    print(long_token["access_token"])
    print("\nA garder secret. Mets-le dans META_ACCESS_TOKEN.")


if __name__ == "__main__":
    main()
