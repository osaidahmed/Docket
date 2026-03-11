from pathlib import Path
from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import (
    MediaTypes,
    Movie,
    Status,
)
from app.providers.services import ProviderAPIError
from integrations.imports import helpers
from integrations.imports.helpers import MediaImportUnexpectedError
from integrations.imports.trakt import (
    TraktImporter,
    importer,
)

mock_path = Path(__file__).resolve().parent.parent / "mock_data"
app_mock_path = (
    Path(__file__).resolve().parent.parent.parent.parent / "app" / "tests" / "mock_data"
)


class TraktWatchedTests(TestCase):
    """Tests for processing watched movies and episodes."""

    def setUp(self):
        credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**credentials)

    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_watched_movie(self, mock_get_metadata):
        movie_entry = {
            "type": "movie",
            "movie": {"title": "Test Movie", "ids": {"tmdb": 67890}},
            "watched_at": "2023-01-02T00:00:00.000Z",
        }

        mock_get_metadata.return_value = {
            "title": "Test Movie",
            "image": "movie_image.jpg",
        }

        trakt_importer = TraktImporter("test", self.user, "new")
        trakt_importer.process_watched_movie(movie_entry)

        self.assertEqual(len(trakt_importer.bulk_media[MediaTypes.MOVIE.value]), 1)
        self.assertEqual(len(trakt_importer.media_instances[MediaTypes.MOVIE.value]), 1)

        movie_obj = trakt_importer.bulk_media[MediaTypes.MOVIE.value][0]
        self.assertEqual(movie_obj.progress, 1)

        trakt_importer.process_watched_movie(movie_entry)
        self.assertEqual(len(trakt_importer.bulk_media[MediaTypes.MOVIE.value]), 2)

    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_watched_episode(self, mock_get_metadata):
        episode_entry = {
            "type": "episode",
            "episode": {"season": 1, "number": 1, "title": "Pilot"},
            "show": {"title": "Test Show", "ids": {"tmdb": 12345}},
            "watched_at": "2023-01-01T00:00:00.000Z",
        }

        def mock_metadata_side_effect(media_type, _, __, ___=None):
            if media_type == MediaTypes.TV.value:
                return {
                    "title": "Test Show",
                    "image": "tv_image.jpg",
                    "last_episode_season": 1,
                    "max_progress": 1,
                }
            if media_type == MediaTypes.SEASON.value:
                return {
                    "title": "Season 1",
                    "image": "season_image.jpg",
                    "episodes": [{"episode_number": 1, "still_path": "/still.jpg"}],
                    "max_progress": 1,
                }
            return None

        mock_get_metadata.side_effect = mock_metadata_side_effect

        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_watched_episode(episode_entry)

        self.assertEqual(len(trakt_importer.bulk_media[MediaTypes.TV.value]), 1)
        self.assertEqual(len(trakt_importer.bulk_media[MediaTypes.SEASON.value]), 1)
        self.assertEqual(len(trakt_importer.bulk_media[MediaTypes.EPISODE.value]), 1)

        trakt_importer.process_watched_episode(episode_entry)
        self.assertEqual(len(trakt_importer.bulk_media[MediaTypes.EPISODE.value]), 2)

    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_watched_movie_no_tmdb_id(self, _mock_get_metadata):
        entry = {
            "type": "movie",
            "movie": {"title": "Test", "ids": {}},
            "watched_at": "2023-01-01T00:00:00.000Z",
        }
        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_watched_movie(entry)
        self.assertEqual(len(trakt_importer.bulk_media), 0)

    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_watched_movie_skip_existing_new_mode(self, mock_get_metadata):
        mock_get_metadata.return_value = {"title": "Test", "image": "img.jpg"}

        entry = {
            "type": "movie",
            "movie": {"title": "Test", "ids": {"tmdb": 123}},
            "watched_at": "2023-01-01T00:00:00.000Z",
        }

        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_watched_movie(entry)
        self.assertEqual(len(trakt_importer.bulk_media[MediaTypes.MOVIE.value]), 1)
        helpers.bulk_create_media(trakt_importer.bulk_media, self.user)

        trakt_importer2 = TraktImporter("testuser", self.user, "new")
        trakt_importer2.process_watched_movie(entry)
        self.assertEqual(len(trakt_importer2.bulk_media[MediaTypes.MOVIE.value]), 0)

    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_watched_movie_metadata_none(self, mock_get_metadata):
        mock_get_metadata.return_value = None
        entry = {
            "type": "movie",
            "movie": {"title": "Test", "ids": {"tmdb": 999}},
            "watched_at": "2023-01-01T00:00:00.000Z",
        }
        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_watched_movie(entry)
        self.assertEqual(len(trakt_importer.bulk_media), 0)

    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_watched_episode_no_tmdb_id(self, _mock_get_metadata):
        entry = {
            "type": "episode",
            "episode": {"season": 1, "number": 1},
            "show": {"title": "Test", "ids": {}},
            "watched_at": "2023-01-01T00:00:00.000Z",
        }
        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_watched_episode(entry)
        self.assertEqual(len(trakt_importer.bulk_media), 0)

    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_watched_episode_tv_metadata_none(self, mock_get_metadata):
        mock_get_metadata.return_value = None
        entry = {
            "type": "episode",
            "episode": {"season": 1, "number": 1},
            "show": {"title": "Test", "ids": {"tmdb": 999}},
            "watched_at": "2023-01-01T00:00:00.000Z",
        }
        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_watched_episode(entry)
        self.assertEqual(len(trakt_importer.bulk_media), 0)

    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_watched_episode_season_metadata_none(self, mock_get_metadata):
        def side_effect(media_type, *_args, **_kwargs):
            if media_type == MediaTypes.TV.value:
                return {"title": "Test", "image": "img.jpg"}
            return None

        mock_get_metadata.side_effect = side_effect
        entry = {
            "type": "episode",
            "episode": {"season": 1, "number": 1},
            "show": {"title": "Test", "ids": {"tmdb": 999}},
            "watched_at": "2023-01-01T00:00:00.000Z",
        }
        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_watched_episode(entry)
        self.assertEqual(
            len(trakt_importer.bulk_media.get(MediaTypes.EPISODE.value, [])), 0
        )

    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_watched_episode_invalid_episode(self, mock_get_metadata):
        def side_effect(media_type, *_args, **_kwargs):
            if media_type == MediaTypes.TV.value:
                return {"title": "Test", "image": "img.jpg", "last_episode_season": 1}
            if media_type == MediaTypes.SEASON.value:
                return {
                    "title": "Season 1",
                    "image": "season.jpg",
                    "episodes": [{"episode_number": 1, "still_path": "/ep1.jpg"}],
                    "max_progress": 1,
                }
            return None

        mock_get_metadata.side_effect = side_effect
        entry = {
            "type": "episode",
            "episode": {"season": 1, "number": 99},
            "show": {"title": "Test", "ids": {"tmdb": 999}},
            "watched_at": "2023-01-01T00:00:00.000Z",
        }
        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_watched_episode(entry)
        self.assertEqual(
            len(trakt_importer.bulk_media.get(MediaTypes.EPISODE.value, [])), 0
        )
        self.assertTrue(any("not found" in w for w in trakt_importer.warnings))

    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_get_episode_image_no_still(self, _mock_get_metadata):
        trakt_importer = TraktImporter("testuser", self.user, "new")
        season_metadata = {
            "episodes": [{"episode_number": 1}],
        }
        result = trakt_importer._get_episode_image(1, season_metadata)
        self.assertEqual(result, settings.IMG_NONE)


