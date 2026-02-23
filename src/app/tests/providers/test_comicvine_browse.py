from django.test import TestCase

from app.models import MediaTypes
from app.providers import comicvine


class ComicVineBrowse(TestCase):
    """Test the ComicVine browse API calls."""

    required_keys = {"media_id", "media_type", "title", "image", "synopsis"}

    def test_recent(self):
        """Test browsing recently added comics."""
        response = comicvine.browse("recent", 1)

        self.assertGreater(len(response["results"]), 0)
        for item in response["results"]:
            self.assertTrue(all(key in item for key in self.required_keys))
            self.assertEqual(item["media_type"], MediaTypes.COMIC.value)

    def test_updated(self):
        """Test browsing recently updated comics."""
        response = comicvine.browse("updated", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_pagination(self):
        """Test that pagination returns different pages."""
        page1 = comicvine.browse("recent", 1)
        page2 = comicvine.browse("recent", 2)

        self.assertEqual(page1["page"], 1)
        self.assertEqual(page2["page"], 2)

    def test_response_format(self):
        """Test that the response has the expected keys."""
        response = comicvine.browse("recent", 1)

        self.assertIn("page", response)
        self.assertIn("total_results", response)
        self.assertIn("total_pages", response)
        self.assertIn("results", response)
