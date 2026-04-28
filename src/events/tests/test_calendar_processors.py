import datetime
from unittest.mock import MagicMock, patch

import requests
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from app.models import (
    TV,
    Anime,
    Book,
    Comic,
    Item,
    Manga,
    MediaTypes,
    Movie,
    Season,
    Sources,
    Status,
)
from app.providers import services
from events.calendar_processors import (
    fetch_releases,
    get_seasons_to_process,
    get_tvmaze_episode_map,
    process_tv,
)
from events.models import Event

IMG = "http://example.com/image.jpg"


class CalendarProcessorsTests(TestCase):
    """Tests for fetch_releases and TV processing functions."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="test",
            password="12345",
        )
        cls.anime_item = Item.objects.create(
            media_id="437",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Perfect Blue",
            image=IMG,
        )
        cls.movie_item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Godfather",
            image=IMG,
        )
        cls.tv_item = Item.objects.create(
            media_id="1396",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Breaking Bad",
            image=IMG,
        )
        cls.season_item = Item.objects.create(
            media_id="1396",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Breaking Bad",
            image=IMG,
            season_number=1,
        )
        cls.manga_item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.MANGA.value,
            title="Berserk",
            image=IMG,
        )
        cls.book_item = Item.objects.create(
            media_id="OL21733390M",
            source=Sources.OPENLIBRARY.value,
            media_type=MediaTypes.BOOK.value,
            title="1984",
            image=IMG,
        )
        cls.comic_item = Item.objects.create(
            media_id="60760",
            source=Sources.COMICVINE.value,
            media_type=MediaTypes.COMIC.value,
            title="Batman",
            image=IMG,
        )
        Anime.objects.create(
            item=cls.anime_item,
            user=cls.user,
            status=Status.PLANNING.value,
        )
        Movie.objects.create(
            item=cls.movie_item,
            user=cls.user,
            status=Status.PLANNING.value,
        )
        Book.objects.create(
            item=cls.book_item,
            user=cls.user,
            status=Status.PLANNING.value,
        )
        Comic.objects.create(
            item=cls.comic_item,
            user=cls.user,
            status=Status.PLANNING.value,
        )
        Manga.objects.create(
            item=cls.manga_item,
            user=cls.user,
            status=Status.PLANNING.value,
        )
        tv_obj = TV.objects.create(
            item=cls.tv_item,
            user=cls.user,
            status=Status.PLANNING.value,
        )
        Season.objects.create(
            item=cls.season_item,
            related_tv=tv_obj,
            user=cls.user,
            status=Status.PLANNING.value,
        )

    @patch("events.calendar_processors.process_tv")
    @patch("events.calendar_processors.process_other")
    @patch("events.calendar_processors.process_anime_bulk")
    def test_fetch_releases_all_types(self, mock_anime, mock_other, mock_tv):
        """Test fetch_releases processes all media types."""
        mock_tv.side_effect = lambda _, eb: eb.append(
            Event(item=self.season_item, content_number=1, datetime=timezone.now()),
        )
        mock_other.side_effect = lambda item, eb: eb.append(
            Event(item=item, content_number=1, datetime=timezone.now()),
        )
        mock_anime.side_effect = lambda items, eb: [
            eb.append(Event(item=i, content_number=1, datetime=timezone.now()))
            for i in items
        ]
        result = fetch_releases(self.user.id)
        mock_anime.assert_called_once()
        anime_items = mock_anime.call_args[0][0]
        self.assertEqual(len(anime_items), 1)
        self.assertEqual(anime_items[0].id, self.anime_item.id)
        self.assertTrue(Event.objects.filter(item=self.season_item).exists())
        self.assertEqual(mock_other.call_count, 3)
        for item in [self.anime_item, self.movie_item, self.manga_item, self.book_item]:
            self.assertTrue(Event.objects.filter(item=item).exists())
        expected_names = [
            "Perfect Blue",
            "The Godfather",
            "Breaking Bad",
            "Berserk",
            "1984",
        ]
        for name in expected_names:
            self.assertIn(name, result)

    @patch("events.calendar_processors.process_other")
    def test_fetch_releases_specific_items(self, mock_other):
        """Test fetch_releases with specific items only."""
        mock_other.side_effect = lambda item, eb: eb.append(
            Event(item=item, content_number=1, datetime=timezone.now()),
        )
        result = fetch_releases(self.user.id, [self.movie_item, self.book_item])
        self.assertEqual(mock_other.call_count, 2)
        self.assertFalse(Event.objects.filter(item=self.anime_item).exists())
        self.assertTrue(Event.objects.filter(item=self.movie_item).exists())
        self.assertTrue(Event.objects.filter(item=self.book_item).exists())
        self.assertIn("The Godfather", result)
        self.assertIn("1984", result)
        self.assertNotIn("Perfect Blue", result)

    @patch("events.calendar_processors.tmdb.tv")
    @patch("events.calendar_processors.tmdb.tv_with_seasons")
    @patch("events.calendar_processors.get_tvmaze_episode_map")
    def test_process_tv_season(self, mock_tvmaze, mock_seasons, mock_tv):
        """Test TV season processing with TVMaze episode times."""
        mock_tv.return_value = {
            "related": {
                "seasons": [
                    {"season_number": 1, "episodes": [1, 2, 3]},
                    {"season_number": 2, "episodes": [1, 2]},
                    {"season_number": 3, "episodes": [1]},
                ],
            },
            "next_episode_season": 2,
        }
        mock_seasons.return_value = {
            "season/1": {
                "image": IMG,
                "season_number": 1,
                "tvdb_id": "81189",
                "episodes": [
                    {"episode_number": 1, "air_date": "2008-01-20"},
                    {"episode_number": 2, "air_date": "2008-01-27"},
                    {"episode_number": 3, "air_date": "2008-02-03"},
                ],
            },
            "season/2": {
                "image": IMG,
                "season_number": 2,
                "tvdb_id": "81189",
                "episodes": [
                    {"episode_number": 1, "air_date": "2009-01-20"},
                    {"episode_number": 2, "air_date": "2009-01-27"},
                ],
            },
            "season/3": {
                "image": IMG,
                "season_number": 3,
                "tvdb_id": "81189",
                "episodes": [{"episode_number": 1, "air_date": "2010-01-20"}],
            },
        }
        mock_tvmaze.return_value = {
            "1_1": "2008-01-20T22:00:00+00:00",
            "1_2": "2008-01-27T22:00:00+00:00",
            "1_3": "2008-02-03T22:00:00+00:00",
        }
        events_bulk = []
        process_tv(self.tv_item, events_bulk)
        self.assertEqual(len(events_bulk), 6)
        self.assertEqual(events_bulk[0].item, self.season_item)
        self.assertEqual(events_bulk[0].content_number, 1)
        expected = datetime.datetime.fromisoformat("2008-01-20T22:00:00+00:00")
        self.assertEqual(events_bulk[0].datetime, expected)

    @patch("events.calendar_processors.tmdb.tv")
    def test_get_seasons_to_process(self, mock_tv):
        """Test empty list and next_episode_season filtering."""
        mock_tv.return_value = {"related": {"seasons": []}}
        self.assertEqual(get_seasons_to_process(self.tv_item), [])

        tv_item = Item.objects.create(
            media_id="2000",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Test TV",
            image=IMG,
        )
        TV.objects.create(
            item=tv_item,
            user=self.user,
            status=Status.PLANNING.value,
        )
        season_item = Item.objects.create(
            media_id="2000",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test TV",
            image=IMG,
            season_number=2,
        )
        Event.objects.create(
            item=season_item,
            content_number=1,
            datetime=timezone.now() - timezone.timedelta(days=30),
        )
        mock_tv.return_value = {
            "related": {"seasons": [{"season_number": 2}, {"season_number": 3}]},
            "next_episode_season": 2,
        }
        result = get_seasons_to_process(tv_item)
        self.assertIn(2, result)
        self.assertIn(3, result)

    @patch("events.calendar_processors.services.api_request")
    def test_tvmaze_episode_map(self, mock_api):
        """Test map creation, caching, and lookup failure."""
        cache.clear()
        mock_api.side_effect = [
            {"id": 12345},
            {
                "_embedded": {
                    "episodes": [
                        {
                            "season": 1,
                            "number": 1,
                            "airstamp": "2008-01-20T22:00:00+00:00",
                        },
                        {
                            "season": 1,
                            "number": 2,
                            "airstamp": "2008-01-27T22:00:00+00:00",
                        },
                    ],
                },
            },
        ]
        result = get_tvmaze_episode_map("81189")
        self.assertEqual(len(result), 2)
        self.assertEqual(result["1_1"], "2008-01-20T22:00:00+00:00")
        self.assertEqual(result["1_2"], "2008-01-27T22:00:00+00:00")
        self.assertEqual(cache.get("tvmaze_map_81189"), result)

        mock_api.reset_mock()
        get_tvmaze_episode_map("81189")
        mock_api.assert_not_called()

        cache.clear()
        mock_api.reset_mock()
        mock_api.side_effect = None
        mock_api.return_value = None
        self.assertEqual(get_tvmaze_episode_map("invalid_id"), {})

    def test_fetch_releases_manual_source(self):
        """Test fetch_releases returns early for manual sources."""
        manual_item = Item.objects.create(
            media_id="999",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.MOVIE.value,
            title="Manual Movie",
            image=IMG,
        )
        result = fetch_releases(self.user.id, [manual_item])
        self.assertEqual(result, "Manual sources are not processed")

    @patch("events.calendar_processors.get_items_to_process")
    def test_fetch_releases_no_items(self, mock_get_items):
        """Test fetch_releases returns message when no items to process."""
        mock_get_items.return_value = []
        result = fetch_releases(self.user.id)
        self.assertEqual(result, "No items to process")

    @patch("events.calendar_processors.tmdb.tv")
    def test_process_tv_provider_error(self, mock_tv):
        """Test process_tv handles ProviderAPIError gracefully."""
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.text = "Server error"
        mock_tv.side_effect = services.ProviderAPIError(
            provider=Sources.TMDB.value,
            error=error_response,
            details="API error",
        )
        events_bulk = []
        process_tv(self.tv_item, events_bulk)
        self.assertEqual(len(events_bulk), 0)

    @patch("events.calendar_processors.tmdb.tv_with_seasons")
    @patch("events.calendar_processors.tmdb.tv")
    def test_process_tv_missing_season_and_no_tvdb(self, mock_tv, mock_seasons):
        """Test missing season key in data and no TVDB ID path."""
        mock_tv.return_value = {
            "related": {
                "seasons": [{"season_number": 1}, {"season_number": 2}],
            },
        }
        mock_seasons.return_value = {
            "season/1": {
                "image": IMG,
                "season_number": 1,
                "tvdb_id": None,
                "episodes": [{"episode_number": 1, "air_date": "2008-01-20"}],
            },
        }
        events_bulk = []
        process_tv(self.tv_item, events_bulk)
        self.assertEqual(len(events_bulk), 1)

    @patch("events.calendar_processors.get_tvmaze_episode_map")
    @patch("events.calendar_processors.tmdb.tv_with_seasons")
    @patch("events.calendar_processors.tmdb.tv")
    def test_process_season_no_episodes(self, mock_tv, mock_seasons, mock_tvmaze):
        """Test season with no episodes returns early."""
        mock_tv.return_value = {
            "related": {"seasons": [{"season_number": 1}]},
        }
        mock_seasons.return_value = {
            "season/1": {
                "image": IMG,
                "season_number": 1,
                "tvdb_id": "81189",
                "episodes": [],
            },
        }
        mock_tvmaze.return_value = {}
        events_bulk = []
        process_tv(self.tv_item, events_bulk)
        self.assertEqual(len(events_bulk), 0)

    @patch("events.calendar_processors.services.api_request")
    def test_lookup_tvmaze_404(self, mock_api):
        """Test TVMaze lookup with 404 response."""
        cache.clear()
        error_response = MagicMock()
        error_response.status_code = 404
        error_response.text = "Not found"
        mock_api.side_effect = requests.exceptions.HTTPError(
            response=error_response,
        )
        result = get_tvmaze_episode_map("tvdb_404")
        self.assertEqual(result, {})

    @patch("events.calendar_processors.services.api_request")
    def test_lookup_tvmaze_500(self, mock_api):
        """Test TVMaze lookup with 500 response."""
        cache.clear()
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.text = "Server error"
        mock_api.side_effect = requests.exceptions.HTTPError(
            response=error_response,
        )
        result = get_tvmaze_episode_map("tvdb_500")
        self.assertEqual(result, {})

    @patch("events.calendar_processors.services.api_request")
    def test_lookup_tvmaze_no_id_in_response(self, mock_api):
        """Test TVMaze lookup returns no id field."""
        cache.clear()
        mock_api.return_value = {"name": "Some Show"}
        result = get_tvmaze_episode_map("tvdb_noid")
        self.assertEqual(result, {})


class CalendarProcessorsBranchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="cp_branch", password="x"
        )
        cls.tv_item = Item.objects.create(
            media_id="555",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Branch Show",
            image=IMG,
        )

    @patch("events.calendar_processors.tmdb.tv")
    def test_get_seasons_to_process_no_seasons(self, mock_tv):
        mock_tv.return_value = {"related": {}}
        result = get_seasons_to_process(self.tv_item)
        self.assertEqual(result, [])

    @patch("events.calendar_processors.tmdb.tv")
    def test_get_seasons_to_process_empty_seasons_list(self, mock_tv):
        mock_tv.return_value = {"related": {"seasons": []}}
        result = get_seasons_to_process(self.tv_item)
        self.assertEqual(result, [])

    @patch("events.calendar_processors.process_tv_seasons")
    @patch("events.calendar_processors.get_seasons_to_process")
    def test_process_tv_no_seasons_logs_and_returns(self, mock_seasons, mock_process):
        mock_seasons.return_value = []
        process_tv(self.tv_item, [])
        mock_process.assert_not_called()

    @patch("events.calendar_processors.get_seasons_to_process")
    def test_process_tv_provider_error_swallowed(self, mock_seasons):
        mock_seasons.side_effect = services.ProviderAPIError(
            Sources.TMDB.value,
            type(
                "Err",
                (),
                {"response": type("R", (), {"status_code": 500, "text": "x"})()},
            )(),
        )
        process_tv(self.tv_item, [])

    @patch("events.calendar_processors.get_seasons_to_process")
    def test_process_tv_unexpected_exception_swallowed(self, mock_seasons):
        mock_seasons.side_effect = ValueError("kaboom")
        process_tv(self.tv_item, [])


class AnimeBulkBranchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="ab_branch", password="x"
        )
        cls.anime_item = Item.objects.create(
            media_id="100",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="A",
            image=IMG,
        )

    @patch("events.calendar_processors.process_other")
    @patch("events.calendar_processors.get_anime_schedule_bulk")
    def test_anime_falls_back_to_process_other_when_no_data(
        self, mock_bulk, mock_other
    ):
        from events.calendar_processors import process_anime_bulk

        mock_bulk.return_value = {}
        process_anime_bulk([self.anime_item], [])
        mock_other.assert_called_once()

    def test_process_anime_bulk_empty_returns_early(self):
        from events.calendar_processors import process_anime_bulk

        process_anime_bulk([], [])

    def test_convert_anime_episode_none_airing_uses_sentinel(self):
        from events.calendar_processors import SENTINEL_DATETIME, _convert_anime_episode

        ev = _convert_anime_episode(self.anime_item, {"airingAt": None, "episode": 1})
        self.assertEqual(ev.datetime, SENTINEL_DATETIME)


class FillMissingEpisodesTests(TestCase):
    @patch("events.calendar_processors.services.get_media_metadata")
    def test_returns_none_when_mal_episode_count_higher(self, mock_meta):
        from events.calendar_processors import _fill_missing_episodes

        mock_meta.return_value = {"max_progress": 20}
        result = _fill_missing_episodes(
            schedule=[],
            total_episodes=12,
            mal_id="42",
            end_date={"year": 2025, "month": 1, "day": 1},
        )
        self.assertIsNone(result)


class GetEpisodeDatetimeBranchTests(TestCase):
    def test_invalid_air_date_returns_sentinel(self):
        from events.calendar_processors import SENTINEL_DATETIME, get_episode_datetime

        result = get_episode_datetime(
            episode={"air_date": "not-a-date"},
            season_number=1,
            episode_number=1,
            tvmaze_map={},
        )
        self.assertEqual(result, SENTINEL_DATETIME)
