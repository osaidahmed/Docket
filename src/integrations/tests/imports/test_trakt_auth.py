import json
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase
from django_celery_beat.models import IntervalSchedule, PeriodicTask

from app.providers.services import ProviderAPIError
from integrations.imports import helpers
from integrations.imports.helpers import MediaImportError
from integrations.imports.trakt import TraktImporter
from integrations.imports.trakt_auth import (
    get_access_token,
    get_username_from_oauth,
    handle_oauth_callback,
    update_refresh_token,
)


class TraktOAuthTests(TestCase):
    """Tests for Trakt OAuth helper functions."""

    def setUp(self):
        credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**credentials)

    @patch("integrations.imports.trakt_auth.get_username_from_oauth")
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

    @patch("integrations.imports.trakt_auth.update_refresh_token")
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
        schedule, _ = IntervalSchedule.objects.get_or_create(
            every=1,
            period=IntervalSchedule.DAYS,
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


class TraktAPIRequestTests(TestCase):
    """Tests for TraktImporter API request and pagination methods."""

    def setUp(self):
        credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**credentials)

    def test_trakt_importer_with_refresh_token(self):
        encrypted_token = helpers.encrypt("test_token")
        trakt_importer = TraktImporter(
            "testuser",
            self.user,
            "new",
            refresh_token=encrypted_token,
        )

        self.assertEqual(trakt_importer.username, "testuser")
        self.assertEqual(trakt_importer.refresh_token, encrypted_token)
        self.assertEqual(trakt_importer.mode, "new")

    def test_trakt_importer_without_refresh_token(self):
        trakt_importer = TraktImporter("testuser", self.user, "new", refresh_token=None)

        self.assertEqual(trakt_importer.username, "testuser")
        self.assertIsNone(trakt_importer.refresh_token)
        self.assertEqual(trakt_importer.mode, "new")

    @patch("integrations.imports.trakt.TraktImporter._make_api_request")
    def test_make_api_request_with_refresh_token(self, mock_request):
        mock_request.return_value = {"test": "data"}
        encrypted_token = helpers.encrypt("test_token")
        trakt_importer = TraktImporter(
            "testuser",
            self.user,
            "new",
            refresh_token=encrypted_token,
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
            "testuser",
            self.user,
            "new",
            refresh_token=encrypted_token,
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
