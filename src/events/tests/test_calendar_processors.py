import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

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
    anilist_date_parser,
    date_parser,
    fetch_releases,
    get_anime_schedule_bulk,
    get_seasons_to_process,
    get_tvmaze_episode_map,
    process_anime_bulk,
    process_comic,
    process_other,
    process_tv,
)
from events.models import Event

IMG = "http://example.com/image.jpg"


class CalendarProcessorsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="test", password="12345",
        )
        cls.anime_item = Item.objects.create(
            media_id="437", source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value, title="Perfect Blue", image=IMG,
        )
        Anime.objects.create(
            item=cls.anime_item, user=cls.user, status=Status.PLANNING.value,
        )
        cls.movie_item = Item.objects.create(
            media_id="238", source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value, title="The Godfather", image=IMG,
        )
        Movie.objects.create(
            item=cls.movie_item, user=cls.user, status=Status.PLANNING.value,
        )
        cls.tv_item = Item.objects.create(
            media_id="1396", source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value, title="Breaking Bad", image=IMG,
        )
        tv_object = TV.objects.create(
            item=cls.tv_item, user=cls.user, status=Status.PLANNING.value,
        )
        cls.season_item = Item.objects.create(
            media_id="1396", source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value, title="Breaking Bad",
            image=IMG, season_number=1,
        )
        Season.objects.create(
            item=cls.season_item, related_tv=tv_object,
            user=cls.user, status=Status.PLANNING.value,
        )
        cls.manga_item = Item.objects.create(
            media_id="1", source=Sources.MAL.value,
            media_type=MediaTypes.MANGA.value, title="Berserk", image=IMG,
        )
        Manga.objects.create(
            item=cls.manga_item, user=cls.user, status=Status.PLANNING.value,
        )
        cls.book_item = Item.objects.create(
            media_id="OL21733390M", source=Sources.OPENLIBRARY.value,
            media_type=MediaTypes.BOOK.value, title="1984", image=IMG,
        )
        Book.objects.create(
            item=cls.book_item, user=cls.user, status=Status.PLANNING.value,
        )
        cls.comic_item = Item.objects.create(
            media_id="60760", source=Sources.COMICVINE.value,
            media_type=MediaTypes.COMIC.value, title="Batman", image=IMG,
        )
        Comic.objects.create(
            item=cls.comic_item, user=cls.user, status=Status.PLANNING.value,
        )

    # --- fetch_releases ---

    @patch("events.calendar_processors.process_tv")
    @patch("events.calendar_processors.process_other")
    @patch("events.calendar_processors.process_anime_bulk")
    def test_fetch_releases_all_types(self, mock_anime, mock_other, mock_tv):
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
        self.assertTrue(Event.objects.filter(item=self.anime_item).exists())
        self.assertTrue(Event.objects.filter(item=self.movie_item).exists())
        self.assertTrue(Event.objects.filter(item=self.manga_item).exists())
        self.assertTrue(Event.objects.filter(item=self.book_item).exists())
        self.assertIn("Perfect Blue", result)
        self.assertIn("The Godfather", result)
        self.assertIn("Breaking Bad", result)
        self.assertIn("Berserk", result)
        self.assertIn("1984", result)

    @patch("events.calendar_processors.process_other")
    def test_fetch_releases_specific_items(self, mock_other):
        mock_other.side_effect = lambda item, eb: eb.append(
            Event(item=item, content_number=1, datetime=timezone.now()),
        )

        result = fetch_releases(self.user.id, [self.movie_item, self.book_item])

        self.assertEqual(mock_other.call_count, 2)
        self.assertFalse(Event.objects.filter(item=self.anime_item).exists())
        self.assertTrue(Event.objects.filter(item=self.movie_item).exists())
        self.assertFalse(Event.objects.filter(item=self.season_item).exists())
        self.assertFalse(Event.objects.filter(item=self.manga_item).exists())
        self.assertTrue(Event.objects.filter(item=self.book_item).exists())
        self.assertIn("The Godfather", result)
        self.assertIn("1984", result)
        self.assertNotIn("Perfect Blue", result)
        self.assertNotIn("Breaking Bad", result)
        self.assertNotIn("Berserk", result)

    # --- TV processing ---

    @patch("events.calendar_processors.tmdb.tv")
    @patch("events.calendar_processors.tmdb.tv_with_seasons")
    @patch("events.calendar_processors.get_tvmaze_episode_map")
    def test_process_tv_season(self, mock_tvmaze, mock_seasons, mock_tv):
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
                "image": IMG, "season_number": 1,
                "episodes": [
                    {"episode_number": 1, "air_date": "2008-01-20"},
                    {"episode_number": 2, "air_date": "2008-01-27"},
                    {"episode_number": 3, "air_date": "2008-02-03"},
                ],
                "tvdb_id": "81189",
            },
            "season/2": {
                "image": IMG, "season_number": 2,
                "episodes": [
                    {"episode_number": 1, "air_date": "2009-01-20"},
                    {"episode_number": 2, "air_date": "2009-01-27"},
                ],
                "tvdb_id": "81189",
            },
            "season/3": {
                "image": IMG, "season_number": 3,
                "episodes": [{"episode_number": 1, "air_date": "2010-01-20"}],
                "tvdb_id": "81189",
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
    def test_get_seasons_empty_list(self, mock_tv):
        mock_tv.return_value = {"related": {"seasons": []}}
        self.assertEqual(get_seasons_to_process(self.tv_item), [])

    @patch("events.calendar_processors.tmdb.tv")
    def test_get_seasons_next_episode(self, mock_tv):
        tv_item = Item.objects.create(
            media_id="2000", source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value, title="Test TV", image=IMG,
        )
        TV.objects.create(
            item=tv_item, user=self.user, status=Status.PLANNING.value,
        )
        season_item = Item.objects.create(
            media_id="2000", source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value, title="Test TV",
            image=IMG, season_number=2,
        )
        Event.objects.create(
            item=season_item, content_number=1,
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
        cache.clear()
        mock_api.side_effect = [
            {"id": 12345},
            {
                "_embedded": {
                    "episodes": [
                        {
                            "season": 1, "number": 1,
                            "airstamp": "2008-01-20T22:00:00+00:00",
                        },
                        {
                            "season": 1, "number": 2,
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

    @patch("events.calendar_processors.services.api_request")
    def test_tvmaze_episode_map_lookup_failure(self, mock_api):
        cache.clear()
        mock_api.return_value = None
        self.assertEqual(get_tvmaze_episode_map("invalid_id"), {})
        mock_api.assert_called_once()

    # --- Anime processing ---

    @patch("events.calendar_processors.services.api_request")
    def test_process_anime_bulk(self, mock_api):
        mock_api.return_value = {
            "data": {
                "Page": {
                    "pageInfo": {"hasNextPage": False},
                    "media": [{
                        "idMal": 437,
                        "endDate": {"year": 1997, "month": 8, "day": 5},
                        "episodes": 1,
                        "airingSchedule": {
                            "nodes": [{"episode": 1, "airingAt": 870739200}],
                        },
                    }],
                },
            },
        }

        events_bulk = []
        process_anime_bulk([self.anime_item], events_bulk)

        self.assertEqual(len(events_bulk), 1)
        self.assertEqual(events_bulk[0].item, self.anime_item)
        self.assertEqual(events_bulk[0].content_number, 1)
        expected = datetime.datetime.fromtimestamp(870739200, tz=ZoneInfo("UTC"))
        self.assertEqual(events_bulk[0].datetime, expected)

    @patch("events.calendar_processors.services.get_media_metadata")
    @patch("events.calendar_processors.services.api_request")
    def test_anime_bulk_no_anilist_match(self, mock_api, mock_metadata):
        mock_api.return_value = {
            "data": {
                "Page": {
                    "pageInfo": {"hasNextPage": False},
                    "media": [],
                },
            },
        }
        mock_metadata.return_value = {
            "max_progress": 1,
            "details": {"end_date": "1997-08-05"},
        }

        events_bulk = []
        process_anime_bulk([self.anime_item], events_bulk)
        self.assertEqual(len(events_bulk), 1)

    @patch("events.calendar_processors.services.api_request")
    def test_anime_schedule_bulk(self, mock_api):
        mock_api.return_value = {
            "data": {
                "Page": {
                    "pageInfo": {"hasNextPage": False},
                    "media": [{
                        "idMal": 437,
                        "startDate": {"year": 1997, "month": 8, "day": 5},
                        "endDate": {"year": 1997, "month": 8, "day": 5},
                        "episodes": 1,
                        "airingSchedule": {
                            "nodes": [{"episode": 1, "airingAt": 870739200}],
                        },
                    }],
                },
            },
        }

        result = get_anime_schedule_bulk(["437"])
        self.assertIn("437", result)
        self.assertEqual(len(result["437"]), 1)
        self.assertEqual(result["437"][0]["episode"], 1)
        self.assertEqual(result["437"][0]["airingAt"], 870739200)

    @patch("events.calendar_processors.services.get_media_metadata")
    @patch("events.calendar_processors.services.api_request")
    def test_anime_schedule_bulk_no_airing(self, mock_api, mock_metadata):
        mock_api.return_value = {
            "data": {
                "Page": {
                    "pageInfo": {"hasNextPage": False},
                    "media": [{
                        "idMal": 437,
                        "endDate": {"year": 1997, "month": 8, "day": 12},
                        "episodes": 2,
                        "airingSchedule": {"nodes": []},
                    }],
                },
            },
        }
        mock_metadata.return_value = {
            "max_progress": 2,
            "details": {"end_date": "1997-08-12"},
        }

        result = get_anime_schedule_bulk(["437"])
        self.assertIn("437", result)
        self.assertEqual(len(result["437"]), 1)
        self.assertEqual(result["437"][0]["episode"], 2)
        dt = datetime.datetime.fromtimestamp(
            result["437"][0]["airingAt"], tz=ZoneInfo("UTC"),
        )
        self.assertEqual(dt.year, 1997)
        self.assertEqual(dt.month, 8)
        self.assertEqual(dt.day, 12)

    @patch("events.calendar_processors.services.api_request")
    def test_anime_schedule_bulk_filter_episodes(self, mock_api):
        mock_api.return_value = {
            "data": {
                "Page": {
                    "pageInfo": {"hasNextPage": False},
                    "media": [{
                        "idMal": 437,
                        "endDate": {"year": 1997, "month": 8, "day": 5},
                        "episodes": 1,
                        "airingSchedule": {
                            "nodes": [
                                {"episode": 1, "airingAt": 870739200},
                                {"episode": 2, "airingAt": 870825600},
                            ],
                        },
                    }],
                },
            },
        }

        result = get_anime_schedule_bulk(["437"])
        self.assertIn("437", result)
        self.assertEqual(len(result["437"]), 1)
        self.assertEqual(result["437"][0]["episode"], 1)

    def test_anilist_date_parser_complete(self):
        result = anilist_date_parser({"year": 2024, "month": 3, "day": 28})
        dt = datetime.datetime.fromtimestamp(result, tz=ZoneInfo("UTC"))
        self.assertEqual(dt.year, 2024)
        self.assertEqual(dt.month, 3)
        self.assertEqual(dt.day, 28)

    def test_anilist_date_parser_partial_day(self):
        result = anilist_date_parser({"year": 2024, "month": 3, "day": None})
        dt = datetime.datetime.fromtimestamp(result, tz=ZoneInfo("UTC"))
        self.assertEqual(dt.year, 2024)
        self.assertEqual(dt.month, 3)
        self.assertEqual(dt.day, 1)

    def test_anilist_date_parser_partial_month_day(self):
        result = anilist_date_parser({"year": 2024, "month": None, "day": None})
        dt = datetime.datetime.fromtimestamp(result, tz=ZoneInfo("UTC"))
        self.assertEqual(dt.year, 2024)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 1)

    def test_anilist_date_parser_missing_year(self):
        self.assertIsNone(
            anilist_date_parser({"year": None, "month": 3, "day": 28})
        )

    # --- Other media processing ---

    @patch("events.calendar_processors.services.get_media_metadata")
    def test_process_other_movie(self, mock_metadata):
        mock_metadata.return_value = {
            "max_progress": 1,
            "details": {"release_date": "1999-10-15"},
        }
        events_bulk = []
        process_other(self.movie_item, events_bulk)
        self.assertEqual(len(events_bulk), 1)
        self.assertEqual(events_bulk[0].item, self.movie_item)
        self.assertIsNone(events_bulk[0].content_number)
        self.assertEqual(events_bulk[0].datetime, date_parser("1999-10-15"))

    @patch("events.calendar_processors.services.get_media_metadata")
    def test_process_other_book(self, mock_metadata):
        mock_metadata.return_value = {
            "max_progress": 328,
            "details": {"publish_date": "1949-06-08"},
        }
        events_bulk = []
        process_other(self.book_item, events_bulk)
        self.assertEqual(len(events_bulk), 1)
        self.assertEqual(events_bulk[0].item, self.book_item)
        self.assertEqual(events_bulk[0].content_number, 328)
        self.assertEqual(events_bulk[0].datetime, date_parser("1949-06-08"))

    @patch("events.calendar_processors.services.get_media_metadata")
    def test_process_other_manga(self, mock_metadata):
        mock_metadata.return_value = {
            "details": {"end_date": "2023-12-22"},
            "max_progress": 375,
        }
        events_bulk = []
        process_other(self.manga_item, events_bulk)
        self.assertEqual(len(events_bulk), 1)
        self.assertEqual(events_bulk[0].item, self.manga_item)
        self.assertEqual(events_bulk[0].content_number, 375)
        self.assertEqual(events_bulk[0].datetime, date_parser("2023-12-22"))

    @patch("events.calendar_processors.services.get_media_metadata")
    def test_process_other_manga_ongoing_no_chapters(self, mock_metadata):
        mock_metadata.return_value = {
            "details": {"end_date": None},
            "max_progress": None,
        }
        events_bulk = []
        process_other(self.manga_item, events_bulk)
        self.assertEqual(len(events_bulk), 1)
        self.assertEqual(events_bulk[0].item, self.manga_item)
        self.assertIsNone(events_bulk[0].content_number)
        self.assertEqual(
            events_bulk[0].datetime,
            datetime.datetime.min.replace(tzinfo=ZoneInfo("UTC")),
        )

    @patch("events.calendar_processors.services.get_media_metadata")
    def test_process_other_manga_completed_no_chapters(self, mock_metadata):
        mock_metadata.return_value = {
            "details": {"end_date": "2023-12-22"},
            "max_progress": None,
        }
        events_bulk = []
        process_other(self.manga_item, events_bulk)
        self.assertEqual(len(events_bulk), 1)
        self.assertEqual(events_bulk[0].item, self.manga_item)
        self.assertIsNone(events_bulk[0].content_number)
        self.assertEqual(events_bulk[0].datetime, date_parser("2023-12-22"))

    @patch("events.calendar_processors.services.get_media_metadata")
    def test_process_other_invalid_date(self, mock_metadata):
        mock_metadata.return_value = {
            "max_progress": None,
            "details": {"release_date": "invalid-date"},
        }
        events_bulk = []
        process_other(self.movie_item, events_bulk)
        self.assertEqual(len(events_bulk), 0)

    @patch("events.calendar_processors.services.get_media_metadata")
    def test_process_other_no_date(self, mock_metadata):
        mock_metadata.return_value = {
            "max_progress": None,
            "details": {},
        }
        events_bulk = []
        process_other(self.movie_item, events_bulk)
        self.assertEqual(len(events_bulk), 0)

    @patch("app.providers.tmdb.movie")
    def test_process_other_provider_api_error(self, mock_tmdb_movie):
        response_mock = MagicMock()
        response_mock.status_code = 404
        response_mock.text = "Not found"
        mock_tmdb_movie.side_effect = services.ProviderAPIError(
            provider=Sources.TMDB.value,
            error=response_mock,
            details="Movie not found",
        )
        events_bulk = []
        process_other(self.movie_item, events_bulk)
        self.assertEqual(len(events_bulk), 0)

    # --- Comic processing ---

    @patch("events.calendar_processors.services.get_media_metadata")
    @patch("events.calendar_processors.comicvine.issue")
    def test_process_comic_with_store_date(self, mock_issue, mock_metadata):
        comic_item = Item.objects.create(
            media_id="4050-18166", source=Sources.COMICVINE.value,
            media_type=MediaTypes.COMIC.value, title="Batman", image=IMG,
        )
        mock_metadata.return_value = {
            "max_issue_number": 10,
            "last_issue_id": "4000-123456",
            "last_issue": {"issue_number": "10"},
        }
        mock_issue.return_value = {
            "store_date": "2023-04-15",
            "cover_date": "2023-05-01",
        }

        events_bulk = []
        process_comic(comic_item, events_bulk)
        self.assertEqual(len(events_bulk), 1)
        self.assertEqual(events_bulk[0].item, comic_item)
        self.assertEqual(events_bulk[0].content_number, 10)
        self.assertEqual(events_bulk[0].datetime, date_parser("2023-04-15"))
        mock_issue.assert_called_once_with("4000-123456")

    @patch("events.calendar_processors.services.get_media_metadata")
    @patch("events.calendar_processors.comicvine.issue")
    def test_process_comic_with_cover_date_only(self, mock_issue, mock_metadata):
        comic_item = Item.objects.create(
            media_id="4050-18167", source=Sources.COMICVINE.value,
            media_type=MediaTypes.COMIC.value, title="Superman", image=IMG,
        )
        mock_metadata.return_value = {
            "max_issue_number": 5,
            "last_issue_id": "4000-123457",
            "last_issue": {"issue_number": "5"},
        }
        mock_issue.return_value = {"store_date": None, "cover_date": "2023-05-01"}

        events_bulk = []
        process_comic(comic_item, events_bulk)
        self.assertEqual(len(events_bulk), 1)
        self.assertEqual(events_bulk[0].item, comic_item)
        self.assertEqual(events_bulk[0].content_number, 5)
        self.assertEqual(events_bulk[0].datetime, date_parser("2023-05-01"))

    @patch("events.calendar_processors.services.get_media_metadata")
    @patch("events.calendar_processors.comicvine.issue")
    def test_process_comic_no_dates(self, mock_issue, mock_metadata):
        comic_item = Item.objects.create(
            media_id="4050-18168", source=Sources.COMICVINE.value,
            media_type=MediaTypes.COMIC.value, title="Wonder Woman", image=IMG,
        )
        mock_metadata.return_value = {
            "max_issue_number": 3,
            "last_issue_id": "4000-123458",
            "last_issue": {"issue_number": "3"},
        }
        mock_issue.return_value = {"store_date": None, "cover_date": None}

        events_bulk = []
        process_comic(comic_item, events_bulk)
        self.assertEqual(len(events_bulk), 0)

    @patch("events.calendar_processors.services.get_media_metadata")
    def test_process_comic_provider_api_error(self, mock_metadata):
        comic_item = Item.objects.create(
            media_id="99999", source=Sources.COMICVINE.value,
            media_type=MediaTypes.COMIC.value, title="Test Comic", image=IMG,
        )
        Comic.objects.create(
            item=comic_item, user=self.user, status=Status.PLANNING.value,
        )
        response_mock = MagicMock()
        response_mock.status_code = 500
        response_mock.text = "Server error"
        mock_metadata.side_effect = services.ProviderAPIError(
            provider=Sources.COMICVINE.value,
            error=response_mock,
            details="API error",
        )

        events_bulk = []
        process_comic(comic_item, events_bulk)
        self.assertEqual(len(events_bulk), 0)
