from datetime import UTC, timedelta

from django.contrib.auth import get_user_model
from django.db import models
from django.test import TestCase, override_settings
from django.utils import timezone

from app.models import TV, Anime, Item, Manga, MediaTypes, Season, Sources, Status
from events.models import Event, SentinelDatetime
from events.notifications import (
    check_user_season_tracking,
    format_notification,
    get_all_user_tracking_data,
    get_tv_tracking_data,
    get_user_releases,
    is_user_tracking_item,
)


def _create_base_users():
    User = get_user_model()
    user1 = User.objects.create_user(
        username="user1",
        password="12345",
        notification_urls="https://example.com/notify1",
    )
    user2 = User.objects.create_user(
        username="user2",
        password="12345",
        notification_urls="https://example.com/notify2",
    )
    user3 = User.objects.create_user(
        username="user3",
        password="12345",
    )
    return user1, user2, user3


def _create_base_items():
    anime_item = Item.objects.create(
        media_id="1",
        source=Sources.MAL.value,
        media_type=MediaTypes.ANIME.value,
        title="Test Anime",
        image="http://example.com/anime.jpg",
    )
    manga_item = Item.objects.create(
        media_id="2",
        source=Sources.MAL.value,
        media_type=MediaTypes.MANGA.value,
        title="Test Manga",
        image="http://example.com/manga.jpg",
    )
    tv_show_item = Item.objects.create(
        media_id="1668",
        source=Sources.TMDB.value,
        media_type=MediaTypes.TV.value,
        title="Test TV Show",
        image="http://example.com/tv.jpg",
    )
    season1_item = Item.objects.create(
        media_id="1668",
        source=Sources.TMDB.value,
        media_type=MediaTypes.SEASON.value,
        title="Test TV Show - Season 1",
        season_number=1,
        image="http://example.com/tv.jpg",
    )
    season2_item = Item.objects.create(
        media_id="1668",
        source=Sources.TMDB.value,
        media_type=MediaTypes.SEASON.value,
        title="Test TV Show - Season 2",
        season_number=2,
        image="http://example.com/tv.jpg",
    )
    season3_item = Item.objects.create(
        media_id="1668",
        source=Sources.TMDB.value,
        media_type=MediaTypes.SEASON.value,
        title="Test TV Show - Season 3",
        season_number=3,
        image="http://example.com/tv.jpg",
    )
    return (
        anime_item,
        manga_item,
        tv_show_item,
        season1_item,
        season2_item,
        season3_item,
    )


