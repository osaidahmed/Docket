from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.db import models
from django.test import TestCase, override_settings
from django.utils import timezone

from app.models import TV, Anime, Item, Manga, MediaTypes, Season, Sources, Status
from events.models import Event
from events.notifications import (
    send_daily_digest,
    send_notifications,
    send_releases,
)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class SendingTests(TestCase):
    """Tests for notification sending, digest building, and delivery preferences."""

    @classmethod
    def setUpTestData(cls):
        cls._create_users()
        cls._create_items()
        cls._create_media_tracking()
        cls._create_events()
        cls.user1.notification_excluded_items.add(cls.manga_item)

    @classmethod
    def _create_users(cls):
        cls.user1 = get_user_model().objects.create_user(
            username="user1",
            password="12345",
            notification_urls="https://example.com/notify1",
        )
        cls.user2 = get_user_model().objects.create_user(
            username="user2",
            password="12345",
            notification_urls="https://example.com/notify2",
        )
        cls.user3 = get_user_model().objects.create_user(
            username="user3",
            password="12345",
        )

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
        cls.season1_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test TV Show - Season 1",
            season_number=1,
            image="http://example.com/tv.jpg",
        )
        cls.season2_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test TV Show - Season 2",
            season_number=2,
            image="http://example.com/tv.jpg",
        )
        cls.season3_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test TV Show - Season 3",
            season_number=3,
            image="http://example.com/tv.jpg",
        )

    @classmethod
    def _create_media_tracking(cls):
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
            ],
        )

    @classmethod
    def _create_events(cls):
        now = timezone.now()
        ten_mins_ago = now - timedelta(minutes=10)

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
        cls.season2_event = Event.objects.create(
            item=cls.season2_item,
            content_number=3,
            datetime=ten_mins_ago,
            notification_sent=False,
        )
        cls.season3_event = Event.objects.create(
            item=cls.season3_item,
            content_number=1,
            datetime=ten_mins_ago,
            notification_sent=False,
        )

    def _all_event_ids(self):
        return [
            self.anime_event.id,
            self.manga_event.id,
            self.season1_event.id,
            self.season2_event.id,
            self.season3_event.id,
        ]

    @patch("events.notifications.send_notifications")
    def test_end_to_end_notification(self, mock_send_notifications):
        """Test the entire notification flow."""
        mock_send_notifications.return_value = {
            "event_count": 5,
            "event_ids": self._all_event_ids(),
        }

        send_releases()

        self.anime_event.refresh_from_db()
        self.manga_event.refresh_from_db()
        self.season1_event.refresh_from_db()
        self.season2_event.refresh_from_db()
        self.season3_event.refresh_from_db()

        self.assertTrue(self.anime_event.notification_sent)
        self.assertTrue(self.manga_event.notification_sent)
        self.assertTrue(self.season1_event.notification_sent)
        self.assertTrue(self.season2_event.notification_sent)
        self.assertTrue(self.season3_event.notification_sent)

        mock_send_notifications.assert_called_once()

    @patch("events.notifications.send_notifications")
    def test_exclude_then_notify(self, mock_send_notifications):
        """Test excluding an item then verifying it's not in notifications."""
        item2 = Item.objects.create(
            media_id="100",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Another Anime",
            image="http://example.com/anime2.jpg",
        )

        Anime.objects.create(
            item=item2,
            user=self.user1,
            status=Status.IN_PROGRESS.value,
        )

        now = timezone.now()
        ten_mins_ago = now - timedelta(minutes=10)

        event2 = Event.objects.create(
            item=item2,
            content_number=3,
            datetime=ten_mins_ago,
            notification_sent=False,
        )

        mock_send_notifications.return_value = {
            "event_count": 6,
            "event_ids": self._all_event_ids() + [event2.id],
        }

        self.user1.notification_excluded_items.add(self.anime_item)

        send_releases()

        self.anime_event.refresh_from_db()
        event2.refresh_from_db()
        self.manga_event.refresh_from_db()
        self.assertTrue(self.anime_event.notification_sent)
        self.assertTrue(event2.notification_sent)
        self.assertTrue(self.manga_event.notification_sent)

    @patch("events.notifications.send_notifications")
    def test_no_users_with_notifications(self, mock_send_notifications):
        """Test behavior when no users have notification URLs configured."""
        mock_send_notifications.return_value = {
            "event_count": 5,
            "event_ids": self._all_event_ids(),
        }

        get_user_model().objects.all().update(notification_urls="")

        send_releases()

        mock_send_notifications.assert_not_called()

    @patch("events.notifications.send_notifications")
    def test_multiple_media_types(self, mock_send_notifications):
        """Test notifications with multiple media types."""
        mock_send_notifications.return_value = {
            "event_count": 5,
            "event_ids": self._all_event_ids(),
        }

        self.user1.notification_excluded_items.remove(self.manga_item)

        send_releases()

        self.anime_event.refresh_from_db()
        self.manga_event.refresh_from_db()
        self.season1_event.refresh_from_db()
        self.season2_event.refresh_from_db()
        self.season3_event.refresh_from_db()

        self.assertTrue(self.anime_event.notification_sent)
        self.assertTrue(self.manga_event.notification_sent)
        self.assertTrue(self.season1_event.notification_sent)
        self.assertTrue(self.season2_event.notification_sent)
        self.assertTrue(self.season3_event.notification_sent)

    @patch("events.notifications.send_notifications")
    def test_send_releases(self, mock_send_notifications):
        """Test the send_releases task."""
        mock_send_notifications.return_value = {
            "event_count": 5,
            "event_ids": self._all_event_ids(),
        }

        send_releases()

        self.anime_event.refresh_from_db()
        self.manga_event.refresh_from_db()
        self.season1_event.refresh_from_db()
        self.season2_event.refresh_from_db()
        self.season3_event.refresh_from_db()

        self.assertTrue(self.anime_event.notification_sent)
        self.assertTrue(self.manga_event.notification_sent)
        self.assertTrue(self.season1_event.notification_sent)
        self.assertTrue(self.season2_event.notification_sent)
        self.assertTrue(self.season3_event.notification_sent)

    @patch("apprise.Apprise")
    def test_send_notifications(self, mock_apprise):
        """Test the send_notifications function."""
        mock_instance = MagicMock()
        mock_apprise.return_value = mock_instance
        mock_instance.notify.return_value = True

        users_with_notifications = (
            get_user_model()
            .objects.filter(
                ~models.Q(notification_urls=""),
            )
            .prefetch_related("notification_excluded_items")
        )

        recent_events = Event.objects.filter(
            notification_sent=False,
        ).select_related("item")

        result = send_notifications(
            recent_events,
            users_with_notifications,
            "Test Title",
        )

        self.assertIn("event_count", result)
        self.assertIn("event_ids", result)
        self.assertEqual(result["event_count"], 5)
        self.assertEqual(len(result["event_ids"]), 5)

    @patch("events.notifications.send_notifications")
    def test_no_recent_events(self, mock_send_notifications):
        """Test behavior when no recent events are found."""
        Event.objects.all().update(notification_sent=True)

        result = send_releases()

        mock_send_notifications.assert_not_called()

        self.assertEqual(result, "No recent releases found")

    def test_future_events_not_included(self):
        """Test that future events are not included in notifications."""
        now = timezone.now()
        one_hour_ahead = now + timedelta(hours=1)

        future_event = Event.objects.create(
            item=self.anime_item,
            content_number=6,
            datetime=one_hour_ahead,
            notification_sent=False,
        )

        send_releases()

        future_event.refresh_from_db()
        self.assertFalse(future_event.notification_sent)

    @patch("apprise.Apprise")
    def test_exception_during_notification(self, mock_apprise):
        """Test handling of exceptions during notification."""
        mock_instance = MagicMock()
        mock_apprise.return_value = mock_instance
        mock_instance.notify.side_effect = Exception("Test exception")

        users_with_notifications = (
            get_user_model()
            .objects.filter(
                ~models.Q(notification_urls=""),
            )
            .prefetch_related("notification_excluded_items")
        )

        recent_events = Event.objects.filter(
            notification_sent=False,
        ).select_related("item")

        result = send_notifications(
            recent_events,
            users_with_notifications,
            "Test Title",
        )

        self.assertIn("event_count", result)
        self.assertIn("event_ids", result)

    @patch("events.notifications.send_notifications")
    def test_release_notifications_disabled(self, mock_send_notifications):
        """Test that users with disabled release_notifications_enabled."""
        mock_send_notifications.return_value = {
            "event_count": 5,
            "event_ids": self._all_event_ids(),
        }

        self.user1.release_notifications_enabled = False
        self.user1.save()

        send_releases()

        mock_send_notifications.assert_called_once()

        users = mock_send_notifications.call_args[1]["users"]

        user_ids = [user.id for user in users]
        self.assertNotIn(self.user1.id, user_ids)

        self.assertIn(self.user2.id, user_ids)

    @patch("events.notifications.send_notifications")
    def test_all_users_notifications_disabled(self, mock_send_notifications):
        """Test behavior when all users have notifications disabled."""
        mock_send_notifications.return_value = {}

        get_user_model().objects.all().update(release_notifications_enabled=False)

        send_releases()

        mock_send_notifications.assert_not_called()

    @patch("events.notifications.send_notifications")
    def test_send_daily_digest(self, mock_send_notifications):
        """Test the send_daily_digest task."""
        mock_send_notifications.return_value = {
            "event_count": 5,
            "event_ids": self._all_event_ids(),
        }

        now = timezone.localtime()
        today = now.replace(hour=12, minute=0, second=0, microsecond=0)

        self.anime_event.datetime = today
        self.anime_event.save()

        self.manga_event.datetime = today
        self.manga_event.save()

        self.season1_event.datetime = today
        self.season1_event.save()

        self.season2_event.datetime = today
        self.season2_event.save()

        self.season3_event.datetime = today
        self.season3_event.save()

        self.user1.daily_digest_enabled = True
        self.user1.save()

        self.user2.daily_digest_enabled = True
        self.user2.save()

        result = send_daily_digest()

        mock_send_notifications.assert_called_once()

        self.assertEqual(result, "Daily digest sent for 5 releases")

    @patch("events.notifications.send_notifications")
    def test_daily_digest_no_releases(self, mock_send_notifications):
        """Test daily digest when no releases are scheduled for today."""
        now = timezone.now()
        tomorrow = now + timedelta(days=1)

        self.anime_event.datetime = tomorrow
        self.anime_event.save()

        self.manga_event.datetime = tomorrow
        self.manga_event.save()

        self.season1_event.datetime = tomorrow
        self.season1_event.save()

        self.season2_event.datetime = tomorrow
        self.season2_event.save()

        self.season3_event.datetime = tomorrow
        self.season3_event.save()

        self.user1.daily_digest_enabled = True
        self.user1.save()

        result = send_daily_digest()

        mock_send_notifications.assert_not_called()

        self.assertEqual(result, "No releases scheduled for today")

    @patch("events.notifications.send_notifications")
    def test_daily_digest_no_users(self, mock_send_notifications):
        """Test daily digest when no users have it enabled."""
        now = timezone.now()
        today = now.replace(hour=12, minute=0, second=0, microsecond=0)

        self.anime_event.datetime = today
        self.anime_event.save()

        get_user_model().objects.all().update(daily_digest_enabled=False)

        result = send_daily_digest()

        mock_send_notifications.assert_not_called()

        self.assertEqual(result, "No users with daily digest enabled")

    @patch("events.notifications.send_notifications")
    def test_daily_digest_excluded_items(self, mock_send_notifications):
        """Test daily digest respects excluded items."""
        mock_send_notifications.return_value = {
            "event_count": 4,
            "event_ids": [
                self.anime_event.id,
                self.season1_event.id,
                self.season2_event.id,
                self.season3_event.id,
            ],
        }

        now = timezone.localtime()
        today = now.replace(hour=12, minute=0, second=0, microsecond=0)

        self.anime_event.datetime = today
        self.anime_event.save()

        self.manga_event.datetime = today
        self.manga_event.save()

        self.season1_event.datetime = today
        self.season1_event.save()

        self.season2_event.datetime = today
        self.season2_event.save()

        self.season3_event.datetime = today
        self.season3_event.save()

        self.user1.daily_digest_enabled = True
        self.user1.save()

        result = send_daily_digest()

        mock_send_notifications.assert_called_once()

        self.assertEqual(result, "Daily digest sent for 4 releases")

    @patch("events.notifications.send_notifications")
    def test_daily_digest_timezone_handling(self, mock_send_notifications):
        """Test daily digest handles timezones correctly."""
        mock_send_notifications.return_value = {
            "event_count": 5,
            "event_ids": self._all_event_ids(),
        }

        now_in_current_tz = timezone.localtime()

        today_in_current_tz = now_in_current_tz.replace(
            hour=12,
            minute=0,
            second=0,
            microsecond=0,
        )

        self.anime_event.datetime = today_in_current_tz
        self.anime_event.save()

        self.manga_event.datetime = today_in_current_tz
        self.manga_event.save()

        self.season1_event.datetime = today_in_current_tz
        self.season1_event.save()

        self.season2_event.datetime = today_in_current_tz
        self.season2_event.save()

        self.season3_event.datetime = today_in_current_tz
        self.season3_event.save()

        self.user1.daily_digest_enabled = True
        self.user1.save()

        result = send_daily_digest()

        mock_send_notifications.assert_called_once()

        self.assertEqual(result, "Daily digest sent for 5 releases")

    @patch("events.notifications.send_notifications")
    def test_daily_digest_with_notification_urls(self, mock_send_notifications):
        """Test daily digest only sends to users with notification URLs."""
        mock_send_notifications.return_value = {
            "event_count": 5,
            "event_ids": self._all_event_ids(),
        }

        now = timezone.localtime()
        today = now.replace(hour=12, minute=0, second=0, microsecond=0)

        self.anime_event.datetime = today
        self.anime_event.save()

        self.manga_event.datetime = today
        self.manga_event.save()

        self.season1_event.datetime = today
        self.season1_event.save()

        self.season2_event.datetime = today
        self.season2_event.save()

        self.season3_event.datetime = today
        self.season3_event.save()

        get_user_model().objects.all().update(daily_digest_enabled=True)

        self.user2.notification_urls = ""
        self.user2.save()

        result = send_daily_digest()

        mock_send_notifications.assert_called_once()

        users = mock_send_notifications.call_args[1]["users"]
        user_ids = [user.id for user in users]
        self.assertIn(self.user1.id, user_ids)
        self.assertNotIn(self.user2.id, user_ids)

        self.assertEqual(result, "Daily digest sent for 5 releases")
