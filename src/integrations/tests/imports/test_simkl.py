from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import (
    TV,
    Anime,
    Episode,
    Item,
    MediaTypes,
    Movie,
    Season,
    Status,
)
from app.providers.services import ProviderAPIError
from integrations.imports import (
    helpers,
    simkl,
)
from integrations.imports.helpers import MediaImportError

mock_path = Path(__file__).resolve().parent.parent / "mock_data"
app_mock_path = (
    Path(__file__).resolve().parent.parent.parent.parent / "app" / "tests" / "mock_data"
)


class SimklImporterMixin:
    """Shared setUp and helpers for SIMKL import tests."""

    def setUp(self):
        credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**credentials)
        self.importer = simkl.SimklImporter(
            helpers.encrypt("token"),
            self.user,
            "new",
        )

    def _make_tv_entry(
        self, title, tmdb_id, status="watching", rating=5, seasons=None, memo=None
    ):
        entry = {
            "last_watched_at": "2023-01-01T00:00:00Z",
            "show": {"title": title, "ids": {"tmdb": tmdb_id} if tmdb_id else {}},
            "status": status,
            "user_rating": rating,
            "memo": memo or {},
        }
        if seasons is not None:
            entry["seasons"] = seasons
        return entry

    def _make_movie_entry(
        self, title, tmdb_id, status="completed", rating=5, last_watched=None
    ):
        return {
            "added_to_watchlist_at": "2023-01-01T00:00:00Z",
            "movie": {"title": title, "ids": {"tmdb": tmdb_id} if tmdb_id else {}},
            "status": status,
            "user_rating": rating,
            "last_watched_at": last_watched or "2023-01-01T00:00:00Z",
            "memo": {},
        }

    def _make_anime_entry(
        self,
        title,
        mal_id,
        status="completed",
        rating=5,
        episodes=0,
        last_watched=None,
        memo=None,
    ):
        return {
            "added_to_watchlist_at": "2023-01-01T00:00:00Z",
            "show": {"title": title, "ids": {"mal": mal_id} if mal_id else {}},
            "status": status,
            "user_rating": rating,
            "watched_episodes_count": episodes,
            "last_watched_at": last_watched,
            "memo": memo or {},
        }

    def _make_user_list(self, shows=None, movies=None, anime=None):
        result = {}
        if shows is not None:
            result["shows"] = shows
        if movies is not None:
            result["movies"] = movies
        if anime is not None:
            result["anime"] = anime
        return result

    def _make_not_found_error(self, provider_name):
        error_response = Mock()
        error_response.status_code = requests.codes.not_found
        error_response.text = "Not found"
        return ProviderAPIError(provider_name, Mock(response=error_response))


