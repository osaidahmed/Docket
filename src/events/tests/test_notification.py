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


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TrackingTests(TestCase):
    """Tests for TV tracking, user release collection, and item tracking status."""

    @classmethod
    def _create_items(cls):
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
        cls.tv_show_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Test TV Show",
            image="http://example.com/tv.jpg",
        )
        for sn in range(1, 4):
            setattr(
                cls,
                f"season{sn}_item",
                Item.objects.create(
                    media_id="1668",
                    source=Sources.TMDB.value,
                    media_type=MediaTypes.SEASON.value,
                    title=f"Test TV Show - Season {sn}",
                    season_number=sn,
                    image="http://example.com/tv.jpg",
                ),
            )

    @classmethod
    def _create_events(cls):
        ten_mins_ago = timezone.now() - timedelta(minutes=10)
        event_defs = [
            ("anime_event", cls.anime_item, 5),
            ("manga_event", cls.manga_item, 10),
            ("season1_event", cls.season1_item, 5),
            ("season2_event", cls.season2_item, 3),
            ("season3_event", cls.season3_item, 1),
        ]
        for attr, item, num in event_defs:
            setattr(
                cls,
                attr,
                Event.objects.create(
                    item=item,
                    content_number=num,
                    datetime=ten_mins_ago,
                    notification_sent=False,
                ),
            )

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user1 = User.objects.create_user(
            username="user1",
            password="12345",
            notification_urls="https://example.com/notify1",
        )
        cls.user2 = User.objects.create_user(
            username="user2",
            password="12345",
            notification_urls="https://example.com/notify2",
        )
        cls.user3 = User.objects.create_user(
            username="user3",
            password="12345",
        )
        cls._create_items()

        for user in (cls.user1, cls.user2, cls.user3):
            Anime.objects.create(
                item=cls.anime_item,
                user=user,
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
                )
            ]
        )

        cls._create_events()
        cls.user1.notification_excluded_items.add(cls.manga_item)

    def _target_events(self, *events):
        return {(e.item.id, e.content_number): e for e in events}

    def _notified_users(self, **filter_kwargs):
        qs = get_user_model().objects.filter(~models.Q(notification_urls=""))
        if filter_kwargs:
            qs = qs.filter(**filter_kwargs)
        return qs.prefetch_related("notification_excluded_items")

    # --- TV tracking tests ---

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

    # --- User release and tracking tests ---

    def test_get_all_user_tracking_data(self):
        """Test the get_all_user_tracking_data function."""
        users = self._notified_users()
        target_events = self._target_events(
            self.anime_event,
            self.manga_event,
            self.season1_event,
            self.season2_event,
        )
        user_exclusions = {
            u.id: set(u.notification_excluded_items.values_list("id", flat=True))
            for u in users
        }

        tracking_data = get_all_user_tracking_data(
            users,
            target_events,
            user_exclusions,
        )

        self.assertIsInstance(tracking_data, dict)
        self.assertIn((self.user1.id, self.anime_item.id), tracking_data)
        self.assertIn((self.user1.id, self.manga_item.id), tracking_data)
        self.assertIn((self.user1.id, self.season1_item.id), tracking_data)

    def test_get_user_releases(self):
        """Test the get_user_releases function."""
        target_events = self._target_events(
            self.anime_event,
            self.manga_event,
            self.season1_event,
            self.season2_event,
        )
        user_releases = get_user_releases(self._notified_users(), target_events)

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
        target_events = self._target_events(
            self.anime_event,
            self.manga_event,
            self.season1_event,
        )
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
        target_events = self._target_events(self.anime_event, self.manga_event)
        user_releases = get_user_releases(self._notified_users(), target_events)

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
        pref = self.user1.get_or_create_media_pref("anime")
        pref.enabled = False
        pref.save(update_fields=["enabled"])
        if hasattr(self.user1, "_pref_cache"):
            del self.user1._pref_cache
        self.user1.notification_excluded_items.clear()

        target_events = self._target_events(self.anime_event, self.manga_event)
        users = self._notified_users(id=self.user1.id)
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


class SendUserNotificationCallShapeTests(TestCase):
    """Pin Apprise notify() invocation shape (kwargs + URL list)."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="notify-shape",
            password="x",
        )

    def test_notify_called_with_title_and_body_kwargs(self):
        from unittest.mock import MagicMock, patch

        from events.notifications import send_user_notification

        with patch("events.notifications.apprise.Apprise") as mock_apprise_cls:
            mock_obj = MagicMock()
            mock_obj.notify.return_value = True
            mock_apprise_cls.return_value = mock_obj
            send_user_notification(
                self.user,
                ["mailto://user@x"],
                "Hello",
                "Body content",
            )
        mock_obj.notify.assert_called_once_with(title="Hello", body="Body content")

    def test_each_url_added_to_apprise(self):
        from unittest.mock import MagicMock, patch

        from events.notifications import send_user_notification

        with patch("events.notifications.apprise.Apprise") as mock_apprise_cls:
            mock_obj = MagicMock()
            mock_obj.notify.return_value = True
            mock_apprise_cls.return_value = mock_obj
            send_user_notification(
                self.user,
                ["mailto://a", "discord://b", "slack://c"],
                "Hello",
                "Body",
            )
        added_calls = [c.args[0] for c in mock_obj.add.call_args_list]
        self.assertEqual(added_calls, ["mailto://a", "discord://b", "slack://c"])

    def test_failed_notify_logs_error(self):
        from unittest.mock import MagicMock, patch

        from events.notifications import send_user_notification

        with (
            patch("events.notifications.apprise.Apprise") as mock_apprise_cls,
            patch(
                "events.notifications.logger.error",
            ) as mock_error,
        ):
            mock_obj = MagicMock()
            mock_obj.notify.return_value = False
            mock_apprise_cls.return_value = mock_obj
            send_user_notification(
                self.user,
                ["mailto://a"],
                "Hello",
                "Body",
            )
        self.assertTrue(mock_error.called)
