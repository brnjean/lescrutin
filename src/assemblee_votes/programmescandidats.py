from __future__ import annotations

import html
import re
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from html.parser import HTMLParser
from urllib.parse import urljoin


INDEX_URL = "https://programmescandidats.fr/scrutins"
USER_AGENT = "lescrutin-bot/1.0 (+https://brnjean.github.io/lescrutin)"


@dataclass(frozen=True)
class ScrutinExplanation:
    description: str
    url: str


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.description = ""
        self._in_lead = False
        self.lead_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value or "" for key, value in attrs}
        if tag.lower() != "meta":
            if tag.lower() == "p" and "lead" in attr.get("class", "").split():
                self._in_lead = True
            return
        if attr.get("name", "").lower() == "description":
            self.description = html.unescape(attr.get("content", "")).strip()

    def handle_data(self, data: str) -> None:
        if self._in_lead:
            self.lead_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "p" and self._in_lead:
            self._in_lead = False

    @property
    def lead(self) -> str:
        return html.unescape(" ".join(" ".join(self.lead_parts).split())).strip()


def _download_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8")


@lru_cache(maxsize=1)
def _scrutins_index() -> str:
    return _download_text(INDEX_URL)


def _find_scrutin_url(numero: int) -> str | None:
    pattern = rf'href=["\']([^"\']*/scrutin/{numero}[^"\']*)["\']'
    match = re.search(pattern, _scrutins_index())
    if not match:
        return None
    return urljoin(INDEX_URL, html.unescape(match.group(1)))


def fetch_scrutin_explanation(numero: int) -> ScrutinExplanation | None:
    url = _find_scrutin_url(numero)
    if not url:
        return None
    parser = _MetaParser()
    parser.feed(_download_text(url))
    description = parser.lead or parser.description
    if not description or re.match(rf"Scrutin n°\s*{numero}\b", description):
        return None
    if "Aucun résumé en langage courant" in description:
        return None
    return ScrutinExplanation(description=description, url=url)
