from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from app.link_providers.base import LinkProviderError
from app.link_providers.providers.anikai import AnikaiProvider


def _mock_response(html):
    response = MagicMock()
    response.text = html
    return response


_RESULT_HTML = """
<html><body>
  <nav><a href="/genres/action">Action</a></nav>
  <main>
    <a href="/watch/naruto-9r5k">Naruto</a>
    <a href="/watch/boruto-naruto-next-generations-p125">Boruto</a>
  </main>
</body></html>
"""

_EMPTY_HTML = """
<html><body>
  <nav><a href="/genres/action">Action</a></nav>
  <main><p>No results found</p></main>
</body></html>
"""


def _item(title="Title", english_title="English"):
    return SimpleNamespace(title=title, english_title=english_title)


class AnikaiProviderTests(SimpleTestCase):
    """Unit tests for AnikaiProvider against mocked SSR HTML."""

    @patch("app.link_providers.providers.anikai.link_http.http_get")
    def test_returns_first_watch_href(self, mock_get):
        mock_get.return_value = _mock_response(_RESULT_HTML)
        result = AnikaiProvider().find(_item(english_title="Naruto"))
        self.assertIsNotNone(result)
        self.assertEqual(result.url, "https://anikai.to/watch/naruto-9r5k")
        self.assertEqual(result.site_id, "anikai")

    @patch("app.link_providers.providers.anikai.link_http.http_get")
    def test_returns_none_when_no_results(self, mock_get):
        mock_get.return_value = _mock_response(_EMPTY_HTML)
        self.assertIsNone(AnikaiProvider().find(_item()))

    @patch("app.link_providers.providers.anikai.link_http.http_get")
    def test_returns_none_on_provider_error(self, mock_get):
        mock_get.side_effect = LinkProviderError("network down")
        self.assertIsNone(AnikaiProvider().find(_item()))

    @patch("app.link_providers.providers.anikai.link_http.http_get")
    def test_falls_back_to_native_title(self, mock_get):
        mock_get.side_effect = [
            _mock_response(_EMPTY_HTML),
            _mock_response(_RESULT_HTML),
        ]
        item = _item(title="Shingeki no Kyojin", english_title="Attack on Titan")
        result = AnikaiProvider().find(item)
        self.assertIsNotNone(result)
        self.assertEqual(mock_get.call_count, 2)

    @patch("app.link_providers.providers.anikai.link_http.http_get")
    def test_skips_non_watch_anchors(self, mock_get):
        html = """
        <a href="/login">Login</a>
        <a href="/genres/action">Action</a>
        <a href="/watch/real-anime-abc1">Real Anime</a>
        """
        mock_get.return_value = _mock_response(html)
        result = AnikaiProvider().find(_item(english_title="Anything"))
        self.assertEqual(result.url, "https://anikai.to/watch/real-anime-abc1")
