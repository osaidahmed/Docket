import logging
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup
from django.utils.text import slugify

from app.link_providers import http as link_http
from app.link_providers.base import LinkProvider, LinkProviderError, LinkResult

logger = logging.getLogger(__name__)

BASE_URL = "https://fastflix.to"
SEARCH_URL = BASE_URL + "/?s={query}"

_PATH_BY_TYPE = {"movie": "movies", "tv": "tvshows"}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Referer": BASE_URL + "/",
}


def _direct_url(media_type, title):
    path = _PATH_BY_TYPE.get(media_type)
    slug = slugify(title)
    if not path or not slug:
        return None
    return f"{BASE_URL}/{path}/{slug}/"


def _head_ok(url):
    """Return True only when the URL resolves to itself (not redirected to an index)."""
    try:
        response = link_http.get_session().head(
            url,
            headers=_HEADERS,
            timeout=10,
            allow_redirects=True,
        )
    except requests.exceptions.RequestException:
        return False
    if response.status_code != requests.codes.ok:
        return False
    return response.url.rstrip("/") == url.rstrip("/")


def _scrape_first_match(html, media_type):
    soup = BeautifulSoup(html, "html.parser")
    expected_path = _PATH_BY_TYPE.get(media_type)
    if not expected_path:
        return None
    needle = f"{BASE_URL}/{expected_path}/"
    needle_stripped = needle.rstrip("/")
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if href.startswith(needle) and href.rstrip("/") != needle_stripped:
            return href
    return None


class FastFlixProvider(LinkProvider):
    """Movie and TV provider for fastflix.to via slug URL + SSR fallback."""

    site_id = "fastflix"
    label = "FastFlix (fastflix.to)"
    media_types = ("movie", "tv")
    requires_flaresolverr = False

    def find(self, item):
        """Try direct slug URL first; on miss, scrape the search page."""
        if item.media_type not in _PATH_BY_TYPE:
            return None
        direct = _direct_url(item.media_type, item.title)
        if direct and _head_ok(direct):
            return LinkResult(url=direct, site_id=self.site_id)
        return self._search_fallback(item)

    def _search_fallback(self, item):
        query = item.english_title or item.title
        try:
            response = link_http.http_get(
                SEARCH_URL.format(query=quote(query)),
                headers=_HEADERS,
            )
        except LinkProviderError:
            return None
        href = _scrape_first_match(response.text, item.media_type)
        if not href:
            return None
        return LinkResult(url=urljoin(BASE_URL + "/", href), site_id=self.site_id)