class TestSimklFullImport(SimklImporterMixin, TestCase):
    """Test full import flow and status/date mapping."""

    @patch("integrations.imports.simkl.SimklImporter._get_user_list")
    def test_importer(self, user_list):
        """Test importing media from SIMKL."""
        user_list.return_value = {
            "shows": [
                {
                    "last_watched_at": "2023-01-02T00:00:00Z",
                    "show": {"title": "Breaking Bad", "ids": {"tmdb": 1396}},
                    "status": "watching",
                    "user_rating": 8,
                    "seasons": [
                        {
                            "number": 1,
                            "episodes": [
                                {"number": 1},
                                {"number": 2, "watched_at": "2023-01-02T00:00:00Z"},
                            ],
                        },
                    ],
                    "memo": {},
                },
            ],
            "movies": [
                {
                    "added_to_watchlist_at": "2023-01-01T00:00:00Z",
                    "movie": {"title": "Perfect Blue", "ids": {"tmdb": 10494}},
                    "status": "completed",
                    "user_rating": 9,
                    "last_watched_at": "2023-02-01T00:00:00Z",
                    "memo": {},
                },
            ],
            "anime": [
                {
                    "added_to_watchlist_at": "2023-01-01T00:00:00Z",
                    "show": {"title": "Example Anime", "ids": {"mal": 1}},
                    "status": "plantowatch",
                    "user_rating": 7,
                    "watched_episodes_count": 0,
                    "last_watched_at": None,
                    "memo": {"text": "Great series!"},
                },
            ],
        }

        imported_counts, warnings = self.importer.import_data()

        self.assertEqual(imported_counts[MediaTypes.TV.value], 1)
        self.assertEqual(imported_counts[MediaTypes.MOVIE.value], 1)
        self.assertEqual(imported_counts[MediaTypes.ANIME.value], 1)
        self.assertEqual(warnings, "")

        tv_item = Item.objects.get(media_type=MediaTypes.TV.value)
        self.assertEqual(tv_item.title, "Breaking Bad")
        tv_obj = TV.objects.get(item=tv_item)
        self.assertEqual(tv_obj.status, Status.IN_PROGRESS.value)
        self.assertEqual(tv_obj.score, 8)

        movie_item = Item.objects.get(media_type=MediaTypes.MOVIE.value)
        self.assertEqual(movie_item.title, "Perfect Blue")
        movie_obj = Movie.objects.get(item=movie_item)
        self.assertEqual(movie_obj.status, Status.COMPLETED.value)
        self.assertEqual(movie_obj.score, 9)
        self.assertEqual(movie_obj.progress, 1)

        anime_item = Item.objects.get(media_type=MediaTypes.ANIME.value)
        self.assertEqual(anime_item.title, "Cowboy Bebop")
        anime_obj = Anime.objects.get(item=anime_item)
        self.assertEqual(anime_obj.status, Status.PLANNING.value)
        self.assertEqual(anime_obj.score, 7)
        self.assertEqual(anime_obj.notes, "Great series!")

    @patch("integrations.imports.simkl.SimklImporter._get_user_list")
    def test_import_empty_data(self, mock_user_list):
        mock_user_list.return_value = None
        imported_counts, warnings = self.importer.import_data()
        self.assertEqual(imported_counts, {})
        self.assertEqual(warnings, "")

    def test_get_status(self):
        self.assertEqual(self.importer._get_status("completed"), Status.COMPLETED.value)
        self.assertEqual(
            self.importer._get_status("watching"),
            Status.IN_PROGRESS.value,
        )
        self.assertEqual(
            self.importer._get_status("plantowatch"),
            Status.PLANNING.value,
        )
        self.assertEqual(self.importer._get_status("hold"), Status.PAUSED.value)
        self.assertEqual(self.importer._get_status("dropped"), Status.DROPPED.value)
        self.assertEqual(
            self.importer._get_status("unknown"),
            Status.IN_PROGRESS.value,
        )

    def test_get_date(self):
        self.assertEqual(
            self.importer._get_date("2023-01-01T00:00:00Z"),
            datetime(2023, 1, 1, 0, 0, 0, tzinfo=UTC),
        )
        self.assertIsNone(self.importer._get_date(None))

    def test_importer_function(self):
        with patch.object(
            simkl.SimklImporter, "import_data", return_value=({}, "")
        ) as mock:
            result = simkl.importer(helpers.encrypt("token"), self.user, "new")
            mock.assert_called_once()
            self.assertEqual(result, ({}, ""))


