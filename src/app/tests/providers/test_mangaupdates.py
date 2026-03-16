from unittest.mock import MagicMock, PropertyMock, patch

import requests
from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from app.models import MediaTypes, Sources
from app.providers import mangaupdates, services
from app.providers.mangaupdates import (
    get_authors,
    get_genres,
    get_max_progress,
    get_score,
    get_status,
    handle_error,
)


class HandleErrorTests(SimpleTestCase):
    """Test mangaupdates handle_error function."""

    def _make_http_error(self, status_code, json_data=None, json_raises=None):
        """Create a mock HTTPError with a mocked response."""
        mock_response = MagicMock()
        type(mock_response).status_code = PropertyMock(return_value=status_code)
        if json_raises:
            mock_response.json.side_effect = json_raises
        else:
            mock_response.json.return_value = json_data

        error = requests.exceptions.HTTPError(response=mock_response)
        error.response = mock_response
        return error

    def test_json_decode_error_raises_provider_api_error(self):
        """Test that JSONDecodeError raises ProviderAPIError."""
        error = self._make_http_error(
            status_code=500,
            json_raises=requests.exceptions.JSONDecodeError("msg", "doc", 0),
        )

        with self.assertRaises(services.ProviderAPIError):
            handle_error(error)

    def test_bad_request_with_empty_search_returns_empty_results(self):
        """Test 400 with search error about empty string returns empty results."""
        error = self._make_http_error(
            status_code=400,
            json_data={
                "context": {
                    "search": [{"errors": ['"" must have a length between 1 and 400']}]
                }
            },
        )

        result = handle_error(error)
        self.assertEqual(result, {"results": [], "total_hits": 0})

    def test_bad_request_without_search_error_raises(self):
        """Test 400 without matching search error raises ProviderAPIError."""
        error = self._make_http_error(
            status_code=400,
            json_data={"context": {"search": [{"errors": ["some other error"]}]}},
        )

        with self.assertRaises(services.ProviderAPIError):
            handle_error(error)

    def test_other_status_code_raises_provider_api_error(self):
        """Test that non-400 errors raise ProviderAPIError."""
        error = self._make_http_error(
            status_code=500,
            json_data={"error": "Internal Server Error"},
        )

        with self.assertRaises(services.ProviderAPIError):
            handle_error(error)


class MangaUpdatesBrowseTests(TestCase):

    def setUp(self):
        cache.clear()

    @patch("app.providers.services.api_request")
    def test_browse_releases(self, mock_api):
        mock_api.return_value = {
            "results": [
                {
                    "record": {
                        "series_id": 123,
                        "title": "Test Manga",
                        "image": {"url": {"original": "https://img/1.jpg"}},
                        "description": "A test manga",
                    }
                }
            ],
            "total_hits": 1,
        }
        data = mangaupdates.browse("releases", 1)
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["title"], "Test Manga")
        self.assertEqual(data["results"][0]["source"], Sources.MANGAUPDATES.value)

    @patch("app.providers.services.api_request")
    def test_browse_releases_orderby(self, mock_api):
        mock_api.return_value = {"results": [], "total_hits": 0}
        mangaupdates.browse("releases", 1)
        call_kwargs = mock_api.call_args[1]
        self.assertEqual(call_kwargs["params"]["orderby"], "year")

    @patch("app.providers.services.api_request")
    def test_browse_rating_orderby(self, mock_api):
        mock_api.return_value = {"results": [], "total_hits": 0}
        mangaupdates.browse("rating", 1)
        call_kwargs = mock_api.call_args[1]
        self.assertEqual(call_kwargs["params"]["orderby"], "rating")

    @patch("app.providers.services.api_request")
    def test_browse_cached(self, mock_api):
        mock_api.return_value = {"results": [], "total_hits": 0}
        mangaupdates.browse("releases", 1)
        mangaupdates.browse("releases", 1)
        mock_api.assert_called_once()


class MangaUpdatesHelperTests(SimpleTestCase):

    def test_get_genres_with_list(self):
        result = get_genres([{"genre": "Action"}, {"genre": "Drama"}])
        self.assertEqual(result, ["Action", "Drama"])

    def test_get_genres_empty(self):
        self.assertIsNone(get_genres(None))

    def test_get_authors_with_list(self):
        self.assertEqual(get_authors([{"name": "Author A"}]), ["Author A"])

    def test_get_authors_empty(self):
        self.assertIsNone(get_authors(None))

    def test_get_max_progress_completed(self):
        result = get_max_progress({"completed": True, "latest_chapter": 100})
        self.assertEqual(result, 100)

    def test_get_max_progress_ongoing(self):
        result = get_max_progress({"completed": False, "latest_chapter": 50})
        self.assertIsNone(result)

    def test_get_score_with_value(self):
        self.assertEqual(get_score(8.567), 8.6)

    def test_get_score_none(self):
        self.assertIsNone(get_score(None))

    def test_get_status_with_volumes(self):
        result = get_status("5 Volumes (Complete)")
        self.assertEqual(result, "5 Volumes (Complete)")

    def test_get_status_none(self):
        self.assertIsNone(get_status(None))
