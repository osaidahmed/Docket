from unittest.mock import patch

from django.test import TestCase

from app.models import MediaTypes, Sources
from app.providers import services


class SearchSuggestRankingTests(TestCase):
    """Test ranking preferences and cross-provider deduplication."""

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_results_interleaved_by_type_preference(self, mock_tmdb, mock_mal):
        """One result per type is interleaved in enabled_types order."""
        mock_tmdb.return_value = [
            {
                "media_id": 100,
                "source": Sources.TMDB.value,
                "media_type": "movie",
                "title": "Movie A",
                "image": "http://example.com/m.jpg",
            },
            {
                "media_id": 101,
                "source": Sources.TMDB.value,
                "media_type": "tv",
                "title": "TV Show A",
                "image": "http://example.com/tv.jpg",
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
                        "title": "Anime A",
                        "image": "http://example.com/a.jpg",
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
                        "title": "Manga A",
                        "image": "http://example.com/mg.jpg",
                        "synopsis": "",
                    },
                ],
            },
        ]

        enabled = [
            MediaTypes.ANIME.value,
            MediaTypes.MANGA.value,
            MediaTypes.TV.value,
            MediaTypes.MOVIE.value,
        ]
        results = services.search_suggest_api("Test", enabled)

        result_types = [r["media_type"] for r in results]
        self.assertEqual(
            result_types,
            [MediaTypes.ANIME.value, MediaTypes.MANGA.value, "tv", "movie"],
        )

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_round_robin_diversity(self, mock_tmdb, mock_mal):
        """Multiple results per type are interleaved, not grouped."""
        mock_tmdb.return_value = [
            {
                "media_id": i,
                "source": Sources.TMDB.value,
                "media_type": "tv",
                "title": f"TV {i}",
                "image": "http://example.com/tv.jpg",
            }
            for i in range(3)
        ]
        mock_mal.side_effect = [
            {
                "page": 1,
                "total_results": 3,
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
                    for i in range(3)
                ],
            },
            {
                "page": 1,
                "total_results": 0,
                "total_pages": 1,
                "results": [],
            },
        ]

        enabled = [MediaTypes.ANIME.value, MediaTypes.TV.value]
        results = services.search_suggest_api("Test", enabled, limit=5)

        result_types = [r["media_type"] for r in results]
        self.assertEqual(
            result_types,
            [
                MediaTypes.ANIME.value,
                "tv",
                MediaTypes.ANIME.value,
                "tv",
                MediaTypes.ANIME.value,
            ],
        )

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_cross_provider_dedup_keeps_preferred_anime(self, mock_tmdb, mock_mal):
        """When anime ranks higher than TV, duplicate TV result is removed."""
        mock_tmdb.return_value = [
            {
                "media_id": 100,
                "source": Sources.TMDB.value,
                "media_type": "tv",
                "title": "Attack on Titan",
                "image": "http://example.com/aot_tv.jpg",
            },
        ]
        mock_mal.side_effect = [
            {
                "page": 1,
                "total_results": 1,
                "total_pages": 1,
                "results": [
                    {
                        "media_id": 16498,
                        "source": Sources.MAL.value,
                        "media_type": MediaTypes.ANIME.value,
                        "title": "Shingeki no Kyojin",
                        "english_title": "Attack on Titan",
                        "image": "http://example.com/aot_mal.jpg",
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

        enabled = [MediaTypes.ANIME.value, MediaTypes.TV.value]
        results = services.search_suggest_api("Attack on Titan", enabled)

        media_types = [r["media_type"] for r in results]
        self.assertIn(MediaTypes.ANIME.value, media_types)
        self.assertNotIn("tv", media_types)

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_cross_provider_dedup_keeps_preferred_tv(self, mock_tmdb, mock_mal):
        """When TV ranks higher than anime, duplicate anime result is removed."""
        mock_tmdb.return_value = [
            {
                "media_id": 100,
                "source": Sources.TMDB.value,
                "media_type": "tv",
                "title": "Attack on Titan",
                "image": "http://example.com/aot_tv.jpg",
            },
        ]
        mock_mal.side_effect = [
            {
                "page": 1,
                "total_results": 1,
                "total_pages": 1,
                "results": [
                    {
                        "media_id": 16498,
                        "source": Sources.MAL.value,
                        "media_type": MediaTypes.ANIME.value,
                        "title": "Shingeki no Kyojin",
                        "english_title": "Attack on Titan",
                        "image": "http://example.com/aot_mal.jpg",
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

        enabled = [MediaTypes.TV.value, MediaTypes.ANIME.value]
        results = services.search_suggest_api("Attack on Titan", enabled)

        media_types = [r["media_type"] for r in results]
        self.assertIn("tv", media_types)
        self.assertNotIn(MediaTypes.ANIME.value, media_types)

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_cross_provider_dedup_matches_mal_title(self, mock_tmdb, mock_mal):
        """Dedup matches when TMDB title equals MAL's main (Japanese) title."""
        mock_tmdb.return_value = [
            {
                "media_id": 100,
                "source": Sources.TMDB.value,
                "media_type": "tv",
                "title": "Naruto",
                "image": "http://example.com/naruto_tv.jpg",
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
                        "english_title": "",
                        "image": "http://example.com/naruto_mal.jpg",
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

        enabled = [MediaTypes.ANIME.value, MediaTypes.TV.value]
        results = services.search_suggest_api("Naruto", enabled)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["media_type"], MediaTypes.ANIME.value)

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_cross_provider_dedup_ignores_movie_types(self, mock_tmdb, mock_mal):
        """Movie results with same title as anime are NOT deduped."""
        mock_tmdb.return_value = [
            {
                "media_id": 100,
                "source": Sources.TMDB.value,
                "media_type": "movie",
                "title": "Your Name",
                "image": "http://example.com/yn_movie.jpg",
            },
        ]
        mock_mal.side_effect = [
            {
                "page": 1,
                "total_results": 1,
                "total_pages": 1,
                "results": [
                    {
                        "media_id": 32281,
                        "source": Sources.MAL.value,
                        "media_type": MediaTypes.ANIME.value,
                        "title": "Kimi no Na wa.",
                        "english_title": "Your Name",
                        "image": "http://example.com/yn_mal.jpg",
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

        enabled = [
            MediaTypes.ANIME.value,
            MediaTypes.MOVIE.value,
            MediaTypes.TV.value,
        ]
        results = services.search_suggest_api("Your Name", enabled)

        media_types = [r["media_type"] for r in results]
        self.assertIn("movie", media_types)
        self.assertIn(MediaTypes.ANIME.value, media_types)

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_cross_provider_dedup_case_insensitive(self, mock_tmdb, mock_mal):
        """Title matching is case-insensitive."""
        mock_tmdb.return_value = [
            {
                "media_id": 100,
                "source": Sources.TMDB.value,
                "media_type": "tv",
                "title": "ATTACK ON TITAN",
                "image": "http://example.com/aot.jpg",
            },
        ]
        mock_mal.side_effect = [
            {
                "page": 1,
                "total_results": 1,
                "total_pages": 1,
                "results": [
                    {
                        "media_id": 16498,
                        "source": Sources.MAL.value,
                        "media_type": MediaTypes.ANIME.value,
                        "title": "Shingeki no Kyojin",
                        "english_title": "attack on titan",
                        "image": "http://example.com/aot_mal.jpg",
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

        enabled = [MediaTypes.ANIME.value, MediaTypes.TV.value]
        results = services.search_suggest_api("attack on titan", enabled)

        self.assertEqual(len(results), 1)
