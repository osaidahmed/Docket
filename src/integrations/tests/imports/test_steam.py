from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from requests import Response
from requests.exceptions import HTTPError

from app.models import (
    Game,
    MediaTypes,
    Sources,
    Status,
)
from integrations.imports import (
    helpers,
    steam,
)

mock_path = Path(__file__).resolve().parent.parent / "mock_data"
app_mock_path = (
    Path(__file__).resolve().parent.parent.parent.parent / "app" / "tests" / "mock_data"
)


class ImportSteam(TestCase):
    """Test importing media from Steam."""

    def setUp(self):
        """Create user for the tests."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)

    @patch("integrations.imports.steam.services.api_request")
    @patch("integrations.imports.steam.external_game")
    @patch("integrations.imports.steam.services.get_media_metadata")
    def test_import_steam_games(
        self,
        mock_get_metadata,
        mock_external_game,
        mock_api_request,
    ):
        """Test importing games from Steam."""
        mock_api_request.return_value = {
            "response": {
                "games": [
                    {
                        "appid": 730,
                        "name": "Counter-Strike 2",
                        "playtime_forever": 1250,
                        "playtime_2weeks": 120,  # Recent activity
                        "rtime_last_played": 1704067200,  # Recent timestamp
                    },
                    {
                        "appid": 570,
                        "name": "Dota 2",
                        "playtime_forever": 0,  # Never played
                        "playtime_2weeks": 0,  # No recent activity
                    },
                    {
                        "appid": 440,
                        "name": "Team Fortress 2",
                        "playtime_forever": 500,
                        "playtime_2weeks": 0,  # No recent activity
                        "rtime_last_played": 1672531200,  # Old timestamp (over 14 days)
                    },
                ],
            },
        }

        mock_external_game.side_effect = [1, 2, 3]  # IGDB game IDs for each Steam app

        mock_get_metadata.side_effect = [
            {"title": "Counter-Strike 2", "image": "http://example.com/cs2.jpg"},
            {"title": "Dota 2", "image": "http://example.com/dota2.jpg"},
            {"title": "Team Fortress 2", "image": "http://example.com/tf2.jpg"},
        ]

        imported_counts, _ = steam.importer(
            "76561198000000000",
            self.user,
            "new",
        )

        self.assertEqual(imported_counts[MediaTypes.GAME.value], 3)

        games = Game.objects.filter(user=self.user)
        self.assertEqual(games.count(), 3)

        cs2_game = games.get(item__title="Counter-Strike 2")
        self.assertEqual(cs2_game.status, Status.IN_PROGRESS.value)
        self.assertEqual(cs2_game.progress, 1250)

        dota_game = games.get(item__title="Dota 2")
        self.assertEqual(dota_game.status, Status.PLANNING.value)
        self.assertEqual(dota_game.progress, 0)

        tf2_game = games.get(item__title="Team Fortress 2")
        self.assertEqual(tf2_game.status, Status.PAUSED.value)
        self.assertEqual(tf2_game.progress, 500)

    @patch("integrations.imports.steam.services.api_request")
    def test_import_steam_private_profile(self, mock_api_request):
        """Test handling of private Steam profile."""
        response = Response()
        response.status_code = 403
        mock_api_request.side_effect = HTTPError(response=response)

        with self.assertRaises(helpers.MediaImportError) as context:
            steam.importer("76561198000000000", self.user, "new")

        self.assertIn("private or invalid", str(context.exception))

    @patch("integrations.imports.steam.services.api_request")
    @patch("integrations.imports.steam.external_game")
    def test_import_steam_game_not_found_in_igdb(
        self,
        mock_external_game,
        mock_api_request,
    ):
        """Test handling of games not found in IGDB."""
        mock_api_request.return_value = {
            "response": {
                "games": [
                    {
                        "appid": 999,
                        "name": "Unknown Game",
                        "playtime_forever": 100,
                        "playtime_2weeks": 0,
                    },
                ],
            },
        }

        mock_external_game.return_value = None

        imported_counts, warnings = steam.importer(
            "76561198000000000",
            self.user,
            "new",
        )

        self.assertEqual(imported_counts.get(MediaTypes.GAME.value, 0), 0)

        self.assertIn("Unknown Game (999)", warnings)
        self.assertIn(f"Couldn't find a match in {Sources.IGDB.label}", warnings)

        self.assertEqual(Game.objects.filter(user=self.user).count(), 0)

    def test_determine_game_status_logic(self):
        """Test the status determination logic."""
        importer_instance = steam.SteamImporter("76561198000000000", self.user, "new")

        status = importer_instance._determine_game_status(0, 0)
        self.assertEqual(status, Status.PLANNING.value)

        status = importer_instance._determine_game_status(100, 50)
        self.assertEqual(status, Status.IN_PROGRESS.value)

        status = importer_instance._determine_game_status(100, 0)
        self.assertEqual(status, Status.PAUSED.value)

        status = importer_instance._determine_game_status(100, 0)
        self.assertEqual(status, Status.PAUSED.value)

    @patch("integrations.imports.steam.services.api_request")
    def test_import_steam_no_api_key(self, _mock_api_request):
        """Test handling when Steam API key is not configured."""
        with patch.object(settings, "STEAM_API_KEY", ""):
            with self.assertRaises(helpers.MediaImportError) as context:
                steam.importer("76561198000000000", self.user, "new")

            self.assertIn("Steam API key not configured", str(context.exception))

    @patch("integrations.imports.steam.services.api_request")
    def test_import_steam_no_games(self, mock_api_request):
        mock_api_request.return_value = {"response": {"games": []}}
        imported_counts, warnings = steam.importer(
            "76561198000000000", self.user, "new",
        )
        self.assertEqual(imported_counts.get(MediaTypes.GAME.value, 0), 0)

    @patch("integrations.imports.steam.services.api_request")
    def test_import_steam_no_games_in_response(self, mock_api_request):
        mock_api_request.return_value = {"response": {}}
        imported_counts, warnings = steam.importer(
            "76561198000000000", self.user, "new",
        )
        self.assertEqual(imported_counts, {})

    @patch("integrations.imports.steam.services.api_request")
    def test_import_steam_invalid_response(self, mock_api_request):
        mock_api_request.return_value = {}
        with self.assertRaises(helpers.MediaImportError) as ctx:
            steam.importer("76561198000000000", self.user, "new")
        self.assertIn("Invalid response", str(ctx.exception))

    @patch("integrations.imports.steam.services.api_request")
    def test_import_steam_bad_request(self, mock_api_request):
        response = Response()
        response.status_code = 400
        mock_api_request.side_effect = HTTPError(response=response)

        with self.assertRaises(helpers.MediaImportError) as ctx:
            steam.importer("76561198000000000", self.user, "new")
        self.assertIn("Bad request", str(ctx.exception))

    @patch("integrations.imports.steam.services.api_request")
    def test_import_steam_unauthorized(self, mock_api_request):
        response = Response()
        response.status_code = 401
        mock_api_request.side_effect = HTTPError(response=response)

        with self.assertRaises(helpers.MediaImportError) as ctx:
            steam.importer("76561198000000000", self.user, "new")
        self.assertIn("Invalid Steam API key", str(ctx.exception))

    @patch("integrations.imports.steam.services.api_request")
    def test_import_steam_unknown_http_error(self, mock_api_request):
        response = Response()
        response.status_code = 500
        mock_api_request.side_effect = HTTPError(response=response)

        with self.assertRaises(helpers.MediaImportError) as ctx:
            steam.importer("76561198000000000", self.user, "new")
        self.assertIn("Steam API error: 500", str(ctx.exception))

    @patch("integrations.imports.steam.time.sleep")
    @patch("integrations.imports.steam.services.api_request")
    def test_import_steam_rate_limit_retry_exhausted(self, mock_api_request, mock_sleep):
        response = Response()
        response.status_code = 429
        mock_api_request.side_effect = HTTPError(response=response)

        with self.assertRaises(helpers.MediaImportError) as ctx:
            steam.importer("76561198000000000", self.user, "new")
        self.assertIn("rate limit exceeded", str(ctx.exception))
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("app.providers.services.get_media_metadata")
    @patch("integrations.imports.steam.services.api_request")
    @patch("integrations.imports.steam.external_game")
    def test_process_game_skip_existing_new_mode(
        self,
        mock_external_game,
        mock_api_request,
        mock_global_metadata,
    ):
        from app.models import Game, Item
        mock_global_metadata.return_value = {
            "title": "Existing Game",
            "image": "img.jpg",
            "max_progress": None,
        }

        item = Item.objects.create(
            media_id="100",
            source=Sources.IGDB.value,
            media_type=MediaTypes.GAME.value,
            title="Existing Game",
            image="img.jpg",
        )
        Game.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        mock_api_request.return_value = {
            "response": {
                "games": [
                    {
                        "appid": 730,
                        "name": "Existing Game",
                        "playtime_forever": 100,
                        "playtime_2weeks": 0,
                    },
                ],
            },
        }
        mock_external_game.return_value = 100

        imported_counts, _ = steam.importer(
            "76561198000000000", self.user, "new",
        )
        self.assertEqual(imported_counts.get(MediaTypes.GAME.value, 0), 0)

    @patch("integrations.imports.steam.services.api_request")
    @patch("integrations.imports.steam.external_game")
    @patch("integrations.imports.steam.services.get_media_metadata")
    def test_process_game_provider_api_error_not_found(
        self,
        mock_get_metadata,
        mock_external_game,
        mock_api_request,
    ):
        from unittest.mock import Mock

        mock_api_request.return_value = {
            "response": {
                "games": [
                    {
                        "appid": 999,
                        "name": "Missing Game",
                        "playtime_forever": 100,
                        "playtime_2weeks": 0,
                    },
                ],
            },
        }
        mock_external_game.return_value = 999

        error = Mock()
        error.response.status_code = 404
        error.response.text = "Game with id 999 not found"
        from app.providers.services import ProviderAPIError
        mock_get_metadata.side_effect = ProviderAPIError(
            "IGDB", error, details="Game with id 999 not found",
        )

        imported_counts, warnings = steam.importer(
            "76561198000000000", self.user, "new",
        )
        self.assertEqual(imported_counts.get(MediaTypes.GAME.value, 0), 0)
        self.assertIn("Missing Game", warnings)

    @patch("integrations.imports.steam.services.api_request")
    @patch("integrations.imports.steam.external_game")
    @patch("integrations.imports.steam.services.get_media_metadata")
    def test_process_game_value_error(
        self,
        mock_get_metadata,
        mock_external_game,
        mock_api_request,
    ):
        mock_api_request.return_value = {
            "response": {
                "games": [
                    {
                        "appid": 999,
                        "name": "Bad Game",
                        "playtime_forever": 100,
                        "playtime_2weeks": 0,
                    },
                ],
            },
        }
        mock_external_game.return_value = 999
        mock_get_metadata.side_effect = ValueError("bad data")

        imported_counts, warnings = steam.importer(
            "76561198000000000", self.user, "new",
        )
        self.assertEqual(imported_counts.get(MediaTypes.GAME.value, 0), 0)
        self.assertIn("Bad Game", warnings)
