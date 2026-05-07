from django.contrib.auth import get_user_model
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
from events.calendar import (
    auto_move_completed_to_planning,
    get_items_to_process,
    save_events,
)
from events.models import Event

IMG = "http://example.com/image.jpg"


class GetItemsToProcessTests(TestCase):
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
        Anime.objects.create(
            item=cls.anime_item,
            user=cls.user,
            status=Status.PLANNING.value,
        )
        cls.movie_item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Godfather",
            image=IMG,
        )
        Movie.objects.create(
            item=cls.movie_item,
            user=cls.user,
            status=Status.PLANNING.value,
        )
        cls.tv_item = Item.objects.create(
            media_id="1396",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Breaking Bad",
            image=IMG,
        )
        tv_object = TV.objects.create(
            item=cls.tv_item,
            user=cls.user,
            status=Status.PLANNING.value,
        )
        cls.season_item = Item.objects.create(
            media_id="1396",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Breaking Bad",
            image=IMG,
            season_number=1,
        )
        Season.objects.create(
            item=cls.season_item,
            related_tv=tv_object,
            user=cls.user,
            status=Status.PLANNING.value,
        )
        cls.manga_item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.MANGA.value,
            title="Berserk",
            image=IMG,
        )
        Manga.objects.create(
            item=cls.manga_item,
            user=cls.user,
            status=Status.PLANNING.value,
        )
        cls.book_item = Item.objects.create(
            media_id="OL21733390M",
            source=Sources.OPENLIBRARY.value,
            media_type=MediaTypes.BOOK.value,
            title="1984",
            image=IMG,
        )
        Book.objects.create(
            item=cls.book_item,
            user=cls.user,
            status=Status.PLANNING.value,
        )
        cls.comic_item = Item.objects.create(
            media_id="60760",
            source=Sources.COMICVINE.value,
            media_type=MediaTypes.COMIC.value,
            title="Batman",
            image=IMG,
        )
        Comic.objects.create(
            item=cls.comic_item,
            user=cls.user,
            status=Status.PLANNING.value,
        )

    def test_sentinel_only_items_are_included(self):
        """Items with only sentinel events get reprocessed (e.g. stuck in NYA)."""
        from datetime import datetime as _dt
        from zoneinfo import ZoneInfo

        sentinel = _dt.min.replace(tzinfo=ZoneInfo("UTC"))
        Event.objects.create(item=self.anime_item, datetime=sentinel)

        items = get_items_to_process(self.user)
        self.assertIn(self.anime_item, items)

    def test_filters_by_user_and_event_state(self):
        user2 = get_user_model().objects.create_user(
            username="test2",
            password="12345",
        )

        future_date = timezone.now() + timezone.timedelta(days=7)
        Event.objects.create(
            item=self.anime_item,
            content_number=1,
            datetime=future_date,
        )
        Event.objects.create(
            item=self.season_item,
            content_number=1,
            datetime=future_date,
        )

        past_date = timezone.now() - timezone.timedelta(days=30)
        Event.objects.create(
            item=self.manga_item,
            content_number=1,
            datetime=past_date,
        )

        old_past_date = timezone.now() - timezone.timedelta(days=400)
        Event.objects.create(
            item=self.book_item,
            content_number=1,
            datetime=old_past_date,
        )

        comic_recent_date = timezone.now() - timezone.timedelta(days=180)
        Event.objects.create(
            item=self.comic_item,
            content_number=1,
            datetime=comic_recent_date,
        )

        user2_item = Item.objects.create(
            media_id="888",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="User2 Anime",
            image=IMG,
        )
        Anime.objects.create(
            item=user2_item,
            user=user2,
            status=Status.IN_PROGRESS.value,
        )

        items = get_items_to_process(self.user)

        self.assertIn(self.anime_item, items)
        self.assertIn(self.tv_item, items)
        self.assertIn(self.comic_item, items)
        self.assertIn(self.movie_item, items)
        self.assertNotIn(user2_item, items)
        self.assertNotIn(self.manga_item, items)
        self.assertNotIn(self.book_item, items)

        all_items = get_items_to_process()
        self.assertIn(self.anime_item, all_items)
        self.assertIn(user2_item, all_items)


class AutoMoveCompletedToPlanningTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="test",
            password="12345",
        )
        cls.tv_item = Item.objects.create(
            media_id="500",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Test TV Show",
            image=IMG,
        )
        cls.tv = TV(
            item=cls.tv_item,
            user=cls.user,
            status=Status.COMPLETED.value,
        )
        TV.save_base(cls.tv)

        cls.season_item = Item.objects.create(
            media_id="500",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test TV Show",
            image=IMG,
            season_number=2,
        )

    def test_completed_tv_moves_to_planning_on_future_events(self):
        future_date = timezone.now() + timezone.timedelta(days=30)
        events_bulk = [
            Event(item=self.season_item, content_number=1, datetime=future_date),
        ]
        auto_move_completed_to_planning(events_bulk)
        self.tv.refresh_from_db()
        self.assertEqual(self.tv.status, Status.PLANNING.value)

    def test_in_progress_tv_not_affected(self):
        self.tv.status = Status.IN_PROGRESS.value
        self.tv.save()

        future_date = timezone.now() + timezone.timedelta(days=30)
        events_bulk = [
            Event(item=self.season_item, content_number=1, datetime=future_date),
        ]
        auto_move_completed_to_planning(events_bulk)
        self.tv.refresh_from_db()
        self.assertEqual(self.tv.status, Status.IN_PROGRESS.value)

    def test_no_move_without_future_events(self):
        past_date = timezone.now() - timezone.timedelta(days=30)
        events_bulk = [
            Event(item=self.season_item, content_number=1, datetime=past_date),
        ]
        auto_move_completed_to_planning(events_bulk)
        self.tv.refresh_from_db()
        self.assertEqual(self.tv.status, Status.COMPLETED.value)


class SaveEventsNoContentNumberTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="test_save",
            password="12345",
        )
        cls.movie_item = Item.objects.create(
            media_id="999",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image=IMG,
        )
        Movie.objects.create(
            item=cls.movie_item,
            user=cls.user,
            status=Status.PLANNING.value,
        )

    def test_creates_event_without_content_number(self):
        events_bulk = [
            Event(
                item=self.movie_item,
                content_number=None,
                datetime=timezone.now(),
            ),
        ]
        items_updated = save_events(events_bulk)
        self.assertIn(self.movie_item, items_updated)
        self.assertTrue(
            Event.objects.filter(
                item=self.movie_item, content_number__isnull=True
            ).exists()
        )

    def test_updates_existing_event_datetime(self):
        original_dt = timezone.now()
        Event.objects.create(
            item=self.movie_item,
            content_number=None,
            datetime=original_dt,
        )
        new_dt = original_dt + timezone.timedelta(days=7)
        save_events(
            [
                Event(item=self.movie_item, content_number=None, datetime=new_dt),
            ]
        )
        updated = Event.objects.get(item=self.movie_item, content_number__isnull=True)
        self.assertEqual(updated.datetime, new_dt)


class CalendarEdgeCaseTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="t",
            password="x",
        )

    def test_generate_final_message_no_updates(self):
        from events.calendar import generate_final_message

        item = Item.objects.create(
            media_id="1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="A",
            image=IMG,
        )
        msg = generate_final_message([item], items_updated=set())
        self.assertIn("No releases", msg)

    def test_cleanup_invalid_events_deletes_obsolete_content_numbers(self):
        from events.calendar import cleanup_invalid_events

        item = Item.objects.create(
            media_id="2",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="S",
            image=IMG,
            season_number=1,
        )
        Event.objects.create(item=item, content_number=1, datetime=timezone.now())
        Event.objects.create(item=item, content_number=2, datetime=timezone.now())
        events_bulk = [
            Event(item=item, content_number=1, datetime=timezone.now()),
        ]
        cleanup_invalid_events(events_bulk)
        remaining = Event.objects.filter(item=item).values_list(
            "content_number", flat=True
        )
        self.assertNotIn(2, remaining)

    def test_get_tv_items_to_include_empty_input(self):
        from events.calendar import get_tv_items_to_include

        empty_qs = Item.objects.filter(media_type=MediaTypes.TV.value, media_id="nope")
        result = get_tv_items_to_include(empty_qs, timezone.now(), timezone.now())
        self.assertEqual(result, [])

    def test_should_include_tv_all_sentinel(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from events.calendar import _should_include_tv

        sentinel = datetime.min.replace(tzinfo=ZoneInfo("UTC"))

        class _Ev:
            def __init__(self, dt):
                self.datetime = dt

        result = _should_include_tv(
            [_Ev(sentinel), _Ev(sentinel)], timezone.now(), sentinel
        )
        self.assertTrue(result)

    def test_should_include_tv_past_only(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo

        from events.calendar import _should_include_tv

        sentinel = datetime.min.replace(tzinfo=ZoneInfo("UTC"))
        past = timezone.now() - timezone.timedelta(days=400)

        class _Ev:
            def __init__(self, dt):
                self.datetime = dt

        result = _should_include_tv([_Ev(past)], timezone.now(), sentinel)
        self.assertFalse(result)


class CalendarDatesTests(TestCase):
    def test_year_only_string_parsed(self):
        from events._calendar_dates import date_parser

        result = date_parser("2025")
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 1)

    def test_year_month_string_parsed(self):
        from events._calendar_dates import date_parser

        result = date_parser("2025-06")
        self.assertEqual(result.year, 2025)
        self.assertEqual(result.month, 6)
        self.assertEqual(result.day, 1)

    def test_full_date_string(self):
        from events._calendar_dates import date_parser

        result = date_parser("2025-06-15")
        self.assertEqual(result.day, 15)