class TraktListProcessingTests(TestCase):
    """Tests for watchlist, ratings, comments processing."""

    def setUp(self):
        credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**credentials)

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_watchlist(self, mock_get_metadata, mock_make_request):
        watchlist_entry = {
            "listed_at": "2023-01-01T00:00:00.000Z",
            "type": "show",
            "show": {"title": "Watchlist Show", "ids": {"tmdb": 54321}},
        }

        mock_make_request.return_value = [watchlist_entry]
        mock_get_metadata.return_value = {
            "title": "Watchlist Show",
            "image": "show_image.jpg",
        }

        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_watchlist()

        self.assertEqual(len(trakt_importer.bulk_media[MediaTypes.TV.value]), 1)
        tv_obj = trakt_importer.bulk_media[MediaTypes.TV.value][0]
        self.assertEqual(tv_obj.status, Status.PLANNING.value)

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_ratings(self, mock_get_metadata, mock_make_request):
        rating_entry = {
            "rated_at": "2023-01-01T00:00:00.000Z",
            "type": "movie",
            "movie": {"title": "Rated Movie", "ids": {"tmdb": 238}},
            "rating": 8,
        }

        mock_make_request.return_value = [rating_entry]
        mock_get_metadata.return_value = {
            "title": "Rated Movie",
            "image": "movie_image.jpg",
        }

        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_ratings()

        self.assertEqual(len(trakt_importer.bulk_media[MediaTypes.MOVIE.value]), 1)
        movie_obj = trakt_importer.bulk_media[MediaTypes.MOVIE.value][0]
        self.assertEqual(movie_obj.score, 8)

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_comments(self, mock_get_metadata, mock_make_request):
        first_page = [
            {
                "type": "movie",
                "movie": {"title": "Commented Movie", "ids": {"tmdb": 123}},
                "comment": {
                    "comment": "Great movie!",
                    "updated_at": "2023-01-01T00:00:00.000Z",
                },
            },
        ]
        second_page = []

        mock_make_request.side_effect = [first_page, second_page]
        mock_get_metadata.return_value = {
            "title": "Commented Movie",
            "image": "movie_image.jpg",
        }

        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_comments()

        calls = mock_make_request.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertIn("?page=1&limit=1000", calls[0].args[0])
        self.assertIn("?page=2&limit=1000", calls[1].args[0])

        self.assertEqual(len(trakt_importer.bulk_media[MediaTypes.MOVIE.value]), 1)
        movie_obj = trakt_importer.bulk_media[MediaTypes.MOVIE.value][0]
        self.assertEqual(movie_obj.notes, "Great movie!")

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_watchlist_exception(self, mock_get_metadata, mock_request):
        mock_request.return_value = [
            {
                "type": "movie",
                "movie": {"title": "Test", "ids": {"tmdb": 123}},
                "listed_at": "2023-01-01T00:00:00.000Z",
            },
        ]
        mock_get_metadata.side_effect = RuntimeError("unexpected")

        trakt_importer = TraktImporter("testuser", self.user, "new")
        with self.assertRaises(MediaImportUnexpectedError):
            trakt_importer.process_watchlist()

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_ratings_exception(self, mock_get_metadata, mock_request):
        mock_request.return_value = [
            {
                "type": "movie",
                "movie": {"title": "Test", "ids": {"tmdb": 123}},
                "rating": 8,
                "rated_at": "2023-01-01T00:00:00.000Z",
            },
        ]
        mock_get_metadata.side_effect = RuntimeError("unexpected")

        trakt_importer = TraktImporter("testuser", self.user, "new")
        with self.assertRaises(MediaImportUnexpectedError):
            trakt_importer.process_ratings()

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_comments_exception(self, mock_get_metadata, mock_request):
        mock_request.side_effect = [
            [
                {
                    "type": "movie",
                    "movie": {"title": "Test", "ids": {"tmdb": 123}},
                    "comment": {
                        "comment": "test",
                        "updated_at": "2023-01-01T00:00:00.000Z",
                    },
                },
            ],
            [],
        ]
        mock_get_metadata.side_effect = RuntimeError("unexpected")

        trakt_importer = TraktImporter("testuser", self.user, "new")
        with self.assertRaises(MediaImportUnexpectedError):
            trakt_importer.process_comments()

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_generic_entry_season(self, mock_get_metadata, mock_request):
        def side_effect(media_type, *_args, **_kwargs):
            if media_type == MediaTypes.TV.value:
                return {"title": "Test Show", "image": "tv.jpg"}
            if media_type == MediaTypes.SEASON.value:
                return {"title": "Season 1", "image": "s1.jpg"}
            return None

        mock_get_metadata.side_effect = side_effect

        watchlist_entry = {
            "type": "season",
            "show": {"title": "Test Show", "ids": {"tmdb": 555}},
            "season": {"number": 1},
            "listed_at": "2023-01-01T00:00:00.000Z",
        }

        mock_request.return_value = [watchlist_entry]

        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_watchlist()

        self.assertEqual(len(trakt_importer.bulk_media[MediaTypes.TV.value]), 1)
        self.assertEqual(len(trakt_importer.bulk_media[MediaTypes.SEASON.value]), 1)

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_generic_entry_movie_no_tmdb(
        self, _mock_get_metadata, mock_request
    ):
        entry = {
            "type": "movie",
            "movie": {"title": "No ID Movie", "ids": {}},
            "listed_at": "2023-01-01T00:00:00.000Z",
        }
        mock_request.return_value = [entry]

        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_watchlist()
        self.assertEqual(
            len(trakt_importer.bulk_media.get(MediaTypes.MOVIE.value, [])), 0
        )

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_generic_entry_metadata_none(self, mock_get_metadata, mock_request):
        mock_get_metadata.return_value = None
        entry = {
            "type": "movie",
            "movie": {"title": "Test", "ids": {"tmdb": 123}},
            "listed_at": "2023-01-01T00:00:00.000Z",
        }
        mock_request.return_value = [entry]

        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_watchlist()
        self.assertEqual(
            len(trakt_importer.bulk_media.get(MediaTypes.MOVIE.value, [])), 0
        )

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_generic_entry_season_tv_metadata_none(
        self, mock_get_metadata, mock_request
    ):
        def side_effect(media_type, *_args, **_kwargs):
            if media_type == MediaTypes.SEASON.value:
                return {"title": "Season 1", "image": "s1.jpg"}
            return None

        mock_get_metadata.side_effect = side_effect

        entry = {
            "type": "season",
            "show": {"title": "Test", "ids": {"tmdb": 123}},
            "season": {"number": 1},
            "listed_at": "2023-01-01T00:00:00.000Z",
        }
        mock_request.return_value = [entry]

        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_watchlist()
        self.assertEqual(
            len(trakt_importer.bulk_media.get(MediaTypes.SEASON.value, [])), 0
        )

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_update_instance_on_duplicate(self, mock_get_metadata, mock_request):
        mock_get_metadata.return_value = {"title": "Test Movie", "image": "img.jpg"}

        entry = {
            "type": "movie",
            "movie": {"title": "Test Movie", "ids": {"tmdb": 777}},
            "rated_at": "2023-01-01T00:00:00.000Z",
            "rating": 8,
        }

        mock_request.return_value = [entry, entry]

        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_ratings()

        movie_objs = trakt_importer.bulk_media[MediaTypes.MOVIE.value]
        self.assertEqual(len(movie_objs), 1)
        self.assertEqual(movie_objs[0].score, 8)

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_get_tv_obj_existing(self, mock_get_metadata, mock_request):
        def side_effect(media_type, *_args, **_kwargs):
            if media_type == MediaTypes.TV.value:
                return {"title": "Test Show", "image": "tv.jpg"}
            if media_type == MediaTypes.SEASON.value:
                return {"title": "Season 1", "image": "s1.jpg"}
            return None

        mock_get_metadata.side_effect = side_effect

        entry1 = {
            "type": "season",
            "show": {"title": "Test Show", "ids": {"tmdb": 555}},
            "season": {"number": 1},
            "listed_at": "2023-01-01T00:00:00.000Z",
        }
        entry2 = {
            "type": "season",
            "show": {"title": "Test Show", "ids": {"tmdb": 555}},
            "season": {"number": 2},
            "listed_at": "2023-01-02T00:00:00.000Z",
        }

        mock_request.return_value = [entry1, entry2]

        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_watchlist()

        self.assertEqual(len(trakt_importer.bulk_media[MediaTypes.TV.value]), 1)


