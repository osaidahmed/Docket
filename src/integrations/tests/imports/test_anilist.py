import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import (
    Anime,
    Manga,
    MediaTypes,
    Status,
)
from app.providers.services import ProviderAPIError
from integrations.imports import (
    anilist,
    helpers,
)
from integrations.imports.helpers import MediaImportError, MediaImportUnexpectedError

mock_path = Path(__file__).resolve().parent.parent / "mock_data"
app_mock_path = (
    Path(__file__).resolve().parent.parent.parent.parent / "app" / "tests" / "mock_data"
)


class ImportAniList(TestCase):
    """Test importing media from AniList."""

    def setUp(self):
        """Create user for the tests."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)

    @patch("requests.Session.post")
    def test_import_anilist_public(self, mock_request):
        """Basic test importing anime and manga from AniList."""
        with Path(mock_path / "import_anilist.json").open() as file:
            anilist_response = json.load(file)
        mock_request.return_value.json.return_value = anilist_response

        anilist.importer(None, self.user, "new", "bloodthirstiness")

        self.assertEqual(Anime.objects.filter(user=self.user).count(), 4)
        self.assertEqual(Manga.objects.filter(user=self.user).count(), 3)
        self.assertEqual(
            Anime.objects.get(user=self.user, item__title="FLCL").status,
            Status.PAUSED.value,
        )
        self.assertEqual(
            Manga.objects.filter(user=self.user, item__title="One Punch-Man")
            .first()
            .score,
            9,
        )
        self.assertEqual(
            Anime.objects.get(user=self.user, item__title="FLCL")
            .history.first()
            .history_date,
            datetime(2025, 6, 4, 10, 11, 17, tzinfo=UTC),
        )

    @patch("requests.Session.post")
    def test_import_anilist_private(self, mock_request):
        """Basic test importing anime and manga from AniList."""
        with Path(mock_path / "import_anilist.json").open() as file:
            anilist_response = json.load(file)
        mock_request.return_value.json.return_value = anilist_response

        anilist.importer(
            helpers.encrypt("token"),
            self.user,
            "new",
            "username",
        )

        self.assertEqual(Anime.objects.filter(user=self.user).count(), 4)
        self.assertEqual(Manga.objects.filter(user=self.user).count(), 3)
        self.assertEqual(
            Anime.objects.get(user=self.user, item__title="FLCL").status,
            Status.PAUSED.value,
        )
        self.assertEqual(
            Manga.objects.filter(user=self.user, item__title="One Punch-Man")
            .first()
            .score,
            9,
        )
        self.assertEqual(
            Anime.objects.get(user=self.user, item__title="FLCL")
            .history.first()
            .history_date,
            datetime(2025, 6, 4, 10, 11, 17, tzinfo=UTC),
        )

    def test_user_not_found(self):
        """Test that an error is raised if the user is not found."""
        self.assertRaises(
            helpers.MediaImportError,
            anilist.importer,
            None,
            self.user,
            "new",
            "fhdsufdsu",
        )

    @patch("app.providers.services.api_request")
    def test_get_token(self, mock_api_request):
        mock_api_request.side_effect = [
            {"access_token": "test_access"},
            {"data": {"Viewer": {"name": "testuser"}}},
        ]

        request = Mock()
        request.GET = {"code": "auth_code"}
        request.build_absolute_uri.return_value = "http://example.com/callback"

        result = anilist.get_token(request)
        self.assertEqual(result["access_token"], "test_access")
        self.assertEqual(result["username"], "testuser")

    @patch("app.providers.services.api_request")
    def test_get_token_unauthorized(self, mock_api_request):
        error_response = Mock()
        error_response.status_code = requests.codes.unauthorized
        error_response.text = "Unauthorized"
        mock_api_request.side_effect = ProviderAPIError(
            "ANILIST",
            Mock(response=error_response),
        )

        request = Mock()
        request.GET = {"code": "bad_code"}
        request.build_absolute_uri.return_value = "http://example.com/callback"

        with self.assertRaises(MediaImportError):
            anilist.get_token(request)

    @patch("app.providers.services.api_request")
    def test_get_username_from_oauth(self, mock_api_request):
        mock_api_request.return_value = {
            "data": {"Viewer": {"name": "testuser"}},
        }
        result = anilist.get_username_from_oauth("test_access")
        self.assertEqual(result, "testuser")

    @patch("app.providers.services.api_request")
    def test_get_username_from_oauth_unauthorized(self, mock_api_request):
        error_response = Mock()
        error_response.status_code = requests.codes.unauthorized
        error_response.text = "Unauthorized"
        mock_api_request.side_effect = ProviderAPIError(
            "ANILIST",
            Mock(response=error_response),
        )

        with self.assertRaises(MediaImportError):
            anilist.get_username_from_oauth("bad_token")

    @patch("requests.Session.post")
    def test_import_private_user_error(self, mock_request):
        error_response = Mock()
        error_response.status_code = 403
        error_response.json.return_value = {
            "errors": [{"message": "Private User"}],
        }
        error_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=error_response,
        )
        mock_request.return_value = error_response

        with self.assertRaises(MediaImportError) as ctx:
            anilist.importer(None, self.user, "new", "private_user")
        self.assertIn("private", str(ctx.exception))

    @patch("requests.Session.post")
    def test_import_entry_no_mal_id(self, mock_request):
        response_data = {
            "data": {
                "anime": {
                    "lists": [
                        {
                            "isCustomList": False,
                            "entries": [
                                {
                                    "media": {
                                        "coverImage": {"large": "img.jpg"},
                                        "idMal": None,
                                        "title": {"userPreferred": "No MAL Anime"},
                                    },
                                    "status": "COMPLETED",
                                    "score": 8,
                                    "progress": 12,
                                    "startedAt": {
                                        "year": None,
                                        "month": None,
                                        "day": None,
                                    },
                                    "completedAt": {
                                        "year": None,
                                        "month": None,
                                        "day": None,
                                    },
                                    "updatedAt": 1749031877,
                                    "repeat": 0,
                                    "notes": "",
                                },
                            ],
                        },
                    ],
                },
                "manga": {"lists": []},
            },
        }
        mock_request.return_value.json.return_value = response_data

        _, warnings = anilist.importer(None, self.user, "new", "testuser")
        self.assertIn("No matching MAL ID", warnings)

    @patch("requests.Session.post")
    def test_import_entry_unexpected_error(self, mock_request):
        response_data = {
            "data": {
                "anime": {
                    "lists": [
                        {
                            "isCustomList": False,
                            "entries": [
                                {
                                    "media": {
                                        "coverImage": {"large": "img.jpg"},
                                        "idMal": 1,
                                        "title": {"userPreferred": "Bad Anime"},
                                    },
                                    "status": "COMPLETED",
                                    "score": 8,
                                    "progress": 12,
                                    "startedAt": None,
                                    "completedAt": {
                                        "year": None,
                                        "month": None,
                                        "day": None,
                                    },
                                    "updatedAt": 1749031877,
                                    "repeat": 0,
                                    "notes": "",
                                },
                            ],
                        },
                    ],
                },
                "manga": {"lists": []},
            },
        }
        mock_request.return_value.json.return_value = response_data

        with self.assertRaises(MediaImportUnexpectedError):
            anilist.importer(None, self.user, "new", "testuser")

    @patch("requests.Session.post")
    def test_import_custom_list_skipped(self, mock_request):
        response_data = {
            "data": {
                "anime": {
                    "lists": [
                        {
                            "isCustomList": True,
                            "entries": [
                                {
                                    "media": {
                                        "coverImage": {"large": "img.jpg"},
                                        "idMal": 1,
                                        "title": {"userPreferred": "Custom Anime"},
                                    },
                                    "status": "COMPLETED",
                                    "score": 8,
                                    "progress": 12,
                                    "startedAt": {
                                        "year": None,
                                        "month": None,
                                        "day": None,
                                    },
                                    "completedAt": {
                                        "year": None,
                                        "month": None,
                                        "day": None,
                                    },
                                    "updatedAt": 1749031877,
                                    "repeat": 0,
                                    "notes": "",
                                },
                            ],
                        },
                    ],
                },
                "manga": {"lists": []},
            },
        }
        mock_request.return_value.json.return_value = response_data

        imported_counts, _ = anilist.importer(None, self.user, "new", "testuser")
        self.assertEqual(imported_counts.get(MediaTypes.ANIME.value, 0), 0)

    @patch("requests.Session.post")
    def test_import_repeating_status(self, mock_request):
        response_data = {
            "data": {
                "anime": {
                    "lists": [
                        {
                            "isCustomList": False,
                            "entries": [
                                {
                                    "media": {
                                        "coverImage": {"large": "img.jpg"},
                                        "idMal": 999,
                                        "title": {"userPreferred": "Repeat Anime"},
                                        "episodes": 12,
                                    },
                                    "status": "REPEATING",
                                    "score": 9,
                                    "progress": 6,
                                    "startedAt": {"year": 2023, "month": 1, "day": 1},
                                    "completedAt": {
                                        "year": None,
                                        "month": None,
                                        "day": None,
                                    },
                                    "updatedAt": 1749031877,
                                    "repeat": 0,
                                    "notes": "Rewatching!",
                                },
                            ],
                        },
                    ],
                },
                "manga": {"lists": []},
            },
        }
        mock_request.return_value.json.return_value = response_data

        imported_counts, _ = anilist.importer(None, self.user, "new", "testuser")
        self.assertEqual(imported_counts[MediaTypes.ANIME.value], 2)

        anime_objs = Anime.objects.filter(user=self.user)
        statuses = set(anime_objs.values_list("status", flat=True))
        self.assertIn(Status.COMPLETED.value, statuses)
        self.assertIn(Status.IN_PROGRESS.value, statuses)

    def test_get_date_with_partial_date(self):
        importer_instance = anilist.AniListImporter(None, self.user, "new", "test")
        result = importer_instance._get_date({"year": 2023, "month": None, "day": None})
        self.assertEqual(result.year, 2023)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 1)

    @patch("requests.Session.post")
    def test_import_updated_at_zero(self, mock_request):
        response_data = {
            "data": {
                "anime": {
                    "lists": [
                        {
                            "isCustomList": False,
                            "entries": [
                                {
                                    "media": {
                                        "coverImage": {"large": "img.jpg"},
                                        "idMal": 555,
                                        "title": {"userPreferred": "Zero Updated"},
                                    },
                                    "status": "COMPLETED",
                                    "score": 7,
                                    "progress": 12,
                                    "startedAt": {
                                        "year": None,
                                        "month": None,
                                        "day": None,
                                    },
                                    "completedAt": {
                                        "year": None,
                                        "month": None,
                                        "day": None,
                                    },
                                    "updatedAt": 0,
                                    "repeat": 0,
                                    "notes": "",
                                },
                            ],
                        },
                    ],
                },
                "manga": {"lists": []},
            },
        }
        mock_request.return_value.json.return_value = response_data

        imported_counts, _ = anilist.importer(None, self.user, "new", "testuser")
        self.assertEqual(imported_counts[MediaTypes.ANIME.value], 1)
