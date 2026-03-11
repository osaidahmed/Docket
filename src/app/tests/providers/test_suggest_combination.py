from unittest.mock import patch

from django.test import TestCase

from app.models import MediaTypes, Sources
from app.providers import services


class SearchSuggestCombinationTests(TestCase):
    """Test result combination from multiple providers."""

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_returns_combined_results(self, mock_tmdb, mock_mal):
        """Combines results from TMDB multi + MAL anime + MAL manga."""
        mock_tmdb.return_value = [
            {
                "media_id": 100,
                "source": Sources.TMDB.value,
                "media_type": "tv",
                "title": "Narcos",
                "image": "http://example.com/narcos.jpg",
            },
        ]
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
                        "image": "http://example.com/naruto.jpg",
                        "synopsis": "",
                    },
                ],
            },
            {
                "page": 1,
                "total_results": 1,
                "total_pages": 1,
                "results": [
                    {
                        "media_id": 30,
                        "source": Sources.MAL.value,
                        "media_type": MediaTypes.MANGA.value,
                        "title": "Naruto Manga",
                        "image": "http://example.com/naruto_m.jpg",
                        "synopsis": "",
                    },
                ],
            },
        ]

        enabled = [
            MediaTypes.TV.value,
            MediaTypes.MOVIE.value,
            MediaTypes.ANIME.value,
            MediaTypes.MANGA.value,
        ]
        results = services.search_suggest_api("Naruto", enabled)

        sources_in_results = {r["source"] for r in results}
        self.assertIn(Sources.TMDB.value, sources_in_results)
        self.assertIn(Sources.MAL.value, sources_in_results)
        self.assertGreaterEqual(len(results), 3)

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_total_results_capped(self, mock_tmdb, mock_mal):
        """Combined results are capped at the limit."""
        mock_tmdb.return_value = [
            {
                "media_id": i,
                "source": Sources.TMDB.value,
                "media_type": "movie",
                "title": f"Movie {i}",
                "image": "http://example.com/m.jpg",
            }
            for i in range(5)
        ]
        mock_mal.side_effect = [
            {
                "page": 1,
                "total_results": 5,
                "total_pages": 1,
                "results": [
                    {
                        "media_id": 100 + i,
                        "source": Sources.MAL.value,
                        "media_type": MediaTypes.ANIME.value,
                        "title": f"Anime {i}",
                        "image": "http://example.com/a.jpg",
                        "synopsis": "",
                    }
                    for i in range(5)
                ],
            },
            {
                "page": 1,
                "total_results": 5,
                "total_pages": 1,
                "results": [
                    {
                        "media_id": 200 + i,
                        "source": Sources.MAL.value,
                        "media_type": MediaTypes.MANGA.value,
                        "title": f"Manga {i}",
                        "image": "http://example.com/mg.jpg",
                        "synopsis": "",
                    }
                    for i in range(5)
                ],
            },
        ]

        enabled = [
            MediaTypes.TV.value,
            MediaTypes.MOVIE.value,
            MediaTypes.ANIME.value,
            MediaTypes.MANGA.value,
        ]
        results = services.search_suggest_api("Test", enabled, limit=5)

        self.assertLessEqual(len(results), 5)

    @patch("app.providers.igdb.search")
    def test_game_results_in_suggest(self, mock_igdb):
        """Game results appear in suggestions when game type is enabled."""
        mock_igdb.return_value = {
            "page": 1,
            "total_results": 1,
            "total_pages": 1,
            "results": [
                {
                    "media_id": 1000,
                    "source": Sources.IGDB.value,
                    "media_type": MediaTypes.GAME.value,
                    "title": "Elden Ring",
                    "image": "http://example.com/elden.jpg",
                    "synopsis": "",
                },
            ],
        }

        results = services.search_suggest_api("Elden", [MediaTypes.GAME.value])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["media_type"], MediaTypes.GAME.value)
        self.assertEqual(results[0]["source"], Sources.IGDB.value)

    @patch("app.providers.comicvine.search")
    def test_comic_results_in_suggest(self, mock_cv):
        """Comic results appear in suggestions when comic type is enabled."""
        mock_cv.return_value = {
            "page": 1,
            "total_results": 1,
            "total_pages": 1,
            "results": [
                {
                    "media_id": 2000,
                    "source": Sources.COMICVINE.value,
                    "media_type": MediaTypes.COMIC.value,
                    "title": "Batman",
                    "image": "http://example.com/batman.jpg",
                    "synopsis": "",
                },
            ],
        }

        results = services.search_suggest_api("Batman", [MediaTypes.COMIC.value])

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["media_type"], MediaTypes.COMIC.value)
        self.assertEqual(results[0]["source"], Sources.COMICVINE.value)
