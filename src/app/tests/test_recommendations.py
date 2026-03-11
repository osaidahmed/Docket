from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from app.models import Anime, Item, Manga, MediaTypes, Movie, Sources, Status
from app.services.recommendations import (
    _add_title_variants,
    _matches_cross_media,
    compute_recommendations,
    get_cache_key,
    get_progress,
    get_progress_key,
)


class CacheKeyTests(TestCase):
    def test_get_cache_key(self):
        result = get_cache_key(1, "movie")
        self.assertEqual(result, "recommendations:1:movie")

    def test_get_progress_key(self):
        result = get_progress_key(1, "movie")
        self.assertEqual(result, "recommendations_progress:1:movie")

    def test_get_progress_none(self):
        cache.clear()
        result = get_progress(1, "movie")
        self.assertIsNone(result)

    def test_get_progress_set(self):
        cache.set("recommendations_progress:1:movie", {"current": 5, "total": 10})
        result = get_progress(1, "movie")
        self.assertEqual(result, {"current": 5, "total": 10})


class TitleVariantTests(TestCase):
    def test_add_title_variants_simple(self):
        title_set = set()
        _add_title_variants(title_set, "Attack on Titan")
        self.assertIn("attack on titan", title_set)

    def test_add_title_variants_with_colon(self):
        title_set = set()
        _add_title_variants(title_set, "Attack on Titan: Final Season")
        self.assertIn("attack on titan: final season", title_set)
        self.assertIn("attack on titan", title_set)

    def test_matches_cross_media_empty(self):
        self.assertFalse(_matches_cross_media("test", set()))

    def test_matches_cross_media_direct_match(self):
        self.assertTrue(_matches_cross_media("test", {"test"}))

    def test_matches_cross_media_no_match(self):
        self.assertFalse(_matches_cross_media("other", {"test"}))

    def test_matches_cross_media_base_title(self):
        self.assertTrue(_matches_cross_media("test: season 2", {"test"}))

    def test_matches_cross_media_base_no_match(self):
        self.assertFalse(_matches_cross_media("other: season 2", {"test"}))


class ComputeRecommendationsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="rec_test", password="12345"
        )

        cls.movie_item_1 = Item.objects.create(
            media_id="100",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Movie One",
            image="http://example.com/1.jpg",
        )
        Movie.objects.create(
            item=cls.movie_item_1,
            user=cls.user,
            status=Status.PLANNING.value,
        )

        cls.movie_item_2 = Item.objects.create(
            media_id="200",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Movie Two",
            image="http://example.com/2.jpg",
        )
        Movie.objects.create(
            item=cls.movie_item_2,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
        )

        cls.movie_item_3 = Item.objects.create(
            media_id="300",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Movie Three",
            image="http://example.com/3.jpg",
        )
        Movie.objects.create(
            item=cls.movie_item_3,
            user=cls.user,
            status=Status.DROPPED.value,
        )

    def setUp(self):
        cache.clear()

    @patch("app.services.recommendations.provider_services.get_media_metadata")
    def test_compute_recommendations_basic(self, mock_metadata):
        mock_metadata.return_value = {
            "genres": ["Action", "Drama"],
            "related": {
                "recommendations": [
                    {
                        "media_id": "999",
                        "source": Sources.TMDB.value,
                        "title": "Recommended Movie",
                    },
                ],
            },
        }

        result = compute_recommendations(self.user.id, MediaTypes.MOVIE.value)
        self.assertIn("active", result)
        self.assertIn("full", result)
        self.assertIn("genres", result)

    @patch("app.services.recommendations.provider_services.get_media_metadata")
    def test_compute_recommendations_dedup_titles(self, mock_metadata):
        recs = [
            {
                "media_id": "999",
                "source": Sources.TMDB.value,
                "title": "Same Title",
            },
            {
                "media_id": "998",
                "source": Sources.MAL.value,
                "title": "Same Title",
            },
            {
                "media_id": "997",
                "source": Sources.TMDB.value,
                "title": "Different Title",
            },
        ]
        mock_metadata.return_value = {
            "genres": ["Action"],
            "related": {"recommendations": recs},
        }

        result = compute_recommendations(self.user.id, MediaTypes.MOVIE.value)
        all_titles = [r["title"] for r in result["active"] + result["full"]]
        self.assertEqual(all_titles.count("Same Title"), 1)
        self.assertIn("Different Title", all_titles)

    @patch("app.services.recommendations.provider_services.get_media_metadata")
    def test_compute_recommendations_genre_sections(self, mock_metadata):
        recs = [
            {
                "media_id": str(i),
                "source": Sources.TMDB.value,
                "title": f"Genre Rec {i}",
            }
            for i in range(500, 510)
        ]
        mock_metadata.return_value = {
            "genres": ["Action", "Drama"],
            "related": {"recommendations": recs},
        }

        result = compute_recommendations(self.user.id, MediaTypes.MOVIE.value)
        all_recs = result["active"] + result["full"]
        genre_recs = result["genres"]
        self.assertGreater(len(all_recs), 0)
        if genre_recs:
            self.assertEqual(genre_recs[0]["name"], "Action")

    @patch("app.services.recommendations.provider_services.get_media_metadata")
    def test_compute_recommendations_respects_max(self, mock_metadata):
        recs = [
            {
                "media_id": str(i),
                "source": Sources.TMDB.value,
                "title": f"Rec {i}",
            }
            for i in range(1000, 1050)
        ]
        mock_metadata.return_value = {
            "genres": ["Sci-Fi"],
            "related": {"recommendations": recs},
        }

        result = compute_recommendations(self.user.id, MediaTypes.MOVIE.value)
        self.assertLessEqual(len(result["active"]), 20)
        self.assertLessEqual(len(result["full"]), 20)
        self.assertEqual(len(result["full"]), 20)

    @patch("app.services.recommendations.provider_services.get_media_metadata")
    def test_compute_recommendations_dedup_same_title_different_keys(
        self, mock_metadata
    ):
        mock_metadata.side_effect = [
            {
                "genres": ["Action"],
                "related": {
                    "recommendations": [
                        {
                            "media_id": "800",
                            "source": Sources.TMDB.value,
                            "title": "Duplicate Movie",
                        },
                    ],
                },
            },
            {
                "genres": ["Action"],
                "related": {
                    "recommendations": [
                        {
                            "media_id": "801",
                            "source": Sources.TMDB.value,
                            "title": "Duplicate Movie",
                        },
                    ],
                },
            },
        ]

        result = compute_recommendations(self.user.id, MediaTypes.MOVIE.value)
        all_titles = [r["title"] for r in result["active"] + result["full"]]
        self.assertEqual(all_titles.count("Duplicate Movie"), 1)

    @patch("app.services.recommendations.provider_services.get_media_metadata")
    def test_compute_recommendations_metadata_failure(self, mock_metadata):
        mock_metadata.side_effect = Exception("API error")

        result = compute_recommendations(self.user.id, MediaTypes.MOVIE.value)
        self.assertEqual(result["active"], [])
        self.assertEqual(result["full"], [])
        self.assertEqual(result["genres"], [])

    @patch("app.services.recommendations.provider_services.get_media_metadata")
    def test_compute_recommendations_caches_result(self, mock_metadata):
        mock_metadata.return_value = {
            "genres": [],
            "related": {"recommendations": []},
        }

        compute_recommendations(self.user.id, MediaTypes.MOVIE.value)
        cached = cache.get(get_cache_key(self.user.id, MediaTypes.MOVIE.value))
        self.assertIsNotNone(cached)

    @patch("app.services.recommendations.provider_services.get_media_metadata")
    def test_compute_recommendations_clears_progress(self, mock_metadata):
        mock_metadata.return_value = {
            "genres": [],
            "related": {"recommendations": []},
        }

        compute_recommendations(self.user.id, MediaTypes.MOVIE.value)
        progress = cache.get(get_progress_key(self.user.id, MediaTypes.MOVIE.value))
        self.assertIsNone(progress)


class MangaCrossMediaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="manga_rec_test", password="12345"
        )

        cls.anime_item = Item.objects.create(
            media_id="50",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Attack on Titan",
            english_title="Attack on Titan",
            image="http://example.com/aot.jpg",
        )
        Anime.objects.create(
            item=cls.anime_item,
            user=cls.user,
            status=Status.COMPLETED.value,
        )

        cls.manga_item = Item.objects.create(
            media_id="60",
            source=Sources.MAL.value,
            media_type=MediaTypes.MANGA.value,
            title="Berserk",
            image="http://example.com/berserk.jpg",
        )
        Manga.objects.create(
            item=cls.manga_item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
        )

    def setUp(self):
        cache.clear()

    @patch("app.services.recommendations.provider_services.get_media_metadata")
    def test_manga_recs_filter_cross_media(self, mock_metadata):
        mock_metadata.return_value = {
            "genres": ["Action"],
            "related": {
                "recommendations": [
                    {
                        "media_id": "999",
                        "source": Sources.MAL.value,
                        "title": "Attack on Titan",
                    },
                    {
                        "media_id": "998",
                        "source": Sources.MAL.value,
                        "title": "One Piece",
                    },
                ],
            },
        }

        result = compute_recommendations(self.user.id, MediaTypes.MANGA.value)
        all_titles = [r["title"] for r in result["active"] + result["full"]]
        self.assertNotIn("Attack on Titan", all_titles)
        self.assertIn("One Piece", all_titles)
