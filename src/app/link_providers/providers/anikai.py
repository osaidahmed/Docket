from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from app.link_providers import http as link_http
from app.link_providers.base import LinkProvider, LinkProviderError, LinkResult

BASE_URL = "https://anikai.to"
SEARCH_URL = BASE_URL + "/browser?keyword={query}"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL + "/",
}


def _first_watch_href(html):
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if href.startswith("/watch/"):
            return href
    return None


class AnikaiProvider(LinkProvider):
    """Anime link provider for anikai.to via SSR HTML scraping."""

    site_id = "anikai"
    label = "AniKai (anikai.to)"
    media_types = ("anime",)

    def find(self, item):
        """Search by english_title (preferred) then native title."""
        query = item.english_title or item.title
        href = self._search(query)
        if not href and item.english_title and item.english_title != item.title:
            href = self._search(item.title)
        if not href:
            return None
        return LinkResult(url=urljoin(BASE_URL + "/", href), site_id=self.site_id)

    def _search(self, query):
        try:
            response = link_http.http_get(
                SEARCH_URL.format(query=quote(query)),
                headers=_HEADERS,
            )
        except LinkProviderError:
            return None
        return _first_watch_href(response.text)