def _create_recent_events(anime_item, manga_item, s1_item, s2_item, s3_item):
    ten_mins_ago = timezone.now() - timedelta(minutes=10)
    anime_event = Event.objects.create(
        item=anime_item,
        content_number=5,
        datetime=ten_mins_ago,
        notification_sent=False,
    )
    manga_event = Event.objects.create(
        item=manga_item,
        content_number=10,
        datetime=ten_mins_ago,
        notification_sent=False,
    )
    s1_event = Event.objects.create(
        item=s1_item,
        content_number=5,
        datetime=ten_mins_ago,
        notification_sent=False,
    )
    s2_event = Event.objects.create(
        item=s2_item,
        content_number=3,
        datetime=ten_mins_ago,
        notification_sent=False,
    )
    s3_event = Event.objects.create(
        item=s3_item,
        content_number=1,
        datetime=ten_mins_ago,
        notification_sent=False,
    )
    return anime_event, manga_event, s1_event, s2_event, s3_event


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TVTrackingTests(TestCase):
    """Tests for TV show and season tracking logic."""

    @classmethod
    def setUpTestData(cls):
        cls.user1, cls.user2, _ = _create_base_users()
        (
            cls.anime_item,
            cls.manga_item,
            cls.tv_show_item,
            cls.season1_item,
            cls.season2_item,
            cls.season3_item,
        ) = _create_base_items()

        TV.objects.create(
            item=cls.tv_show_item,
            user=cls.user1,
            status=Status.IN_PROGRESS.value,
        )
        user2_tv = TV.objects.create(
            item=cls.tv_show_item,
            user=cls.user2,
            status=Status.IN_PROGRESS.value,
        )
        Season.objects.bulk_create(
            [
                Season(
                    item=cls.season2_item,
                    related_tv=user2_tv,
                    user=cls.user2,
                    status=Status.DROPPED.value,
                ),
            ]
        )

    def test_get_tv_tracking_data(self):
        """Test the get_tv_tracking_data function."""
        users = [self.user1, self.user2]
        season_items = [self.season1_item, self.season2_item, self.season3_item]
        user_exclusions = {self.user1.id: set(), self.user2.id: set()}

        tracking_data = get_tv_tracking_data(users, season_items, user_exclusions)

        self.assertIsInstance(tracking_data, dict)

        self.assertTrue(tracking_data[(self.user1.id, self.season1_item.id)])
        self.assertTrue(tracking_data[(self.user1.id, self.season2_item.id)])
        self.assertTrue(tracking_data[(self.user1.id, self.season3_item.id)])

        self.assertTrue(tracking_data[(self.user2.id, self.season1_item.id)])
        self.assertFalse(tracking_data[(self.user2.id, self.season2_item.id)])
        self.assertFalse(tracking_data[(self.user2.id, self.season3_item.id)])

    def test_get_tv_tracking_data_with_inactive_tv_show(self):
        """Test get_tv_tracking_data when TV show is inactive."""
        user4 = get_user_model().objects.create_user(
            username="user4",
            password="12345",
        )
        tv_item = Item.objects.create(
            media_id="1396",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Dropped TV Show",
            image="http://example.com/tv2.jpg",
        )
        season_item = Item.objects.create(
            media_id="1396",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Dropped TV Show - Season 1",
            season_number=1,
            image="http://example.com/tv2.jpg",
        )
        TV.objects.create(
            item=tv_item,
            user=user4,
            status=Status.DROPPED.value,
        )

        tracking_data = get_tv_tracking_data(
            [user4],
            [season_item],
            {user4.id: set()},
        )
        self.assertNotIn((user4.id, season_item.id), tracking_data)

    def test_get_tv_tracking_data_with_excluded_items(self):
        """Test get_tv_tracking_data with excluded items."""
        user_exclusions = {self.user1.id: {self.tv_show_item.id}}

        tracking_data = get_tv_tracking_data(
            [self.user1],
            [self.season1_item],
            user_exclusions,
        )
        self.assertNotIn((self.user1.id, self.season1_item.id), tracking_data)

    def test_get_tv_tracking_data_empty_season_items(self):
        """Test get_tv_tracking_data with empty season items."""
        user_exclusions = {self.user1.id: set(), self.user2.id: set()}

        tracking_data = get_tv_tracking_data(
            [self.user1, self.user2],
            [],
            user_exclusions,
        )
        self.assertEqual(tracking_data, {})

    def test_check_user_season_tracking_active_tv(self):
        """Test check_user_season_tracking with an active TV show."""
        tv_show = TV.objects.get(item=self.tv_show_item, user=self.user1)
        tv_lookup = {(self.user1.id, self.tv_show_item.media_id): tv_show}

        result = check_user_season_tracking(
            self.user1.id,
            self.season1_item,
            tv_lookup,
            {},
        )
        self.assertTrue(result)

    def test_check_user_season_tracking_no_tv_show(self):
        """Test check_user_season_tracking when user has no TV show."""
        result = check_user_season_tracking(
            self.user1.id,
            self.season1_item,
            {},
            {},
        )
        self.assertIsNone(result)

    def test_check_user_season_tracking_dropped_tv(self):
        """Test check_user_season_tracking with a dropped TV show."""
        tv_show = TV.objects.get(item=self.tv_show_item, user=self.user1)
        tv_show.status = Status.DROPPED.value
        tv_show.save()

        tv_lookup = {(self.user1.id, self.tv_show_item.media_id): tv_show}

        result = check_user_season_tracking(
            self.user1.id,
            self.season1_item,
            tv_lookup,
            {},
        )
        self.assertIsNone(result)

    def test_check_user_season_tracking_dropped_earlier_season(self):
        """Test that dropping season 2 blocks season 2+ but not season 1."""
        tv_show = TV.objects.get(item=self.tv_show_item, user=self.user2)
        tv_lookup = {(self.user2.id, self.tv_show_item.media_id): tv_show}

        dropped_season = Season.objects.get(
            item=self.season2_item,
            user=self.user2,
        )
        season_lookup = {
            (self.user2.id, self.tv_show_item.media_id): [dropped_season],
        }

        result = check_user_season_tracking(
            self.user2.id,
            self.season1_item,
            tv_lookup,
            season_lookup,
        )
        self.assertTrue(result)

        result = check_user_season_tracking(
            self.user2.id,
            self.season2_item,
            tv_lookup,
            season_lookup,
        )
        self.assertFalse(result)

        result = check_user_season_tracking(
            self.user2.id,
            self.season3_item,
            tv_lookup,
            season_lookup,
        )
        self.assertFalse(result)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class UserReleaseTrackingTests(TestCase):
    """Tests for user release collection and item tracking status."""

    @classmethod
    def setUpTestData(cls):
        cls.user1, cls.user2, cls.user3 = _create_base_users()
        (
            cls.anime_item,
            cls.manga_item,
            cls.tv_show_item,
            cls.season1_item,
            cls.season2_item,
            cls.season3_item,
        ) = _create_base_items()

        Anime.objects.create(
            item=cls.anime_item,
            user=cls.user1,
            status=Status.IN_PROGRESS.value,
        )
        Anime.objects.create(
            item=cls.anime_item,
            user=cls.user2,
            status=Status.IN_PROGRESS.value,
        )
        Anime.objects.create(
            item=cls.anime_item,
            user=cls.user3,
            status=Status.IN_PROGRESS.value,
        )
        Manga.objects.create(
            item=cls.manga_item,
            user=cls.user1,
            status=Status.IN_PROGRESS.value,
        )
        Manga.objects.create(
            item=cls.manga_item,
            user=cls.user2,
            status=Status.PAUSED.value,
        )
        TV.objects.create(
            item=cls.tv_show_item,
            user=cls.user1,
            status=Status.IN_PROGRESS.value,
        )
        user2_tv = TV.objects.create(
            item=cls.tv_show_item,
            user=cls.user2,
            status=Status.IN_PROGRESS.value,
        )
        Season.objects.bulk_create(
            [
                Season(
                    item=cls.season2_item,
                    related_tv=user2_tv,
                    user=cls.user2,
                    status=Status.DROPPED.value,
                ),
            ]
        )

        (
            cls.anime_event,
            cls.manga_event,
            cls.season1_event,
            cls.season2_event,
            cls.season3_event,
        ) = _create_recent_events(
            cls.anime_item,
            cls.manga_item,
            cls.season1_item,
            cls.season2_item,
            cls.season3_item,
        )

        cls.user1.notification_excluded_items.add(cls.manga_item)

    def test_get_all_user_tracking_data(self):
        """Test the get_all_user_tracking_data function."""
        users_with_notifications = (
            get_user_model()
            .objects.filter(~models.Q(notification_urls=""))
            .prefetch_related("notification_excluded_items")
        )

        target_events = {
            (
                self.anime_event.item.id,
                self.anime_event.content_number,
            ): self.anime_event,
            (
                self.manga_event.item.id,
                self.manga_event.content_number,
            ): self.manga_event,
            (
                self.season1_event.item.id,
                self.season1_event.content_number,
            ): self.season1_event,
            (
                self.season2_event.item.id,
                self.season2_event.content_number,
            ): self.season2_event,
        }

        user_exclusions = {}
        for user in users_with_notifications:
            user_exclusions[user.id] = set(
                user.notification_excluded_items.values_list("id", flat=True),
            )

        tracking_data = get_all_user_tracking_data(
            users_with_notifications,
            target_events,
            user_exclusions,
        )

        self.assertIsInstance(tracking_data, dict)
        self.assertIn((self.user1.id, self.anime_item.id), tracking_data)
        self.assertIn((self.user1.id, self.manga_item.id), tracking_data)
        self.assertIn((self.user1.id, self.season1_item.id), tracking_data)

    def test_get_user_releases(self):
        """Test the get_user_releases function."""
        users_with_notifications = (
            get_user_model()
            .objects.filter(~models.Q(notification_urls=""))
            .prefetch_related("notification_excluded_items")
        )

        target_events = {
            (
                self.anime_event.item.id,
                self.anime_event.content_number,
            ): self.anime_event,
            (
                self.manga_event.item.id,
                self.manga_event.content_number,
            ): self.manga_event,
            (
                self.season1_event.item.id,
                self.season1_event.content_number,
            ): self.season1_event,
            (
                self.season2_event.item.id,
                self.season2_event.content_number,
            ): self.season2_event,
        }

        user_releases = get_user_releases(users_with_notifications, target_events)

        self.assertIn(self.user1.id, user_releases)
        self.assertIn(self.user2.id, user_releases)

        user1_events = user_releases[self.user1.id]
        self.assertTrue(any(e.id == self.anime_event.id for e in user1_events))
        self.assertFalse(any(e.id == self.manga_event.id for e in user1_events))
        self.assertTrue(any(e.id == self.season1_event.id for e in user1_events))

        user2_events = user_releases[self.user2.id]
        self.assertTrue(any(e.id == self.anime_event.id for e in user2_events))
        self.assertFalse(any(e.id == self.manga_event.id for e in user2_events))
        self.assertTrue(any(e.id == self.season1_event.id for e in user2_events))
        self.assertFalse(any(e.id == self.season2_event.id for e in user2_events))

    def test_is_user_tracking_item(self):
        """Test the is_user_tracking_item function."""
        target_events = {
            (
                self.anime_event.item.id,
                self.anime_event.content_number,
            ): self.anime_event,
            (
                self.manga_event.item.id,
                self.manga_event.content_number,
            ): self.manga_event,
            (
                self.season1_event.item.id,
                self.season1_event.content_number,
            ): self.season1_event,
        }
        user_exclusions = {self.user1.id: set(), self.user2.id: set()}

        tracking_data = get_all_user_tracking_data(
            [self.user1, self.user2],
            target_events,
            user_exclusions,
        )

        self.assertTrue(
            is_user_tracking_item(self.user1, self.anime_item, tracking_data)
        )
        self.assertTrue(
            is_user_tracking_item(self.user1, self.manga_item, tracking_data)
        )
        self.assertTrue(
            is_user_tracking_item(self.user2, self.anime_item, tracking_data)
        )
        self.assertFalse(
            is_user_tracking_item(self.user2, self.manga_item, tracking_data)
        )
        self.assertTrue(
            is_user_tracking_item(self.user1, self.season1_item, tracking_data)
        )

    def test_user_exclusion(self):
        """Test that user exclusions are respected."""
        users_with_notifications = (
            get_user_model()
            .objects.filter(~models.Q(notification_urls=""))
            .prefetch_related("notification_excluded_items")
        )

        target_events = {
            (
                self.anime_event.item.id,
                self.anime_event.content_number,
            ): self.anime_event,
            (
                self.manga_event.item.id,
                self.manga_event.content_number,
            ): self.manga_event,
        }

        user_releases = get_user_releases(users_with_notifications, target_events)

        user1_events = user_releases[self.user1.id]
        self.assertFalse(any(e.id == self.manga_event.id for e in user1_events))

    def test_is_user_tracking_item_dropped(self):
        """Test that dropped items are not considered actively tracked."""
        anime = Anime.objects.get(item=self.anime_item, user=self.user1)
        anime.status = Status.DROPPED.value
        anime.save()

        tracking_data = {(self.user1.id, self.anime_item.id): anime}
        self.assertFalse(
            is_user_tracking_item(self.user1, self.anime_item, tracking_data),
        )

    def test_is_user_tracking_item_completed(self):
        """Test that completed items are still considered actively tracked."""
        anime = Anime.objects.get(item=self.anime_item, user=self.user1)
        anime.status = Status.COMPLETED.value
        anime.save()

        tracking_data = {(self.user1.id, self.anime_item.id): anime}
        self.assertTrue(
            is_user_tracking_item(self.user1, self.anime_item, tracking_data),
        )

    def test_is_user_tracking_item_not_tracked(self):
        """Test that an untracked item returns False."""
        untracked_item = Item.objects.create(
            media_id="999",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Untracked Anime",
            image="http://example.com/untracked.jpg",
        )
        self.assertFalse(is_user_tracking_item(self.user1, untracked_item, {}))

    def test_get_user_releases_disabled_media_type(self):
        """Test that disabled media types are excluded from user releases."""
        self.user1.anime_enabled = False
        self.user1.save()

        users = (
            get_user_model()
            .objects.filter(id=self.user1.id)
            .prefetch_related("notification_excluded_items")
        )
        self.user1.notification_excluded_items.clear()

        target_events = {
            (
                self.anime_event.item.id,
                self.anime_event.content_number,
            ): self.anime_event,
            (
                self.manga_event.item.id,
                self.manga_event.content_number,
            ): self.manga_event,
        }

        user_releases = get_user_releases(users, target_events)

        if self.user1.id in user_releases:
            user1_events = user_releases[self.user1.id]
            self.assertFalse(any(e.id == self.anime_event.id for e in user1_events))
        self.assertTrue(
            any(
                e.id == self.manga_event.id
                for e in user_releases.get(self.user1.id, [])
            ),
        )


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class FormatNotificationTests(TestCase):
    """Tests for notification text formatting."""

    @classmethod
    def setUpTestData(cls):
        cls.anime_item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Test Anime",
            image="http://example.com/anime.jpg",
        )
        cls.manga_item = Item.objects.create(
            media_id="2",
            source=Sources.MAL.value,
            media_type=MediaTypes.MANGA.value,
            title="Test Manga",
            image="http://example.com/manga.jpg",
        )
        cls.season1_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test TV Show - Season 1",
            season_number=1,
            image="http://example.com/tv.jpg",
        )

        ten_mins_ago = timezone.now() - timedelta(minutes=10)
        cls.anime_event = Event.objects.create(
            item=cls.anime_item,
            content_number=5,
            datetime=ten_mins_ago,
            notification_sent=False,
        )
        cls.manga_event = Event.objects.create(
            item=cls.manga_item,
            content_number=10,
            datetime=ten_mins_ago,
            notification_sent=False,
        )
        cls.season1_event = Event.objects.create(
            item=cls.season1_item,
            content_number=5,
            datetime=ten_mins_ago,
            notification_sent=False,
        )

    def test_format_notification(self):
        """Test the format_notification function."""
        releases = [self.anime_event, self.manga_event, self.season1_event]
        notification_text = format_notification(releases)

        self.assertIn("Anime", notification_text)
        self.assertIn("Manga", notification_text)
        self.assertIn("TV Shows", notification_text)
        self.assertIn("Test Anime", notification_text)
        self.assertIn("Test Manga", notification_text)
        self.assertIn("Test TV Show", notification_text)
        self.assertIn("E5", notification_text)
        self.assertIn("#10", notification_text)

        releases = [self.anime_event]
        notification_text = format_notification(releases)

        self.assertIn("Anime", notification_text)
        self.assertIn("Test Anime", notification_text)
        self.assertIn("E5", notification_text)
        self.assertNotIn("Manga", notification_text)
        self.assertNotIn("Test Manga", notification_text)

    def test_format_notification_sentinel_time(self):
        """Test that sentinel times don't show a time string."""
        sentinel_event = Event.objects.create(
            item=self.anime_item,
            content_number=99,
            datetime=timezone.datetime(
                2025,
                6,
                15,
                SentinelDatetime.HOUR,
                SentinelDatetime.MINUTE,
                SentinelDatetime.SECOND,
                SentinelDatetime.MICROSECOND,
                tzinfo=UTC,
            ),
            notification_sent=False,
        )

        notification_text = format_notification(releases=[sentinel_event])
        self.assertNotIn("(", notification_text)
        self.assertIn("Test Anime", notification_text)

    def test_format_notification_empty_releases(self):
        """Test format_notification with an empty releases list."""
        notification_text = format_notification(releases=[])
        self.assertIn("Enjoy your media!", notification_text)
        self.assertNotIn("ANIME", notification_text)
