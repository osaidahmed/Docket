from unittest.mock import patch

from django.test import TestCase

from app.models import Sources
from app.providers import tmdb


class TMDBSearchMultiTests(TestCase):
    """Test the tmdb.search_multi() function."""

    @patch("app.providers.services.api_request")
    def test_returns_tv_and_movie_results(self, mock_api):
        """search_multi returns both TV and movie results."""
        mock_api.return_value = {
            "page": 1,
            "total_results": 3,
            "results": [
                {
                    "id": 1399,
                    "media_type": "tv",
                    "name": "Breaking Bad",
                    "poster_path": "/path.jpg",
                    "overview": "A show",
                },
                {
                    "id": 550,
                    "media_type": "movie",
                    "title": "Fight Club",
                    "poster_path": "/fc.jpg",
                    "overview": "A movie",
                },
            ],
        }

        results = tmdb.search_multi("Breaking")

        media_types = {r["media_type"] for r in results}
        self.assertIn("tv", media_types)
        self.assertIn("movie", media_types)
        self.assertEqual(len(results), 2)

    @patch("app.providers.services.api_request")
    def test_filters_out_person_results(self, mock_api):
        """Person results from TMDB multi endpoint are excluded."""
        mock_api.return_value = {
            "page": 1,
            "total_results": 3,
            "results": [
                {
                    "id": 1399,
                    "media_type": "tv",
                    "name": "Breaking Bad",
                    "poster_path": "/path.jpg",
                },
                {
                    "id": 17419,
                    "media_type": "person",
                    "name": "Bryan Cranston",
                    "profile_path": "/profile.jpg",
                },
                {
                    "id": 550,
                    "media_type": "movie",
                    "title": "Fight Club",
                    "poster_path": "/fc.jpg",
                },
            ],
        }

        results = tmdb.search_multi("Breaking")

        for result in results:
            self.assertNotEqual(result["media_type"], "person")
        self.assertEqual(len(results), 2)

    @patch("app.providers.services.api_request")
    def test_result_format(self, mock_api):
        """Each result has all required keys."""
        mock_api.return_value = {
            "page": 1,
            "total_results": 1,
            "results": [
                {
                    "id": 1399,
                    "media_type": "tv",
                    "name": "Breaking Bad",
                    "poster_path": "/path.jpg",
                },
            ],
        }

        results = tmdb.search_multi("Breaking")

        required_keys = {"media_id", "source", "media_type", "title", "image"}
        for result in results:
            self.assertTrue(
                all(key in result for key in required_keys),
                f"Missing keys: {required_keys - set(result.keys())}",
            )
        self.assertEqual(results[0]["source"], Sources.TMDB.value)

    @patch("app.providers.services.api_request")
    def test_capped_at_limit(self, mock_api):
        """Results are capped at the specified limit."""
        mock_api.return_value = {
            "page": 1,
            "total_results": 20,
            "results": [
                {
                    "id": i,
                    "media_type": "movie",
                    "title": f"Movie {i}",
                    "poster_path": f"/m{i}.jpg",
                }
                for i in range(20)
            ],
        }

        results = tmdb.search_multi("Movie", limit=5)

        self.assertLessEqual(len(results), 5)

    @patch("app.providers.services.api_request")
    def test_uses_cache(self, mock_api):
        """Second call with same query hits cache, not the API."""
        mock_api.return_value = {
            "page": 1,
            "total_results": 1,
            "results": [
                {
                    "id": 1399,
                    "media_type": "tv",
                    "name": "Breaking Bad",
                    "poster_path": "/path.jpg",
                },
            ],
        }

        tmdb.search_multi("CacheTest", limit=5)
        tmdb.search_multi("CacheTest", limit=5)

        mock_api.assert_called_once()
