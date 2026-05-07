import datetime
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import (
    Anime,
    Book,
    Comic,
    Item,
    Manga,
    MediaTypes,
    Movie,
    Sources,
    Status,
)
from app.providers import services
from events.calendar_processors import (
    anilist_date_parser,
    date_parser,
    get_anime_schedule_bulk,
    process_anime_bulk,
    process_comic,
    process_other,
)

IMG = "http://example.com/image.jpg"


def _anilist_page(media_list, *, has_next=False):
    return {
        "data": {
            "Page": {
                "pageInfo": {"hasNextPage": has_next},
                "media": media_list,
            },
        },
    }


class CalendarMediaTests(TestCase):
    """Tests for anime, other media, and comic processing functions."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="media_test",
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
        cls.batman_comic = Item.objects.create(
            media_id="4050-18166",
            source=Sources.COMICVINE.value,
            media_type=MediaTypes.COMIC.value,
            title="Batman",
            image=IMG,
        )
        cls.superman_comic = Item.objects.create(
            media_id="4050-18167",
            source=Sources.COMICVINE.value,
            media_type=MediaTypes.COMIC.value,
            title="Superman",
            image=IMG,
        )
        cls.wonderwoman_comic = Item.objects.create(
            media_id="4050-18168",
            source=Sources.COMICVINE.value,
            media_type=MediaTypes.COMIC.value,
            title="Wonder Woman",
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

    @patch("events.calendar_processors.services.get_media_metadata")
    @patch("events.calendar_processors.services.api_request")
    def test_process_anime_bulk(self, mock_api, mock_metadata):
        """Test with AniList match and fallback to metadata."""
        mock_api.return_value = _anilist_page(
            [
                {
                    "idMal": 437,
                    "endDate": {"year": 1997, "month": 8, "day": 5},
                    "episodes": 1,
                    "airingSchedule": {
                        "nodes": [{"episode": 1, "airingAt": 870739200}]
                    },
                }
            ]
        )
        events_bulk = []
        process_anime_bulk([self.anime_item], events_bulk)
        self.assertEqual(len(events_bulk), 1)
        self.assertEqual(events_bulk[0].item, self.anime_item)
        self.assertEqual(events_bulk[0].content_number, 1)
        expected = datetime.datetime.fromtimestamp(870739200, tz=ZoneInfo("UTC"))
        self.assertEqual(events_bulk[0].datetime, expected)

        mock_api.return_value = _anilist_page([])
        mock_metadata.return_value = {
            "max_progress": 1,
            "details": {"end_date": "1997-08-05"},
        }
        events_bulk = []
        process_anime_bulk([self.anime_item], events_bulk)
        self.assertEqual(len(events_bulk), 1)

    @patch("events.calendar_processors.services.get_media_metadata")
    @patch("events.calendar_processors.services.api_request")
    def test_anime_schedule_bulk(self, mock_api, mock_metadata):
        """Test airing schedule, no-airing fallback, and episode filtering."""
        mock_api.return_value = _anilist_page(
            [
                {
                    "idMal": 437,
                    "startDate": {"year": 1997, "month": 8, "day": 5},
                    "endDate": {"year": 1997, "month": 8, "day": 5},
                    "episodes": 1,
                    "airingSchedule": {
                        "nodes": [{"episode": 1, "airingAt": 870739200}]
                    },
                }
            ]
        )
        result = get_anime_schedule_bulk(["437"])
        self.assertIn("437", result)
        self.assertEqual(len(result["437"]), 1)
        self.assertEqual(result["437"][0]["episode"], 1)
        self.assertEqual(result["437"][0]["airingAt"], 870739200)

        mock_api.return_value = _anilist_page(
            [
                {
                    "idMal": 437,
                    "endDate": {"year": 1997, "month": 8, "day": 12},
                    "episodes": 2,
                    "airingSchedule": {"nodes": []},
                }
            ]
        )
        mock_metadata.return_value = {
            "max_progress": 2,
            "details": {"end_date": "1997-08-12"},
        }
        result = get_anime_schedule_bulk(["437"])
        self.assertIn("437", result)
        self.assertEqual(len(result["437"]), 1)
        dt = datetime.datetime.fromtimestamp(
            result["437"][0]["airingAt"],
            tz=ZoneInfo("UTC"),
        )
        self.assertEqual((dt.year, dt.month, dt.day), (1997, 8, 12))

        mock_api.return_value = _anilist_page(
            [
                {
                    "idMal": 437,
                    "endDate": {"year": 1997, "month": 8, "day": 5},
                    "episodes": 1,
                    "airingSchedule": {
                        "nodes": [
                            {"episode": 1, "airingAt": 870739200},
                            {"episode": 2, "airingAt": 870825600},
                        ],
                    },
                }
            ]
        )
        result = get_anime_schedule_bulk(["437"])
        self.assertEqual(len(result["437"]), 1)
        self.assertEqual(result["437"][0]["episode"], 1)

    def test_anilist_date_parser(self):
        """Test complete, partial, and missing year dates."""
        cases = [
            ({"year": 2024, "month": 3, "day": 28}, (2024, 3, 28)),
            ({"year": 2024, "month": 3, "day": None}, (2024, 3, 1)),
            ({"year": 2024, "month": None, "day": None}, (2024, 1, 1)),
        ]
        for date_input, expected_ymd in cases:
            with self.subTest(date_input=date_input):
                result = anilist_date_parser(date_input)
                dt = datetime.datetime.fromtimestamp(result, tz=ZoneInfo("UTC"))
                self.assertEqual(
                    (dt.year, dt.month, dt.day),
                    expected_ymd,
                )

        self.assertIsNone(
            anilist_date_parser({"year": None, "month": 3, "day": 28}),
        )

    def test_process_other(self):
        """Test process_other across media types, edge cases, and errors."""
        sentinel_dt = datetime.datetime.min.replace(tzinfo=ZoneInfo("UTC"))
        cases = [
            (
                self.movie_item,
                {"max_progress": 1, "details": {"release_date": "1999-10-15"}},
                1,
                None,
                date_parser("1999-10-15"),
            ),
            (
                self.book_item,
                {"max_progress": 328, "details": {"publish_date": "1949-06-08"}},
                1,
                328,
                date_parser("1949-06-08"),
            ),
            (
                self.manga_item,
                {"max_progress": 375, "details": {"end_date": "2023-12-22"}},
                1,
                375,
                date_parser("2023-12-22"),
            ),
            (
                self.manga_item,
                {"details": {"end_date": None}, "max_progress": None},
                1,
                None,
                sentinel_dt,
            ),
            (
                self.manga_item,
                {"details": {"end_date": "2023-12-22"}, "max_progress": None},
                1,
                None,
                date_parser("2023-12-22"),
            ),
            (
                self.movie_item,
                {"max_progress": None, "details": {"release_date": "invalid-date"}},
                0,
                None,
                None,
            ),
            (self.movie_item, {"max_progress": None, "details": {}}, 0, None, None),
        ]
        for item, metadata, count, number, dt in cases:
            with (
                self.subTest(item=item.title, details=metadata.get("details")),
                patch(
                    "events.calendar_processors.services.get_media_metadata",
                    return_value=metadata,
                ),
            ):
                events_bulk = []
                process_other(item, events_bulk)
                self.assertEqual(len(events_bulk), count)
                if count:
                    self.assertEqual(events_bulk[0].item, item)
                    self.assertEqual(events_bulk[0].content_number, number)
                    if dt is not None:
                        self.assertEqual(events_bulk[0].datetime, dt)

    @patch("app.providers.tmdb.movie")
    def test_process_other_provider_error(self, mock_tmdb_movie):
        """Test process_other handles ProviderAPIError gracefully."""
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

    def test_process_comic(self):
        """Test comic processing with store date, cover date, and no dates."""
        base_meta = {
            "max_issue_number": 10,
            "last_issue_id": "4000-123456",
            "last_issue": {"issue_number": "10"},
        }
        cases = [
            (
                self.batman_comic,
                base_meta,
                {"store_date": "2023-04-15", "cover_date": "2023-05-01"},
                1,
                10,
                date_parser("2023-04-15"),
            ),
            (
                self.superman_comic,
                {
                    **base_meta,
                    "max_issue_number": 5,
                    "last_issue": {"issue_number": "5"},
                },
                {"store_date": None, "cover_date": "2023-05-01"},
                1,
                5,
                date_parser("2023-05-01"),
            ),
            (
                self.wonderwoman_comic,
                {
                    **base_meta,
                    "max_issue_number": 3,
                    "last_issue": {"issue_number": "3"},
                },
                {"store_date": None, "cover_date": None},
                0,
                None,
                None,
            ),
        ]
        for comic_item, meta, issue_data, count, number, dt in cases:
            with (
                self.subTest(title=comic_item.title),
                patch(
                    "events.calendar_processors.services.get_media_metadata",
                    return_value=meta,
                ),
                patch(
                    "events.calendar_processors.comicvine.issue",
                    return_value=issue_data,
                ),
            ):
                events_bulk = []
                process_comic(comic_item, events_bulk)
                self.assertEqual(len(events_bulk), count)
                if count:
                    self.assertEqual(events_bulk[0].item, comic_item)
                    self.assertEqual(events_bulk[0].content_number, number)
                    if dt is not None:
                        self.assertEqual(events_bulk[0].datetime, dt)

    @patch("events.calendar_processors.services.get_media_metadata")
    def test_process_comic_provider_error(self, mock_metadata):
        """Test process_comic handles ProviderAPIError gracefully."""
        response_mock = MagicMock()
        response_mock.status_code = 500
        response_mock.text = "Server error"
        mock_metadata.side_effect = services.ProviderAPIError(
            provider=Sources.COMICVINE.value,
            error=response_mock,
            details="API error",
        )
        events_bulk = []
        process_comic(self.comic_item, events_bulk)
        self.assertEqual(len(events_bulk), 0)

    def test_process_anime_bulk_empty(self):
        """Test process_anime_bulk with empty items list returns early."""
        events_bulk = []
        process_anime_bulk([], events_bulk)
        self.assertEqual(len(events_bulk), 0)

    @patch("events.calendar_processors.comicvine.issue")
    @patch("events.calendar_processors.services.get_media_metadata")
    def test_process_comic_issue_fetch_error(self, mock_metadata, mock_issue):
        """Test process_comic handles issue fetch ProviderAPIError."""
        mock_metadata.return_value = {
            "max_issue_number": 10,
            "last_issue_id": "4000-123456",
            "last_issue": {"issue_number": "10"},
        }
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.text = "Server error"
        mock_issue.side_effect = services.ProviderAPIError(
            provider=Sources.COMICVINE.value,
            error=error_response,
            details="Issue fetch error",
        )
        events_bulk = []
        process_comic(self.batman_comic, events_bulk)
        self.assertEqual(len(events_bulk), 0)

    @patch("events.calendar_processors.services.get_media_metadata")
    def test_process_other_mangaupdates_sentinel(self, mock_metadata):
        """Test MangaUpdates item gets sentinel datetime when no date key."""
        mangaupdates_item = Item.objects.create(
            media_id="100",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="MU Manga",
            image=IMG,
        )
        mock_metadata.return_value = {
            "max_progress": 50,
            "details": {},
        }
        events_bulk = []
        process_other(mangaupdates_item, events_bulk)
        self.assertEqual(len(events_bulk), 1)
        self.assertEqual(events_bulk[0].content_number, 50)

    @patch("events.calendar_processors.services.get_media_metadata")
    def test_process_other_skips_sentinel_when_currently_airing(
        self,
        mock_metadata,
    ):
        """Currently-airing anime with empty end_date does not get a sentinel event."""
        mock_metadata.return_value = {
            "max_progress": 12,
            "details": {"end_date": None, "status": "Airing"},
        }
        events_bulk = []
        process_other(self.anime_item, events_bulk)
        self.assertEqual(events_bulk, [])

    @patch("events.calendar_processors.services.get_media_metadata")
    def test_process_other_clears_existing_sentinel_when_airing(
        self,
        mock_metadata,
    ):
        """Existing sentinel event is removed when status flips to Airing."""
        from events.calendar import SENTINEL_DATETIME
        from events.models import Event

        Event.objects.create(item=self.anime_item, datetime=SENTINEL_DATETIME)
        mock_metadata.return_value = {
            "max_progress": 12,
            "details": {"end_date": None, "status": "Airing"},
        }
        events_bulk = []
        process_other(self.anime_item, events_bulk)
        self.assertEqual(events_bulk, [])
        self.assertFalse(
            Event.objects.filter(
                item=self.anime_item,
                datetime=SENTINEL_DATETIME,
            ).exists(),
        )

    @patch("events.calendar_processors.services.get_media_metadata")
    def test_process_other_keeps_sentinel_when_upcoming(self, mock_metadata):
        """Upcoming anime with empty end_date still gets a sentinel event."""
        from events.calendar import SENTINEL_DATETIME

        mock_metadata.return_value = {
            "max_progress": 12,
            "details": {"end_date": None, "status": "Upcoming"},
        }
        events_bulk = []
        process_other(self.anime_item, events_bulk)
        self.assertEqual(len(events_bulk), 1)
        self.assertEqual(events_bulk[0].datetime, SENTINEL_DATETIME)

    @patch("events.calendar_processors.services.get_media_metadata")
    def test_process_other_clears_sentinel_when_publishing(self, mock_metadata):
        """Currently-publishing manga clears existing sentinel event."""
        from events.calendar import SENTINEL_DATETIME
        from events.models import Event

        Event.objects.create(item=self.manga_item, datetime=SENTINEL_DATETIME)
        mock_metadata.return_value = {
            "max_progress": 100,
            "details": {"end_date": None, "status": "Publishing"},
        }
        events_bulk = []
        process_other(self.manga_item, events_bulk)
        self.assertEqual(events_bulk, [])
        self.assertFalse(
            Event.objects.filter(
                item=self.manga_item,
                datetime=SENTINEL_DATETIME,
            ).exists(),
        )

    @patch("events.calendar_processors.services.get_media_metadata")
    @patch("events.calendar_processors.services.api_request")
    def test_anime_mal_more_episodes_skips(self, mock_api, mock_metadata):
        """Test anime skipped when MAL has more episodes than AniList."""
        mock_api.return_value = _anilist_page(
            [
                {
                    "idMal": 437,
                    "endDate": {"year": 1997, "month": 8, "day": 5},
                    "episodes": 1,
                    "airingSchedule": {"nodes": []},
                },
            ],
        )
        mock_metadata.return_value = {
            "max_progress": 5,
            "details": {"end_date": "1997-08-05"},
        }
        events_bulk = []
        process_anime_bulk([self.anime_item], events_bulk)
        self.assertEqual(len(events_bulk), 1)
