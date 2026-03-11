from unittest.mock import patch

from django.test import TestCase

from app.models import MediaTypes, Sources
from app.providers import openlibrary


class OpenLibraryBrowse(TestCase):
    """Test the OpenLibrary browse API calls."""

    required_keys = {"media_id", "media_type", "title", "image", "synopsis"}

    def _mock_trending_response(self, page=1):
        return {
            "works": [
                {
                    "title": f"Book {i}",
                    "cover_i": 12345 + i,
                    "editions": {
                        "docs": [{"key": f"/books/OL{100 + i}M"}],
                    },
                }
                for i in range(3)
            ],
        }

    @patch("app.providers.openlibrary.cache")
    @patch("app.providers.services.api_request")
    def test_trending(self, mock_api, mock_cache):
        """Test browsing trending books."""
        mock_cache.get.return_value = None
        mock_api.return_value = self._mock_trending_response()

        response = openlibrary.browse("trending", 1)

        self.assertGreater(len(response["results"]), 0)
        for item in response["results"]:
            self.assertTrue(all(key in item for key in self.required_keys))
            self.assertEqual(item["media_type"], MediaTypes.BOOK.value)
            self.assertEqual(item["source"], Sources.OPENLIBRARY.value)

    @patch("app.providers.openlibrary.cache")
    @patch("app.providers.services.api_request")
    def test_pagination(self, mock_api, mock_cache):
        """Test that pagination returns different pages."""
        mock_cache.get.return_value = None
        mock_api.return_value = self._mock_trending_response()

        page1 = openlibrary.browse("trending", 1)

        mock_cache.get.return_value = None
        mock_api.return_value = self._mock_trending_response(page=2)

        page2 = openlibrary.browse("trending", 2)

        self.assertEqual(page1["page"], 1)
        self.assertEqual(page2["page"], 2)

    @patch("app.providers.openlibrary.cache")
    @patch("app.providers.services.api_request")
    def test_response_format(self, mock_api, mock_cache):
        """Test that the response has the expected keys."""
        mock_cache.get.return_value = None
        mock_api.return_value = self._mock_trending_response()

        response = openlibrary.browse("trending", 1)

        self.assertIn("page", response)
        self.assertIn("total_results", response)
        self.assertIn("total_pages", response)
        self.assertIn("results", response)