class TestSimklSeasonImport(SimklImporterMixin, TestCase):
    """Test season/episode import with status logic."""

    def _build_season_metadata(self):
        return {
            "title": "Breaking Bad",
            "image": "https://image.tmdb.org/t/p/w500/test.jpg",
            "season/1": {
                "image": "https://image.tmdb.org/t/p/w500/season1.jpg",
                "max_progress": 7,
                "episodes": [
                    {"episode_number": i, "still_path": f"/ep{i}.jpg"}
                    for i in range(1, 8)
                ],
            },
            "season/2": {
                "image": "https://image.tmdb.org/t/p/w500/season2.jpg",
                "max_progress": 13,
            },
        }

    def _build_completed_season_user_list(self):
        return self._make_user_list(
            shows=[
                {
                    "last_watched_at": "2023-01-15T00:00:00Z",
                    "show": {"title": "Breaking Bad", "ids": {"tmdb": 1396}},
                    "status": "watching",
                    "user_rating": 9,
                    "seasons": [
                        {
                            "number": 1,
                            "episodes": [
                                {"number": i, "watched_at": f"2023-01-0{i}T00:00:00Z"}
                                for i in range(1, 8)
                            ],
                        },
                    ],
                    "memo": {},
                },
            ],
            movies=[],
            anime=[],
        )

    @patch("integrations.imports.simkl.SimklImporter._get_user_list")
    @patch("app.providers.tmdb.tv_with_seasons")
    def test_season_status_logic_with_completed_seasons(
        self,
        mock_tv_with_seasons,
        mock_user_list,
    ):
        """Test that seasons are marked as completed when all episodes are watched."""
        mock_tv_with_seasons.return_value = self._build_season_metadata()
        mock_user_list.return_value = self._build_completed_season_user_list()

        imported_counts, _ = self.importer.import_data()

        self.assertEqual(imported_counts[MediaTypes.TV.value], 1)
        self.assertEqual(imported_counts[MediaTypes.SEASON.value], 1)
        self.assertEqual(imported_counts[MediaTypes.EPISODE.value], 7)

        tv_item = Item.objects.get(media_type=MediaTypes.TV.value)
        tv_obj = TV.objects.get(item=tv_item)
        self.assertEqual(tv_obj.status, Status.IN_PROGRESS.value)

        season1_item = Item.objects.get(
            media_type=MediaTypes.SEASON.value,
            season_number=1,
        )
        season1_obj = Season.objects.get(item=season1_item)
        self.assertEqual(
            season1_obj.status,
            Status.COMPLETED.value,
            "Season 1 should be completed when all episodes are watched",
        )

        season1_episodes = Episode.objects.filter(
            item__season_number=1,
            item__media_type=MediaTypes.EPISODE.value,
        )
        self.assertEqual(season1_episodes.count(), 7)

        for episode in season1_episodes:
            self.assertIsNotNone(episode.end_date)

    @patch("integrations.imports.simkl.SimklImporter._get_user_list")
    def test_tv_no_seasons_key(self, mock_user_list):
        mock_user_list.return_value = self._make_user_list(
            shows=[self._make_tv_entry("Breaking Bad", 1396)],
        )

        imported_counts, warnings = self.importer.import_data()
        self.assertEqual(imported_counts[MediaTypes.TV.value], 1)


