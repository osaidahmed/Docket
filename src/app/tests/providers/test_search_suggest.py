import time
from unittest.mock import patch

from django.test import TestCase

from app.models import MediaTypes, Sources
from app.providers import services, tmdb


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


class SearchSuggestServiceTests(TestCase):
    """Test the services.search_suggest_api() function."""

    def _all_types_enabled(self):
        return [
            MediaTypes.TV.value,
            MediaTypes.MOVIE.value,
            MediaTypes.ANIME.value,
            MediaTypes.MANGA.value,
        ]

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

        results = services.search_suggest_api("Naruto", self._all_types_enabled())

        sources_in_results = {r["source"] for r in results}
        self.assertIn(Sources.TMDB.value, sources_in_results)
        self.assertIn(Sources.MAL.value, sources_in_results)
        self.assertGreaterEqual(len(results), 3)

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_respects_enabled_types(self, mock_tmdb, mock_mal):
        """Disabled types are not queried."""
        mock_tmdb.return_value = []
        mock_mal.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        # Only manga enabled (no TV, Movie, Anime)
        services.search_suggest_api("Test", [MediaTypes.MANGA.value])

        mock_tmdb.assert_not_called()
        # MAL should be called once for manga only
        self.assertEqual(mock_mal.call_count, 1)

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_deduplication_by_media_id_and_source(self, mock_tmdb, mock_mal):
        """Duplicate (media_id, source) pairs are removed."""
        mock_tmdb.return_value = [
            {
                "media_id": 20,
                "source": Sources.TMDB.value,
                "media_type": "tv",
                "title": "Show A",
                "image": "http://example.com/a.jpg",
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
                        "source": Sources.TMDB.value,
                        "media_type": "tv",
                        "title": "Show A Duplicate",
                        "image": "http://example.com/a2.jpg",
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

        results = services.search_suggest_api("Show", self._all_types_enabled())

        keys = [(str(r["media_id"]), r["source"]) for r in results]
        self.assertEqual(len(keys), len(set(keys)))

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

        results = services.search_suggest_api(
            "Test", self._all_types_enabled(), limit=5
        )

        self.assertLessEqual(len(results), 5)

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_excludes_local_keys(self, mock_tmdb, mock_mal):
        """Items matching local_keys are excluded from results."""
        mock_tmdb.return_value = [
            {
                "media_id": 100,
                "source": Sources.TMDB.value,
                "media_type": "tv",
                "title": "Narcos",
                "image": "http://example.com/narcos.jpg",
            },
            {
                "media_id": 200,
                "source": Sources.TMDB.value,
                "media_type": "movie",
                "title": "Narnia",
                "image": "http://example.com/narnia.jpg",
            },
        ]
        mock_mal.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        local_keys = {("100", Sources.TMDB.value)}
        results = services.search_suggest_api(
            "Nar",
            [MediaTypes.TV.value, MediaTypes.MOVIE.value],
            local_keys=local_keys,
        )

        result_ids = [(str(r["media_id"]), r["source"]) for r in results]
        self.assertNotIn(("100", Sources.TMDB.value), result_ids)
        self.assertIn(("200", Sources.TMDB.value), result_ids)

    def test_empty_query_returns_empty(self):
        """Empty or whitespace query returns empty list."""
        result = services.search_suggest_api("", self._all_types_enabled())
        self.assertEqual(result, [])

        result = services.search_suggest_api("   ", self._all_types_enabled())
        self.assertEqual(result, [])

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
        # Round-robin: anime, tv, anime, tv, anime
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
