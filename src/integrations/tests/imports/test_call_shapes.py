from unittest.mock import Mock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from integrations.imports import anilist as anilist_import
from integrations.imports import helpers
from integrations.imports import simkl as simkl_import
from integrations.imports.steam import SteamImporter
from integrations.imports.trakt_auth import (
    get_access_token,
    get_username_from_oauth,
    handle_oauth_callback,
)


class TraktOAuthCallShapeTests(TestCase):
    def setUp(self):
        credentials = {"username": "shapeuser", "password": "x"}
        self.user = get_user_model().objects.create_user(**credentials)

    @patch("integrations.imports.trakt_auth.get_username_from_oauth")
    @patch("app.providers.services.api_request")
    def test_handle_oauth_callback_request_shape(
        self,
        mock_api_request,
        mock_get_username,
    ):
        mock_api_request.return_value = {
            "access_token": "ax",
            "refresh_token": "rt",
        }
        mock_get_username.return_value = "u"

        request = Mock()
        request.GET = {"code": "auth_code"}
        request.build_absolute_uri.return_value = "http://example.com/cb"

        handle_oauth_callback(request)

        mock_api_request.assert_called_once_with(
            "TRAKT",
            "POST",
            "https://api.trakt.tv/oauth/token",
            params={
                "client_id": settings.TRAKT_API,
                "client_secret": settings.TRAKT_API_SECRET,
                "code": "auth_code",
                "grant_type": "authorization_code",
                "redirect_uri": "http://example.com/cb",
            },
        )

    @patch("app.providers.services.api_request")
    def test_get_username_from_oauth_request_shape(self, mock_api_request):
        mock_api_request.return_value = {"username": "u"}
        get_username_from_oauth("the-access-token")

        args, kwargs = mock_api_request.call_args
        self.assertEqual(args[0], "TRAKT")
        self.assertEqual(args[1], "GET")
        self.assertEqual(args[2], "https://api.trakt.tv/users/me")
        headers = kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer the-access-token")
        self.assertEqual(headers["trakt-api-key"], settings.TRAKT_API)
        self.assertEqual(headers["trakt-api-version"], "2")
        self.assertEqual(headers["Content-Type"], "application/json")

    @patch("integrations.imports.trakt_auth.update_refresh_token")
    @patch("app.providers.services.api_request")
    def test_get_access_token_request_shape(
        self,
        mock_api_request,
        mock_update_refresh,
    ):
        mock_api_request.return_value = {
            "access_token": "new_a",
            "refresh_token": "new_r",
        }
        encrypted = helpers.encrypt("old_r")
        get_access_token(encrypted)

        mock_api_request.assert_called_once_with(
            "TRAKT",
            "POST",
            "https://api.trakt.tv/oauth/token",
            params={
                "client_id": settings.TRAKT_API,
                "client_secret": settings.TRAKT_API_SECRET,
                "refresh_token": "old_r",
                "grant_type": "refresh_token",
                "redirect_uri": f"{settings.BASE_URL}/import/trakt/private",
            },
        )
        mock_update_refresh.assert_called_once_with(encrypted, "new_r")


class AnilistGetTokenCallShapeTests(TestCase):
    @patch("app.providers.services.api_request")
    def test_request_shape(self, mock_api_request):
        mock_api_request.side_effect = [
            {"access_token": "ax"},
            {"data": {"Viewer": {"name": "u"}}},
        ]
        request = Mock()
        request.GET = {"code": "auth"}
        request.build_absolute_uri.return_value = "http://example.com/cb"

        anilist_import.get_token(request)

        first_call = mock_api_request.call_args_list[0]
        self.assertEqual(
            first_call.args,
            ("ANILIST", "POST", "https://anilist.co/api/v2/oauth/token"),
        )
        self.assertEqual(
            first_call.kwargs["params"],
            {
                "client_id": settings.ANILIST_ID,
                "client_secret": settings.ANILIST_SECRET,
                "code": "auth",
                "grant_type": "authorization_code",
                "redirect_uri": "http://example.com/cb",
            },
        )


class SimklGetTokenCallShapeTests(TestCase):
    @patch("app.providers.services.api_request")
    def test_request_shape(self, mock_api_request):
        mock_api_request.side_effect = [
            {"access_token": "ax"},
            {"user": {"name": "u"}},
        ]
        request = Mock()
        request.GET = {"code": "auth"}
        request.build_absolute_uri.return_value = "http://example.com/cb"

        simkl_import.get_token(request)

        first_call = mock_api_request.call_args_list[0]
        self.assertEqual(
            first_call.args,
            ("SIMKL", "POST", "https://api.simkl.com/oauth/token"),
        )
        self.assertEqual(
            first_call.kwargs["headers"],
            {"Content-Type": "application/json"},
        )
        self.assertEqual(
            first_call.kwargs["params"],
            {
                "client_id": settings.SIMKL_ID,
                "client_secret": settings.SIMKL_SECRET,
                "code": "auth",
                "grant_type": "authorization_code",
                "redirect_uri": "http://example.com/cb",
            },
        )


class SteamOwnedGamesCallShapeTests(TestCase):
    def setUp(self):
        self.importer = SteamImporter.__new__(SteamImporter)
        self.importer.api_key = "test-key"
        self.importer.steam_id = "76561"
        self.importer.warnings = []
        self.importer.user = Mock(username="u")

    @patch("integrations.imports.steam.services.api_request")
    def test_request_shape(self, mock_api_request):
        mock_api_request.return_value = {"response": {"games": []}}
        self.importer._get_owned_games()
        mock_api_request.assert_called_once_with(
            "STEAM",
            "GET",
            "https://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/",
            params={
                "key": "test-key",
                "steamid": "76561",
                "include_appinfo": 1,
                "include_played_free_games": 1,
                "format": "json",
            },
        )

    @patch("integrations.imports.steam.time.sleep")
    @patch("integrations.imports.steam.services.api_request")
    def test_retry_backoff_progression(self, mock_api_request, mock_sleep):
        import requests as req_mod

        rate_limit_resp = Mock()
        rate_limit_resp.status_code = req_mod.codes.too_many_requests
        success_response = {"response": {"games": []}}
        mock_api_request.side_effect = [
            req_mod.HTTPError(response=rate_limit_resp),
            req_mod.HTTPError(response=rate_limit_resp),
            success_response,
        ]
        self.importer._get_owned_games()
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_calls == [15, 30]
