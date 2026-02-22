from django.test import TestCase

from app.models import MediaTypes
from app.providers import mal


class MALBrowse(TestCase):
    """Test the MAL browse API calls."""

    required_keys = {"media_id", "media_type", "title", "image", "synopsis"}

    def test_anime_top_rated(self):
        """Test browsing top rated anime."""
        response = mal.browse(MediaTypes.ANIME.value, "all", 1)

        self.assertGreater(len(response["results"]), 0)
        for item in response["results"]:
            self.assertTrue(all(key in item for key in self.required_keys))
            self.assertEqual(item["media_type"], MediaTypes.ANIME.value)

    def test_anime_airing(self):
        """Test browsing currently airing anime."""
        response = mal.browse(MediaTypes.ANIME.value, "airing", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_anime_upcoming(self):
        """Test browsing upcoming anime."""
        response = mal.browse(MediaTypes.ANIME.value, "upcoming", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_anime_bypopularity(self):
        """Test browsing anime by popularity."""
        response = mal.browse(MediaTypes.ANIME.value, "bypopularity", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_manga_top_rated(self):
        """Test browsing top rated manga."""
        response = mal.browse(MediaTypes.MANGA.value, "all", 1)

        self.assertGreater(len(response["results"]), 0)
        for item in response["results"]:
            self.assertTrue(all(key in item for key in self.required_keys))
            self.assertEqual(item["media_type"], MediaTypes.MANGA.value)

    def test_manga_bypopularity(self):
        """Test browsing manga by popularity."""
        response = mal.browse(MediaTypes.MANGA.value, "bypopularity", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_manga_manga(self):
        """Test browsing top manga (manga-only ranking)."""
        response = mal.browse(MediaTypes.MANGA.value, "manga", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_manga_novels(self):
        """Test browsing top novels."""
        response = mal.browse(MediaTypes.MANGA.value, "novels", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_pagination(self):
        """Test that pagination returns different pages."""
        page1 = mal.browse(MediaTypes.ANIME.value, "all", 1)
        page2 = mal.browse(MediaTypes.ANIME.value, "all", 2)

        self.assertEqual(page1["page"], 1)
        self.assertEqual(page2["page"], 2)

    def test_response_format(self):
        """Test that the response has the expected keys."""
        response = mal.browse(MediaTypes.ANIME.value, "all", 1)

        self.assertIn("page", response)
        self.assertIn("total_results", response)
        self.assertIn("total_pages", response)
        self.assertIn("results", response)

    def test_seasonal_browse(self):
        """Test browsing seasonal anime."""
        response = mal.browse_seasonal(2024, "fall", 1)

        self.assertGreater(len(response["results"]), 0)
        for item in response["results"]:
            self.assertTrue(all(key in item for key in self.required_keys))
            self.assertEqual(item["media_type"], MediaTypes.ANIME.value)
