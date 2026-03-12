import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from app.models import (
    TV,
    Anime,
    Item,
    Manga,
    MediaTypes,
    Movie,
    Season,
    Sources,
    Status,
)
from events.models import Event


class EventModelTests(TestCase):
    """Test the Event model."""

    @classmethod
    def _create_test_items(cls):
        cls.season_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test TV Show",
            season_number=1,
        )
        cls.movie_item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
        )
        cls.anime_item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Test Anime",
        )
        cls.manga_item = Item.objects.create(
            media_id="66296374554",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Test Manga",
        )

    @classmethod
    def _create_test_media(cls):
        cls.season = Season.objects.create(
            user=cls.user,
            item=cls.season_item,
            status=Status.IN_PROGRESS.value,
        )
        cls.movie = Movie.objects.create(
            user=cls.user,
            item=cls.movie_item,
            status=Status.PLANNING.value,
        )
        cls.anime = Anime.objects.create(
            user=cls.user,
            item=cls.anime_item,
            status=Status.IN_PROGRESS.value,
        )
        cls.manga = Manga.objects.create(
            user=cls.user,
            item=cls.manga_item,
            status=Status.IN_PROGRESS.value,
        )

    @classmethod
    def _create_test_events(cls):
        cls.now = timezone.now()
        cls.tomorrow = cls.now + datetime.timedelta(days=1)
        cls.next_week = cls.now + datetime.timedelta(days=7)

        cls.season_event = Event.objects.create(
            item=cls.season_item,
            content_number=1,
            datetime=cls.tomorrow,
        )
        cls.movie_event = Event.objects.create(
            item=cls.movie_item,
            datetime=cls.next_week,
        )
        cls.anime_event = Event.objects.create(
            item=cls.anime_item,
            content_number=1,
            datetime=cls.tomorrow,
        )
        cls.manga_event = Event.objects.create(
            item=cls.manga_item,
            content_number=1,
            datetime=cls.tomorrow,
        )

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = get_user_model().objects.create_user(
            username="testuser",
            password="testpassword",
        )
        cls._create_test_items()
        cls._create_test_media()
        cls._create_test_events()

    def test_event_string_representation(self):
        """Test the string representation of events."""
        # Season event
        self.assertEqual(
            str(self.season_event),
            "Test TV Show S1 E1",
        )

        # Movie event
        self.assertEqual(str(self.movie_event), "Test Movie")

        # Anime event
        self.assertEqual(str(self.anime_event), "Test Anime E1")

        # Manga event
        self.assertEqual(str(self.manga_event), "Test Manga #1")


