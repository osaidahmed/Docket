from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from app.models import MediaTypes
from app.providers import hardcover, services
from app.tests.providers._http_error_helpers import make_http_error


class HardcoverBrowse(TestCase):
    """Test the Hardcover browse API calls."""

    required_keys = {"media_id", "media_type", "title", "image", "synopsis"}

    def test_popular(self):
        """Test browsing popular books."""
        response = hardcover.browse("popular", 1)

        self.assertGreater(len(response["results"]), 0)
        for item in response["results"]:
            self.assertTrue(all(key in item for key in self.required_keys))
            self.assertEqual(item["media_type"], MediaTypes.BOOK.value)

    def test_top_rated(self):
        """Test browsing top rated books."""
        response = hardcover.browse("top_rated", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_pagination(self):
        """Test that pagination returns different pages."""
        page1 = hardcover.browse("popular", 1)
        page2 = hardcover.browse("popular", 2)

        self.assertEqual(page1["page"], 1)
        self.assertEqual(page2["page"], 2)

    def test_response_format(self):
        """Test that the response has the expected keys."""
        response = hardcover.browse("popular", 1)

        self.assertIn("page", response)
        self.assertIn("total_results", response)
        self.assertIn("total_pages", response)
        self.assertIn("results", response)


class HardcoverErrorAndEdgeCases(TestCase):
    def setUp(self):
        cache.clear()

    @patch("app.providers.services.api_request")
    def test_hardcover_request_http_error_propagates(self, mock_api):
        mock_api.side_effect = make_http_error(500, {"error": "boom"})
        with self.assertRaises(services.ProviderAPIError):
            hardcover._hardcover_request("query {}", {})

    @patch("app.providers.services.api_request")
    def test_book_not_found_raises_404(self, mock_api):
        mock_api.return_value = {"data": {"books_by_pk": None}}
        with self.assertRaises(services.ProviderAPIError) as ctx:
            hardcover.book("999")
        self.assertEqual(ctx.exception.status_code, 404)

    @patch("app.providers.services.api_request")
    def test_browse_partial_page_total_exact(self, mock_api):
        mock_api.return_value = {
            "data": {
                "books": [
                    {
                        "id": 1,
                        "title": "Solo Book",
                        "cached_image": "http://img/x.jpg",
                        "description": "desc",
                    },
                ],
            },
        }
        data = hardcover.browse("popular", 1)
        self.assertEqual(data["total_results"], 1)
        self.assertEqual(len(data["results"]), 1)
