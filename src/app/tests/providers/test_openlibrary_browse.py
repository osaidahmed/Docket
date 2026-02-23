from django.test import TestCase

from app.models import MediaTypes
from app.providers import openlibrary


class OpenLibraryBrowse(TestCase):
    """Test the OpenLibrary browse API calls."""

    required_keys = {"media_id", "media_type", "title", "image", "synopsis"}

    def test_trending(self):
        """Test browsing trending books."""
        response = openlibrary.browse("trending", 1)

        self.assertGreater(len(response["results"]), 0)
        for item in response["results"]:
            self.assertTrue(all(key in item for key in self.required_keys))
            self.assertEqual(item["media_type"], MediaTypes.BOOK.value)

    def test_pagination(self):
        """Test that pagination returns different pages."""
        page1 = openlibrary.browse("trending", 1)
        page2 = openlibrary.browse("trending", 2)

        self.assertEqual(page1["page"], 1)
        self.assertEqual(page2["page"], 2)

    def test_response_format(self):
        """Test that the response has the expected keys."""
        response = openlibrary.browse("trending", 1)

        self.assertIn("page", response)
        self.assertIn("total_results", response)
        self.assertIn("total_pages", response)
        self.assertIn("results", response)
