import json
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase
from django_celery_beat.models import PeriodicTask

from app.models import (
    MediaTypes,
    Movie,
    Sources,
    Status,
)
from app.providers.services import ProviderAPIError
from integrations.imports import (
    helpers,
)
from integrations.imports.helpers import MediaImportError, MediaImportUnexpectedError
from integrations.imports.trakt import (
    TraktImporter,
    get_access_token,
    get_username_from_oauth,
    handle_oauth_callback,
    importer,
    update_refresh_token,
)

mock_path = Path(__file__).resolve().parent.parent / "mock_data"
app_mock_path = (
    Path(__file__).resolve().parent.parent.parent.parent / "app" / "tests" / "mock_data"
)


class ImportTrakt(TestCase):
    """Test importing media from Trakt."""

    def setUp(self):
        """Create user for the tests."""
        credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**credentials)

    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_watched_movie(self, mock_get_metadata):
        """Test processing a movie entry."""
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

        # Verify progress is set to 1 for completed movies
        movie_obj = trakt_importer.bulk_media[MediaTypes.MOVIE.value][0]
        self.assertEqual(movie_obj.progress, 1)

        # Process the same movie again to test repeat handling
        trakt_importer.process_watched_movie(movie_entry)
        self.assertEqual(len(trakt_importer.bulk_media[MediaTypes.MOVIE.value]), 2)

    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_watched_episode(self, mock_get_metadata):
        """Test processing an episode entry."""
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

        # Process the same episode again to test repeat handling
        trakt_importer.process_watched_episode(episode_entry)
        self.assertEqual(len(trakt_importer.bulk_media[MediaTypes.EPISODE.value]), 2)

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_watchlist(self, mock_get_metadata, mock_make_request):
        """Test processing a watchlist entry."""
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
        """Test processing a rating entry."""
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
        """Test processing paginated comments from Trakt."""
        # First page with one comment
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

        # Second empty page to stop pagination
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
        self.assertIn("?page=1&limit=1000", calls[0].args[0])  # First page
        self.assertIn("?page=2&limit=1000", calls[1].args[0])  # Second page

        self.assertEqual(len(trakt_importer.bulk_media[MediaTypes.MOVIE.value]), 1)
        movie_obj = trakt_importer.bulk_media[MediaTypes.MOVIE.value][0]
        self.assertEqual(movie_obj.notes, "Great movie!")

    @patch("integrations.imports.trakt.TraktImporter._get_paginated_data")
    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_public_import_full_flow(
        self,
        mock_get_metadata,
        mock_make_request,
        mock_get_paginated,
    ):
        """Test full import flow with public username (no OAuth)."""
        mock_get_paginated.side_effect = [
            [
                {
                    "type": "movie",
                    "movie": {"title": "Public Movie", "ids": {"tmdb": 999}},
                    "watched_at": "2023-01-01T00:00:00.000Z",
                },
            ],
            [],  # Empty comments
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
        """Test full import flow with OAuth token."""
        mock_get_paginated.side_effect = [
            [
                {
                    "type": "movie",
                    "movie": {"title": "OAuth Movie", "ids": {"tmdb": 888}},
                    "watched_at": "2023-01-01T00:00:00.000Z",
                },
            ],
            [],  # Empty comments
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

    def test_trakt_importer_with_refresh_token(self):
        """Test TraktImporter initialization with refresh token."""
        encrypted_token = helpers.encrypt("test_token")
        importer = TraktImporter(
            "testuser",
            self.user,
            "new",
            refresh_token=encrypted_token,
        )

        self.assertEqual(importer.username, "testuser")
        self.assertEqual(importer.refresh_token, encrypted_token)
        self.assertEqual(importer.mode, "new")

    def test_trakt_importer_without_refresh_token(self):
        """Test TraktImporter initialization without refresh token (public)."""
        importer = TraktImporter("testuser", self.user, "new", refresh_token=None)

        self.assertEqual(importer.username, "testuser")
        self.assertIsNone(importer.refresh_token)
        self.assertEqual(importer.mode, "new")

    @patch("integrations.imports.trakt.get_username_from_oauth")
    @patch("app.providers.services.api_request")
    def test_handle_oauth_callback(self, mock_api_request, mock_get_username):
        mock_api_request.return_value = {
            "access_token": "test_access",
            "refresh_token": "test_refresh",
        }
        mock_get_username.return_value = "testuser"

        request = Mock()
        request.GET = {"code": "auth_code"}
        request.build_absolute_uri.return_value = "http://example.com/callback"

        result = handle_oauth_callback(request)

        self.assertEqual(result["refresh_token"], "test_refresh")
        self.assertEqual(result["username"], "testuser")

    @patch("app.providers.services.api_request")
    def test_handle_oauth_callback_unauthorized(self, mock_api_request):
        error_response = Mock()
        error_response.status_code = requests.codes.unauthorized
        error_response.text = "Unauthorized"
        mock_api_request.side_effect = ProviderAPIError(
            "TRAKT",
            Mock(response=error_response),
        )

        request = Mock()
        request.GET = {"code": "bad_code"}
        request.build_absolute_uri.return_value = "http://example.com/callback"

        with self.assertRaises(MediaImportError):
            handle_oauth_callback(request)

    @patch("app.providers.services.api_request")
    def test_get_username_from_oauth(self, mock_api_request):
        mock_api_request.return_value = {"username": "testuser"}
        result = get_username_from_oauth("test_access_token")
        self.assertEqual(result, "testuser")

    @patch("app.providers.services.api_request")
    def test_get_username_from_oauth_unauthorized(self, mock_api_request):
        error_response = Mock()
        error_response.status_code = requests.codes.unauthorized
        error_response.text = "Unauthorized"
        mock_api_request.side_effect = ProviderAPIError(
            "TRAKT",
            Mock(response=error_response),
        )

        with self.assertRaises(MediaImportError):
            get_username_from_oauth("bad_token")

    @patch("integrations.imports.trakt.update_refresh_token")
    @patch("app.providers.services.api_request")
    def test_get_access_token(self, mock_api_request, mock_update_refresh):
        mock_api_request.return_value = {
            "access_token": "new_access",
            "refresh_token": "new_refresh",
        }

        encrypted_token = helpers.encrypt("old_refresh")
        result = get_access_token(encrypted_token)

        self.assertEqual(result, "new_access")
        mock_update_refresh.assert_called_once_with(encrypted_token, "new_refresh")

    @patch("app.providers.services.api_request")
    def test_get_access_token_unauthorized(self, mock_api_request):
        error_response = Mock()
        error_response.status_code = requests.codes.unauthorized
        error_response.text = "Unauthorized"
        mock_api_request.side_effect = ProviderAPIError(
            "TRAKT",
            Mock(response=error_response),
        )

        with self.assertRaises(MediaImportError):
            get_access_token(helpers.encrypt("bad_token"))

    def test_update_refresh_token_with_matching_task(self):
        from django_celery_beat.models import IntervalSchedule
        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=1, period=IntervalSchedule.DAYS,
        )
        old_encrypted = helpers.encrypt("old_token")
        task_kwargs = json.dumps({"token": old_encrypted, "user_id": 1})
        PeriodicTask.objects.create(
            name="Test Trakt Import",
            task="Import from Trakt",
            kwargs=task_kwargs,
            interval=schedule,
            enabled=True,
        )

        update_refresh_token(old_encrypted, "new_refresh_token")

        task = PeriodicTask.objects.get(name="Test Trakt Import")
        new_kwargs = json.loads(task.kwargs)
        self.assertEqual(helpers.decrypt(new_kwargs["token"]), "new_refresh_token")

    def test_update_refresh_token_no_matching_task(self):
        update_refresh_token("nonexistent_token", "new_token")

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    def test_make_api_request_with_refresh_token(self, mock_request):
        mock_request.return_value = {"test": "data"}
        encrypted_token = helpers.encrypt("test_token")
        trakt_importer = TraktImporter(
            "testuser", self.user, "new", refresh_token=encrypted_token,
        )

        with patch(
            "integrations.imports.trakt.get_access_token",
            return_value="access_token",
        ):
            trakt_importer._make_api_request.__wrapped__ = None
            actual_importer = TraktImporter.__new__(TraktImporter)
            actual_importer.username = "testuser"
            actual_importer.user = self.user
            actual_importer.mode = "new"
            actual_importer.refresh_token = encrypted_token
            actual_importer.warnings = []
            actual_importer.existing_media = {}
            actual_importer.to_delete = {}
            actual_importer.bulk_media = {}
            actual_importer.media_instances = {}

    @patch("integrations.imports.trakt.services.api_request")
    @patch("integrations.imports.trakt.get_access_token")
    def test_make_api_request_sets_access_token(self, mock_get_token, mock_api_request):
        mock_get_token.return_value = "new_access_token"
        mock_api_request.return_value = {"test": "data"}

        encrypted_token = helpers.encrypt("test_token")
        trakt_importer = TraktImporter(
            "testuser", self.user, "new", refresh_token=encrypted_token,
        )

        result = trakt_importer._make_api_request("https://api.trakt.tv/test")
        self.assertEqual(result, {"test": "data"})
        self.assertEqual(trakt_importer.access_token, "new_access_token")

        trakt_importer._make_api_request("https://api.trakt.tv/test2")
        mock_get_token.assert_called_once()

    @patch("integrations.imports.trakt.services.api_request")
    def test_make_api_request_without_refresh_token(self, mock_api_request):
        mock_api_request.return_value = {"test": "data"}
        trakt_importer = TraktImporter("testuser", self.user, "new")

        result = trakt_importer._make_api_request("https://api.trakt.tv/test")
        self.assertEqual(result, {"test": "data"})

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    def test_get_paginated_data_404(self, mock_request):
        response = Mock()
        response.status_code = requests.codes.not_found
        mock_request.side_effect = requests.exceptions.HTTPError(response=response)

        trakt_importer = TraktImporter("testuser", self.user, "new")
        with self.assertRaises(MediaImportError) as ctx:
            trakt_importer._get_paginated_data("https://api.trakt.tv/test")
        self.assertIn("User slug", str(ctx.exception))

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    def test_get_paginated_data_401(self, mock_request):
        response = Mock()
        response.status_code = requests.codes.unauthorized
        mock_request.side_effect = requests.exceptions.HTTPError(response=response)

        trakt_importer = TraktImporter("testuser", self.user, "new")
        with self.assertRaises(MediaImportError) as ctx:
            trakt_importer._get_paginated_data("https://api.trakt.tv/test")
        self.assertIn("private", str(ctx.exception))

    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_watched_movie_no_tmdb_id(self, mock_get_metadata):
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
    def test_process_watched_episode_no_tmdb_id(self, mock_get_metadata):
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
        def side_effect(media_type, *args, **kwargs):
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
        self.assertEqual(len(trakt_importer.bulk_media.get(MediaTypes.EPISODE.value, [])), 0)

    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_watched_episode_invalid_episode(self, mock_get_metadata):
        def side_effect(media_type, *args, **kwargs):
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
        self.assertEqual(len(trakt_importer.bulk_media.get(MediaTypes.EPISODE.value, [])), 0)
        self.assertTrue(any("not found" in w for w in trakt_importer.warnings))

    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_get_episode_image_no_still(self, mock_get_metadata):
        trakt_importer = TraktImporter("testuser", self.user, "new")
        season_metadata = {
            "episodes": [{"episode_number": 1}],
        }
        from django.conf import settings
        result = trakt_importer._get_episode_image(1, season_metadata)
        self.assertEqual(result, settings.IMG_NONE)

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
        def side_effect(media_type, *args, **kwargs):
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
    def test_process_generic_entry_movie_no_tmdb(self, mock_get_metadata, mock_request):
        entry = {
            "type": "movie",
            "movie": {"title": "No ID Movie", "ids": {}},
            "listed_at": "2023-01-01T00:00:00.000Z",
        }
        mock_request.return_value = [entry]

        trakt_importer = TraktImporter("testuser", self.user, "new")
        trakt_importer.process_watchlist()
        self.assertEqual(len(trakt_importer.bulk_media.get(MediaTypes.MOVIE.value, [])), 0)

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
        self.assertEqual(len(trakt_importer.bulk_media.get(MediaTypes.MOVIE.value, [])), 0)

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_process_generic_entry_season_tv_metadata_none(self, mock_get_metadata, mock_request):
        def side_effect(media_type, *args, **kwargs):
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
        self.assertEqual(len(trakt_importer.bulk_media.get(MediaTypes.SEASON.value, [])), 0)

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

    @patch("integrations.imports.trakt.services.get_media_metadata")
    def test_get_metadata_not_found(self, mock_get_metadata):
        error_response = Mock()
        error_response.status_code = requests.codes.not_found
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
        error_response.status_code = requests.codes.not_found
        error_response.text = "Not found"
        mock_get_metadata.side_effect = ProviderAPIError(
            "TMDB",
            Mock(response=error_response),
        )

        trakt_importer = TraktImporter("testuser", self.user, "new")
        result = trakt_importer._get_metadata(
            MediaTypes.SEASON.value, "999", "Test Show", season_number=2,
        )
        self.assertIsNone(result)
        self.assertTrue(any("S2" in w for w in trakt_importer.warnings))

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    @patch("integrations.imports.trakt.TraktImporter._get_metadata")
    def test_get_tv_obj_existing(self, mock_get_metadata, mock_request):
        def side_effect(media_type, *args, **kwargs):
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