class TestSimklErrorPaths(SimklImporterMixin, TestCase):
    """Test error handling: missing IDs, duplicates, and provider failures."""

    @patch("integrations.imports.simkl.SimklImporter._get_user_list")
    def test_tv_no_tmdb_id(self, mock_user_list):
        mock_user_list.return_value = self._make_user_list(
            shows=[self._make_tv_entry("No ID Show", None, seasons=[])],
        )
        imported_counts, warnings = self.importer.import_data()
        self.assertNotIn(MediaTypes.TV.value, imported_counts)
        self.assertIn("No TMDB ID found", warnings)

    @patch("integrations.imports.simkl.SimklImporter._get_user_list")
    def test_tv_duplicate_in_list(self, mock_user_list):
        entry = self._make_tv_entry("Dupe Show", 1396, rating=8, seasons=[])
        mock_user_list.return_value = self._make_user_list(shows=[entry, entry])
        imported_counts, warnings = self.importer.import_data()
        self.assertEqual(imported_counts.get(MediaTypes.TV.value, 0), 1)
        self.assertIn("already present", warnings)

    @patch("integrations.imports.simkl.SimklImporter._get_user_list")
    @patch("app.providers.tmdb.tv_with_seasons")
    def test_tv_not_found_in_tmdb(self, mock_tv, mock_user_list):
        mock_tv.side_effect = self._make_not_found_error("TMDB")
        mock_user_list.return_value = self._make_user_list(
            shows=[
                self._make_tv_entry(
                    "Missing Show",
                    99999,
                    seasons=[{"number": 1, "episodes": [{"number": 1}]}],
                )
            ],
        )
        imported_counts, warnings = self.importer.import_data()
        self.assertIn("not found", warnings)

    @patch("integrations.imports.simkl.SimklImporter._get_user_list")
    def test_movie_no_tmdb_id(self, mock_user_list):
        mock_user_list.return_value = self._make_user_list(
            movies=[self._make_movie_entry("No ID Movie", None, last_watched=None)],
        )
        imported_counts, warnings = self.importer.import_data()
        self.assertNotIn(MediaTypes.MOVIE.value, imported_counts)
        self.assertIn("No TMDB ID found", warnings)

    @patch("integrations.imports.simkl.SimklImporter._get_user_list")
    def test_movie_duplicate_in_list(self, mock_user_list):
        entry = self._make_movie_entry("Dupe Movie", 10494, rating=8)
        mock_user_list.return_value = self._make_user_list(movies=[entry, entry])
        imported_counts, warnings = self.importer.import_data()
        self.assertEqual(imported_counts.get(MediaTypes.MOVIE.value, 0), 1)
        self.assertIn("already present", warnings)

    @patch("integrations.imports.simkl.SimklImporter._get_user_list")
    @patch("app.providers.tmdb.movie")
    def test_movie_not_found_in_tmdb(self, mock_movie, mock_user_list):
        mock_movie.side_effect = self._make_not_found_error("TMDB")
        mock_user_list.return_value = self._make_user_list(
            movies=[self._make_movie_entry("Missing Movie", 99999)],
        )
        imported_counts, warnings = self.importer.import_data()
        self.assertIn("not found", warnings)

    @patch("integrations.imports.simkl.SimklImporter._get_user_list")
    def test_anime_no_mal_id(self, mock_user_list):
        mock_user_list.return_value = self._make_user_list(
            anime=[self._make_anime_entry("No ID Anime", None)],
        )
        imported_counts, warnings = self.importer.import_data()
        self.assertNotIn(MediaTypes.ANIME.value, imported_counts)
        self.assertIn("No MyAnimeList ID found", warnings)

    @patch("integrations.imports.simkl.SimklImporter._get_user_list")
    def test_anime_duplicate_in_list(self, mock_user_list):
        entry = self._make_anime_entry(
            "Dupe Anime",
            1,
            rating=8,
            episodes=12,
            last_watched="2023-01-01T00:00:00Z",
        )
        mock_user_list.return_value = self._make_user_list(anime=[entry, entry])
        imported_counts, warnings = self.importer.import_data()
        self.assertEqual(imported_counts.get(MediaTypes.ANIME.value, 0), 1)
        self.assertIn("already present", warnings)

    @patch("integrations.imports.simkl.SimklImporter._get_user_list")
    @patch("app.providers.mal.anime")
    def test_anime_not_found_in_mal(self, mock_anime, mock_user_list):
        mock_anime.side_effect = self._make_not_found_error("MAL")
        mock_user_list.return_value = self._make_user_list(
            anime=[
                self._make_anime_entry(
                    "Missing Anime",
                    99999,
                    last_watched="2023-01-01T00:00:00Z",
                )
            ],
        )
        imported_counts, warnings = self.importer.import_data()
        self.assertIn("not found", warnings)


