from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from app.link_providers.base import LinkProviderError
from app.link_providers.http import ScrapedResponse
from app.link_providers.providers.mangafire import MangaFireProvider

_RESULT_HTML = """
<html><body>
  <header><a href="/manga/">Manga</a></header>
  <main>
    <a href="/manga/12345/berserk-abc">Berserk</a>
    <a href="/manga/67890/another-series-xyz">Another</a>
  </main>
</body></html>
"""

_NAV_ONLY_HTML = """
<html><body>
  <header><a href="/manga/">Manga</a></header>
  <main><p>No matches</p></main>
</body></html>
"""


def _scraped(html, url="https://mangafire.to/filter?keyword=x"):
    return ScrapedResponse(html=html, status_code=200, final_url=url)


def _item(title="Native", english_title="English"):
    return SimpleNamespace(title=title, english_title=english_title)


class MangaFireProviderTests(SimpleTestCase):
    """Unit tests for MangaFireProvider via flaresolverr-mediated HTML parsing."""

    @patch("app.link_providers.providers.mangafire.link_http.flaresolverr_get")
    def test_returns_first_manga_href(self, mock_get):
        mock_get.return_value = _scraped(_RESULT_HTML)
        result = MangaFireProvider().find(_item(english_title="Berserk"))
        self.assertIsNotNone(result)
        self.assertEqual(result.url, "https://mangafire.to/manga/12345/berserk-abc")
        self.assertEqual(result.site_id, "mangafire")

    @patch("app.link_providers.providers.mangafire.link_http.flaresolverr_get")
    def test_skips_index_link(self, mock_get):
        mock_get.return_value = _scraped(_NAV_ONLY_HTML)
        self.assertIsNone(MangaFireProvider().find(_item()))

    @patch("app.link_providers.providers.mangafire.link_http.flaresolverr_get")
    def test_returns_none_on_provider_error(self, mock_get):
        mock_get.side_effect = LinkProviderError("flaresolverr down")
        self.assertIsNone(MangaFireProvider().find(_item()))

    @patch("app.link_providers.providers.mangafire.link_http.flaresolverr_get")
    def test_falls_back_to_native_title(self, mock_get):
        mock_get.side_effect = [
            _scraped(_NAV_ONLY_HTML),
            _scraped(_RESULT_HTML),
        ]
        item = _item(title="Original", english_title="Translated")
        result = MangaFireProvider().find(item)
        self.assertIsNotNone(result)
        self.assertEqual(mock_get.call_count, 2)

    def test_requires_flaresolverr_flag(self):
        self.assertTrue(MangaFireProvider.requires_flaresolverr)
