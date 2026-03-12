import datetime
from unittest.mock import patch

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