class TraktMetadataTests(TestCase):
    """Tests for metadata fetching and error handling."""

    def setUp(self):
        credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**credentials)

    @patch("integrations.imports.trakt.services.get_media_metadata")
    def test_get_metadata_not_found(self, mock_get_metadata):
        error_response = Mock()
        error_response.status_code = 404
        error_response.text = "Not found"
        mock_get_metadata.side_effect = ProviderAPIError(
            "TMDB",
            Mock(response=error_response),
        )

        trakt_importer = TraktImporter("testuser", self.user, "new")
        result = trakt_importer._get_metadata(MediaTypes.MOVIE.value, "999", "Test")
        self.assertIsNone(result)
        self.assertTrue(any("not found" in w for w in trakt_importer.warnings))

    @patch("integrations.imports.trakt.services.get_media_metadata")
    def test_get_metadata_season_not_found(self, mock_get_metadata):
        error_response = Mock()
        error_response.status_code = 404
        error_response.text = "Not found"
        mock_get_metadata.side_effect = ProviderAPIError(
            "TMDB",
            Mock(response=error_response),
        )

        trakt_importer = TraktImporter("testuser", self.user, "new")
        result = trakt_importer._get_metadata(
            MediaTypes.SEASON.value,
            "999",
            "Test Show",
            season_number=2,
        )
        self.assertIsNone(result)
        self.assertTrue(any("S2" in w for w in trakt_importer.warnings))


