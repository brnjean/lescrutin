from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request


GRAPH_VERSION = os.getenv("META_GRAPH_API_VERSION", "v22.0")
ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")


def get_json(base_url: str, path: str, params: dict[str, str]) -> dict:
    url = f"{base_url}/{GRAPH_VERSION}/{path.lstrip('/')}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Erreur API {exc.code} sur {url}:\n{body}") from exc


def main() -> None:
    if not ACCESS_TOKEN:
        raise SystemExit("Variable manquante: META_ACCESS_TOKEN")

    print("Test 1: Instagram API avec Instagram Login...")
    try:
        me = get_json(
            "https://graph.instagram.com",
            "/me",
            {
                "fields": "id,user_id,username,account_type",
                "access_token": ACCESS_TOKEN,
            },
        )
        print(json.dumps(me, ensure_ascii=False, indent=2))
        print("\nSi ce test marche, utilise comme META_IG_USER_ID la valeur `id` ci-dessus.")
        return
    except SystemExit as instagram_error:
        print(instagram_error)

    print("\nTest 2: Facebook Graph API via Page Facebook...")
    me = get_json(
        "https://graph.facebook.com",
        "/me/accounts",
        {
            "fields": "id,name,instagram_business_account{id,username}",
            "access_token": ACCESS_TOKEN,
        },
    )
    print(json.dumps(me, ensure_ascii=False, indent=2))
    print("\nSi ce test marche, utilise comme META_IG_USER_ID l'id dans `instagram_business_account`.")


if __name__ == "__main__":
    main()
