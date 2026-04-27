import logging
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup

from app.link_providers import http as link_http
from app.link_providers.base import LinkProvider, LinkProviderError, LinkResult

logger = logging.getLogger(__name__)

BASE_URL = "https://mangafire.to"
SEARCH_URL = BASE_URL + "/filter?keyword={query}"


def _first_manga_href(html):
    """Return the href of the first /manga/... result anchor, or None."""
    soup = BeautifulSoup(html, "html.parser")
    needle = "/manga/"
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if href.startswith(needle) and href.rstrip("/") != needle.rstrip("/"):
            return href
    return None


class MangaFireProvider(LinkProvider):
    """Manga link provider for mangafire.to via flaresolverr-mediated scraping."""

    site_id = "mangafire"
    label = "MangaFire (mangafire.to)"
    media_types = ("manga",)
    requires_flaresolverr = True

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
            scraped = link_http.flaresolverr_get(
                SEARCH_URL.format(query=quote(query)),
            )
        except LinkProviderError:
            return None
        return _first_manga_href(scraped.html)