class EventManagerTests(TestCase):
    """Test the EventManager custom manager."""

    @classmethod
    def _create_test_items(cls):
        cls.tv_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Test TV Show",
        )
        cls.season_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test TV Show",
            season_number=1,
        )
        cls.movie_item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
        )
        cls.paused_movie_item = Item.objects.create(
            media_id="278",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Paused Movie",
        )
        cls.dropped_movie_item = Item.objects.create(
            media_id="424",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Dropped Movie",
        )
        cls.manga_item = Item.objects.create(
            media_id="66296374554",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Test Manga",
        )

    @classmethod
    def _create_test_media(cls):
        cls.tv = TV.objects.create(
            user=cls.user,
            item=cls.tv_item,
            status=Status.IN_PROGRESS.value,
        )
        cls.other_tv = TV.objects.create(
            user=cls.other_user,
            item=cls.tv_item,
            status=Status.IN_PROGRESS.value,
        )
        cls.movie = Movie.objects.create(
            user=cls.user,
            item=cls.movie_item,
            status=Status.PLANNING.value,
        )
        cls.paused_movie = Movie.objects.create(
            user=cls.user,
            item=cls.paused_movie_item,
            status=Status.PAUSED.value,
        )
        cls.dropped_movie = Movie.objects.create(
            user=cls.user,
            item=cls.dropped_movie_item,
            status=Status.DROPPED.value,
        )
        cls.manga = Manga.objects.create(
            user=cls.user,
            item=cls.manga_item,
            status=Status.IN_PROGRESS.value,
        )

    @classmethod
    def _create_test_events(cls):
        cls.base_date = datetime.datetime(
            2025,
            4,
            15,
            12,
            0,
            0,
            tzinfo=datetime.UTC,
        )
        cls.yesterday = cls.base_date - datetime.timedelta(days=1)
        cls.tomorrow = cls.base_date + datetime.timedelta(days=1)
        cls.next_week = cls.base_date + datetime.timedelta(days=7)

        cls.past_event = Event.objects.create(
            item=cls.season_item,
            content_number=1,
            datetime=cls.yesterday,
        )
        cls.movie_event = Event.objects.create(
            item=cls.movie_item,
            datetime=cls.next_week,
        )
        cls.paused_movie_event = Event.objects.create(
            item=cls.paused_movie_item,
            datetime=cls.next_week,
        )
        cls.dropped_movie_event = Event.objects.create(
            item=cls.dropped_movie_item,
            datetime=cls.next_week,
        )
        cls.season_event = Event.objects.create(
            item=cls.season_item,
            content_number=2,
            datetime=cls.tomorrow,
        )
        cls.manga_event1 = Event.objects.create(
            item=cls.manga_item,
            content_number=1,
            datetime=cls.tomorrow,
        )
        cls.manga_event2 = Event.objects.create(
            item=cls.manga_item,
            content_number=2,
            datetime=cls.next_week,
        )

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = get_user_model().objects.create_user(
            username="testuser",
            password="testpassword",
        )
        cls.other_user = get_user_model().objects.create_user(
            username="otheruser",
            password="testpassword",
        )
        cls._create_test_items()
        cls._create_test_media()
        cls._create_test_events()

    def test_get_user_events(self):
        """Test the get_user_events method."""
        # Use fixed dates for testing
        today = self.base_date.date()  # April 15
        next_week = today + datetime.timedelta(days=7)  # April 22

        # Get events for the user
        events = Event.objects.get_user_events(self.user, today, next_week)

        # Should include season and manga events (movie is Planning, so hidden)
        self.assertEqual(events.count(), 3)
        self.assertIn(self.season_event, events)
        self.assertIn(self.manga_event1, events)
        self.assertNotIn(self.movie_event, events)
        self.assertIn(self.manga_event2, events)
        self.assertNotIn(self.past_event, events)

        # Get events for the other user
        other_events = Event.objects.get_user_events(self.other_user, today, next_week)

        # Other user has TV as active, so get season events
        self.assertEqual(other_events.count(), 1)

        # Test with a different date range
        tomorrow = today + datetime.timedelta(days=1)  # April 16
        limited_events = Event.objects.get_user_events(self.user, today, tomorrow)

        self.assertEqual(limited_events.count(), 2)
        self.assertIn(self.season_event, limited_events)  # Season event in range
        self.assertIn(self.manga_event1, limited_events)  # Manga event in range
        self.assertNotIn(self.movie_event, limited_events)  # Outside range
        self.assertNotIn(
            self.past_event,
            limited_events,
        )  # Past event, but filtered by active status

    def test_get_user_events_no_duplicates_from_rewatches(self):
        """Test that rewatched media does not duplicate calendar events."""
        anime_item = Item.objects.create(
            media_id="437",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Rewatched Anime",
        )
        Anime.objects.create(
            user=self.user,
            item=anime_item,
            status=Status.COMPLETED.value,
        )
        Anime.objects.create(
            user=self.user,
            item=anime_item,
            status=Status.COMPLETED.value,
        )
        Anime.objects.create(
            user=self.user,
            item=anime_item,
            status=Status.IN_PROGRESS.value,
        )

        anime_event = Event.objects.create(
            item=anime_item,
            content_number=10,
            datetime=self.tomorrow,
        )

        today = self.base_date.date()
        next_week = today + datetime.timedelta(days=7)
        events = Event.objects.get_user_events(self.user, today, next_week)

        event_ids = [e.id for e in events]
        self.assertEqual(event_ids.count(anime_event.id), 1)
