import time
from unittest.mock import patch

from django.test import TestCase

from app.models import MediaTypes, Sources
from app.providers import services


class SearchSuggestErrorTests(TestCase):
    """Test error handling and timeout behavior."""

    def _all_types_enabled(self):
        return [
            MediaTypes.TV.value,
            MediaTypes.MOVIE.value,
            MediaTypes.ANIME.value,
            MediaTypes.MANGA.value,
        ]

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_handles_tmdb_failure(self, mock_tmdb, mock_mal):
        """TMDB failure doesn't crash; MAL results still returned."""
        mock_tmdb.side_effect = Exception("TMDB down")
        mock_mal.side_effect = [
            {
                "page": 1,
                "total_results": 1,
                "total_pages": 1,
                "results": [
                    {
                        "media_id": 20,
                        "source": Sources.MAL.value,
                        "media_type": MediaTypes.ANIME.value,
                        "title": "Naruto",
                        "image": "http://example.com/n.jpg",
                        "synopsis": "",
                    },
                ],
            },
            {
                "page": 1,
                "total_results": 0,
                "total_pages": 1,
                "results": [],
            },
        ]

        results = services.search_suggest_api("Naruto", self._all_types_enabled())

        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["source"], Sources.MAL.value)

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_handles_mal_failure(self, mock_tmdb, mock_mal):
        """MAL failure doesn't crash; TMDB results still returned."""
        mock_tmdb.return_value = [
            {
                "media_id": 100,
                "source": Sources.TMDB.value,
                "media_type": "tv",
                "title": "Narcos",
                "image": "http://example.com/narcos.jpg",
            },
        ]
        mock_mal.side_effect = Exception("MAL down")

        results = services.search_suggest_api("Nar", self._all_types_enabled())

        self.assertGreater(len(results), 0)
        self.assertEqual(results[0]["source"], Sources.TMDB.value)

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_handles_all_providers_failing(self, mock_tmdb, mock_mal):
        """All providers failing returns empty list, no crash."""
        mock_tmdb.side_effect = Exception("TMDB down")
        mock_mal.side_effect = Exception("MAL down")

        results = services.search_suggest_api("Naruto", self._all_types_enabled())

        self.assertEqual(results, [])

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_timeout_bounds_slow_providers(self, mock_tmdb, mock_mal):
        """Slow providers are abandoned at the timeout boundary."""

        def slow_tmdb(_query, _limit=5):
            time.sleep(services.SUGGEST_API_TIMEOUT + 3)
            return []

        mock_tmdb.side_effect = slow_tmdb
        mock_mal.side_effect = [
            {
                "page": 1,
                "total_results": 1,
                "total_pages": 1,
                "results": [
                    {
                        "media_id": 20,
                        "source": Sources.MAL.value,
                        "media_type": MediaTypes.ANIME.value,
                        "title": "Naruto",
                        "image": "http://example.com/n.jpg",
                        "synopsis": "",
                    },
                ],
            },
            {
                "page": 1,
                "total_results": 0,
                "total_pages": 1,
                "results": [],
            },
        ]

        start = time.monotonic()
        results = services.search_suggest_api("Naruto", self._all_types_enabled())
        elapsed = time.monotonic() - start

        self.assertGreater(len(results), 0)
        self.assertLess(elapsed, services.SUGGEST_API_TIMEOUT + 2)