class TestSimklDateHelpers(SimklImporterMixin, TestCase):
    """Test date extraction and formatting helpers."""

    def test_get_start_date_with_seasons(self):
        anime = {
            "seasons": [
                {
                    "episodes": [
                        {"watched_at": "2023-03-01T00:00:00Z"},
                        {"watched_at": "2023-01-01T00:00:00Z"},
                        {"watched_at": "2023-02-01T00:00:00Z"},
                    ],
                },
            ],
        }
        result = self.importer._get_start_date(anime)
        self.assertEqual(result, datetime(2023, 1, 1, 0, 0, 0, tzinfo=UTC))

    def test_get_start_date_no_seasons(self):
        result = self.importer._get_start_date({})
        self.assertIsNone(result)

    def test_get_start_date_no_watched_at(self):
        anime = {"seasons": [{"episodes": [{}, {}]}]}
        result = self.importer._get_start_date(anime)
        self.assertIsNone(result)

    def test_get_end_date_completed(self):
        result = self.importer._get_end_date(
            Status.COMPLETED.value,
            "2023-01-01T00:00:00Z",
        )
        self.assertEqual(result, datetime(2023, 1, 1, 0, 0, 0, tzinfo=UTC))

    def test_get_end_date_not_completed(self):
        result = self.importer._get_end_date(
            Status.IN_PROGRESS.value,
            "2023-01-01T00:00:00Z",
        )
        self.assertIsNone(result)

    def test_get_history_date_last_watched(self):
        entry = {"last_watched_at": "2023-01-01T00:00:00Z"}
        result = self.importer._get_history_date(entry)
        self.assertEqual(result, datetime(2023, 1, 1, 0, 0, 0, tzinfo=UTC))

    def test_get_history_date_added_to_watchlist(self):
        entry = {
            "last_watched_at": None,
            "added_to_watchlist_at": "2023-02-01T00:00:00Z",
        }
        result = self.importer._get_history_date(entry)
        self.assertEqual(result, datetime(2023, 2, 1, 0, 0, 0, tzinfo=UTC))

    def test_get_history_date_fallback_to_now(self):
        entry = {"last_watched_at": None, "added_to_watchlist_at": None}
        result = self.importer._get_history_date(entry)
        self.assertIsNotNone(result)

    def test_get_episode_image_no_match(self):
        metadata = {
            "season/1": {
                "episodes": [{"episode_number": 1, "still_path": "/ep1.jpg"}],
            },
        }
        from django.conf import settings

        result = self.importer._get_episode_image(
            {"number": 99},
            1,
            metadata,
        )
        self.assertEqual(result, settings.IMG_NONE)


class TestSimklAuth(TestCase):
    """Test SIMKL OAuth token and username retrieval."""

    @patch("app.providers.services.api_request")
    def test_get_token(self, mock_api_request):
        mock_api_request.side_effect = [
            {"access_token": "test_access"},
            {"user": {"name": "testuser"}},
        ]

        request = Mock()
        request.GET = {"code": "auth_code"}
        request.build_absolute_uri.return_value = "http://example.com/callback"

        result = simkl.get_token(request)
        self.assertEqual(result["access_token"], "test_access")
        self.assertEqual(result["username"], "testuser")

    @patch("app.providers.services.api_request")
    def test_get_token_unauthorized(self, mock_api_request):
        error_response = Mock()
        error_response.status_code = requests.codes.unauthorized
        error_response.text = "Unauthorized"
        mock_api_request.side_effect = ProviderAPIError(
            "SIMKL",
            Mock(response=error_response),
        )

        request = Mock()
        request.GET = {"code": "bad_code"}
        request.build_absolute_uri.return_value = "http://example.com/callback"

        with self.assertRaises(MediaImportError):
            simkl.get_token(request)

    @patch("app.providers.services.api_request")
    def test_get_username(self, mock_api_request):
        mock_api_request.return_value = {"user": {"name": "testuser"}}
        result = simkl.get_username("test_token")
        self.assertEqual(result, "testuser")

    @patch("app.providers.services.api_request")
    def test_get_username_unauthorized(self, mock_api_request):
        error_response = Mock()
        error_response.status_code = requests.codes.unauthorized
        error_response.text = "Unauthorized"
        mock_api_request.side_effect = ProviderAPIError(
            "SIMKL",
            Mock(response=error_response),
        )

        with self.assertRaises(MediaImportError):
            simkl.get_username("bad_token")