class TraktFullFlowTests(TestCase):
    """Integration tests for the full import pipeline."""

    def setUp(self):
        credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**credentials)

    @patch("integrations.imports.trakt.TraktImporter._get_paginated_data")
    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_public_import_full_flow(
        self,
        mock_get_metadata,
        mock_make_request,
        mock_get_paginated,
    ):
        mock_get_paginated.side_effect = [
            [
                {
                    "type": "movie",
                    "movie": {"title": "Public Movie", "ids": {"tmdb": 999}},
                    "watched_at": "2023-01-01T00:00:00.000Z",
                },
            ],
            [],
        ]

        mock_make_request.return_value = []

        mock_get_metadata.return_value = {
            "title": "Public Movie",
            "image": "movie.jpg",
        }

        imported_counts, _ = importer(None, self.user, "new", "public_user")

        self.assertEqual(imported_counts[MediaTypes.MOVIE.value], 1)
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 1)

    @patch("integrations.imports.trakt.TraktImporter._get_paginated_data")
    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_oauth_import_full_flow(
        self,
        mock_get_metadata,
        mock_make_request,
        mock_get_paginated,
    ):
        mock_get_paginated.side_effect = [
            [
                {
                    "type": "movie",
                    "movie": {"title": "OAuth Movie", "ids": {"tmdb": 888}},
                    "watched_at": "2023-01-01T00:00:00.000Z",
                },
            ],
            [],
        ]

        mock_make_request.return_value = []

        mock_get_metadata.return_value = {
            "title": "OAuth Movie",
            "image": "movie.jpg",
        }

        encrypted_token = helpers.encrypt("test_refresh_token")
        imported_counts, _ = importer(
            encrypted_token,
            self.user,
            "new",
            "oauth_user",
        )

        self.assertEqual(imported_counts[MediaTypes.MOVIE.value], 1)
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 1)
