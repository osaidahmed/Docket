from django.test import TestCase

from app.models import MediaTypes
from app.providers import igdb


class IGDBBrowse(TestCase):
    """Test the IGDB browse API calls."""

    required_keys = {"media_id", "media_type", "title", "image", "synopsis"}

    def test_popular(self):
        """Test browsing popular games."""
        response = igdb.browse("popular", 1)

        self.assertGreater(len(response["results"]), 0)
        for item in response["results"]:
            self.assertTrue(all(key in item for key in self.required_keys))
            self.assertEqual(item["media_type"], MediaTypes.GAME.value)

    def test_top_rated(self):
        """Test browsing top rated games."""
        response = igdb.browse("top_rated", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_recent(self):
        """Test browsing recently released games."""
        response = igdb.browse("recent", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_anticipated(self):
        """Test browsing most anticipated games."""
        response = igdb.browse("anticipated", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_pagination(self):
        """Test that pagination returns different pages."""
        page1 = igdb.browse("popular", 1)
        page2 = igdb.browse("popular", 2)

        self.assertEqual(page1["page"], 1)
        self.assertEqual(page2["page"], 2)

    def test_response_format(self):
        """Test that the response has the expected keys."""
        response = igdb.browse("popular", 1)

        self.assertIn("page", response)
        self.assertIn("total_results", response)
        self.assertIn("total_pages", response)
        self.assertIn("results", response)
