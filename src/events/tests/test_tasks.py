from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class EventTaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="tasktest",
            password="12345",
        )

    @patch("events.calendar_processors.fetch_releases")
    def test_reload_calendar_with_user(self, mock_fetch):
        from events.tasks import reload_calendar

        mock_fetch.return_value = "done"
        result = reload_calendar(user=self.user)
        mock_fetch.assert_called_once_with(
            user=self.user,
            items_to_process=None,
        )
        self.assertEqual(result, "done")

    @patch("events.calendar_processors.fetch_releases")
    def test_reload_calendar_without_user(self, mock_fetch):
        from events.tasks import reload_calendar

        mock_fetch.return_value = "done"
        result = reload_calendar()
        mock_fetch.assert_called_once_with(
            user=None,
            items_to_process=None,
        )
        self.assertEqual(result, "done")

    @patch("events.notifications.send_releases")
    def test_send_release_notifications(self, mock_send):
        from events.tasks import send_release_notifications

        mock_send.return_value = "2 recent releases processed"
        result = send_release_notifications()
        mock_send.assert_called_once()
        self.assertEqual(result, "2 recent releases processed")

    @patch("events.notifications.send_daily_digest")
    def test_send_daily_digest_notifications(self, mock_send):
        from events.tasks import send_daily_digest_notifications

        mock_send.return_value = "Daily digest sent for 3 releases"
        result = send_daily_digest_notifications()
        mock_send.assert_called_once()
        self.assertEqual(result, "Daily digest sent for 3 releases")
