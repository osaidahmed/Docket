from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase

from app.link_providers.base import LinkProviderError
from app.link_providers.providers.fastflix import FastFlixProvider


def _mock_response(html=None, status=200, url="https://fastflix.to/"):
    response = MagicMock()
    response.text = html or ""
    response.status_code = status
    response.url = url
    return response


def _item(media_type="movie", title="Test Title", english_title=""):
    return SimpleNamespace(
        media_type=media_type,
        title=title,
        english_title=english_title,
    )


class FastFlixProviderTests(SimpleTestCase):
    """Unit tests for FastFlixProvider direct + scrape strategies."""

    @patch("app.link_providers.providers.fastflix.link_http.get_session")
    def test_direct_url_hit_for_movie(self, mock_get_session):
        session = MagicMock()
        session.head.return_value = _mock_response(
            status=200,
            url="https://fastflix.to/movies/inception/",
        )
        mock_get_session.return_value = session

        result = FastFlixProvider().find(_item(title="Inception"))

        self.assertIsNotNone(result)
        self.assertEqual(result.url, "https://fastflix.to/movies/inception/")

    @patch("app.link_providers.providers.fastflix.link_http.get_session")
    def test_direct_url_hit_for_tv(self, mock_get_session):
        session = MagicMock()
        session.head.return_value = _mock_response(
            status=200,
            url="https://fastflix.to/tvshows/breaking-bad/",
        )
        mock_get_session.return_value = session

        result = FastFlixProvider().find(_item(media_type="tv", title="Breaking Bad"))

        self.assertIsNotNone(result)
        self.assertEqual(result.url, "https://fastflix.to/tvshows/breaking-bad/")

    @patch("app.link_providers.providers.fastflix.link_http.http_get")
    @patch("app.link_providers.providers.fastflix.link_http.get_session")
    def test_falls_back_to_search_when_direct_redirects(
        self,
        mock_get_session,
        mock_get,
    ):
        session = MagicMock()
        session.head.return_value = _mock_response(
            status=200,
            url="https://fastflix.to/movies/",
        )
        mock_get_session.return_value = session
        search_html = """
        <a href="https://fastflix.to/movies/inception/">Inception</a>
        """
        mock_get.return_value = _mock_response(html=search_html)

        result = FastFlixProvider().find(_item(title="Inception (alt)"))

        self.assertIsNotNone(result)
        self.assertEqual(result.url, "https://fastflix.to/movies/inception/")

    @patch("app.link_providers.providers.fastflix.link_http.http_get")
    @patch("app.link_providers.providers.fastflix.link_http.get_session")
    def test_search_skips_index_link(self, mock_get_session, mock_get):
        session = MagicMock()
        session.head.return_value = _mock_response(status=404)
        mock_get_session.return_value = session
        nav_only_html = """
        <header><a href="https://fastflix.to/movies/">Movies</a></header>
        """
        mock_get.return_value = _mock_response(html=nav_only_html)

        self.assertIsNone(FastFlixProvider().find(_item(title="Bogus Title")))

    @patch("app.link_providers.providers.fastflix.link_http.http_get")
    @patch("app.link_providers.providers.fastflix.link_http.get_session")
    def test_search_returns_none_on_provider_error(
        self,
        mock_get_session,
        mock_get,
    ):
        session = MagicMock()
        session.head.side_effect = requests.exceptions.RequestException("nope")
        mock_get_session.return_value = session
        mock_get.side_effect = LinkProviderError("network down")

        self.assertIsNone(FastFlixProvider().find(_item(title="Whatever")))

    def test_unsupported_media_type_returns_none(self):
        self.assertIsNone(FastFlixProvider().find(_item(media_type="anime")))
