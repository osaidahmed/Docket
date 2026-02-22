from django.test import TestCase

from app.models import MediaTypes
from app.providers import tmdb


class TMDBBrowse(TestCase):
    """Test the TMDB browse API calls."""

    required_keys = {"media_id", "media_type", "title", "image", "synopsis"}

    def test_tv_trending(self):
        """Test browsing trending TV shows."""
        response = tmdb.browse(MediaTypes.TV.value, "trending", 1)

        self.assertGreater(len(response["results"]), 0)
        for item in response["results"]:
            self.assertTrue(all(key in item for key in self.required_keys))
            self.assertEqual(item["media_type"], MediaTypes.TV.value)

    def test_tv_popular(self):
        """Test browsing popular TV shows."""
        response = tmdb.browse(MediaTypes.TV.value, "popular", 1)

        self.assertGreater(len(response["results"]), 0)
        for item in response["results"]:
            self.assertTrue(all(key in item for key in self.required_keys))

    def test_tv_top_rated(self):
        """Test browsing top rated TV shows."""
        response = tmdb.browse(MediaTypes.TV.value, "top_rated", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_tv_on_the_air(self):
        """Test browsing currently airing TV shows."""
        response = tmdb.browse(MediaTypes.TV.value, "on_the_air", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_movie_trending(self):
        """Test browsing trending movies."""
        response = tmdb.browse(MediaTypes.MOVIE.value, "trending", 1)

        self.assertGreater(len(response["results"]), 0)
        for item in response["results"]:
            self.assertTrue(all(key in item for key in self.required_keys))
            self.assertEqual(item["media_type"], MediaTypes.MOVIE.value)

    def test_movie_popular(self):
        """Test browsing popular movies."""
        response = tmdb.browse(MediaTypes.MOVIE.value, "popular", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_movie_top_rated(self):
        """Test browsing top rated movies."""
        response = tmdb.browse(MediaTypes.MOVIE.value, "top_rated", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_movie_now_playing(self):
        """Test browsing now playing movies."""
        response = tmdb.browse(MediaTypes.MOVIE.value, "now_playing", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_pagination(self):
        """Test that pagination returns different pages."""
        page1 = tmdb.browse(MediaTypes.TV.value, "popular", 1)
        page2 = tmdb.browse(MediaTypes.TV.value, "popular", 2)

        self.assertEqual(page1["page"], 1)
        self.assertEqual(page2["page"], 2)
        self.assertGreater(page1["total_pages"], 1)

    def test_response_format(self):
        """Test that the response has the expected keys."""
        response = tmdb.browse(MediaTypes.MOVIE.value, "popular", 1)

        self.assertIn("page", response)
        self.assertIn("total_results", response)
        self.assertIn("total_pages", response)
        self.assertIn("results", response)
