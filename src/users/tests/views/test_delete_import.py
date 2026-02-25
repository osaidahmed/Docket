from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse
from django_celery_beat.models import CrontabSchedule, PeriodicTask


class DeleteImportScheduleTests(TestCase):
    """Tests for the delete_import_schedule view."""

    @classmethod
    def setUpTestData(cls):
        """Create user and test data for the tests."""
        cls.credentials = {"username": "testuser", "password": "testpass123"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.crontab = CrontabSchedule.objects.create(
            minute="0",
            hour="0",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
        )

        cls.task = PeriodicTask.objects.create(
            name="Import from Trakt for testuser at daily",
            task="Import from Trakt",
            kwargs=f'{{"user_id": {cls.user.id}, "username": "testuser"}}',
            crontab=cls.crontab,
            enabled=True,
        )

        cls.other_user = get_user_model().objects.create_user(
            username="otheruser",
            password="testpass123",
        )

        cls.other_task = PeriodicTask.objects.create(
            name="Import from Trakt for otheruser at daily",
            task="Import from Trakt",
            kwargs=f'{{"user_id": {cls.other_user.id}, "username": "otheruser"}}',
            crontab=cls.crontab,
            enabled=True,
        )

    def setUp(self):
        self.client.login(**self.credentials)

    def test_delete_import_schedule_success(self):
        """Test successful deletion of an import schedule."""
        response = self.client.post(
            reverse("delete_import_schedule"),
            {
                "task_name": self.task.name,
            },
        )
        self.assertRedirects(response, reverse("import_data"))

        with self.assertRaises(PeriodicTask.DoesNotExist):
            PeriodicTask.objects.get(id=self.task.id)

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("Import schedule deleted", str(messages[0]))

        self.assertTrue(PeriodicTask.objects.filter(id=self.other_task.id).exists())

    def test_delete_import_schedule_not_found(self):
        """Test deletion of a non-existent import schedule."""
        response = self.client.post(
            reverse("delete_import_schedule"),
            {
                "task_name": "Non-existent Task",
            },
        )
        self.assertRedirects(response, reverse("import_data"))

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("Import schedule not found", str(messages[0]))

        self.assertTrue(PeriodicTask.objects.filter(id=self.task.id).exists())

    def test_delete_import_schedule_other_user(self):
        """Test deletion of another user's import schedule."""
        response = self.client.post(
            reverse("delete_import_schedule"),
            {
                "task_name": self.other_task.name,
            },
        )
        self.assertRedirects(response, reverse("import_data"))

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("Import schedule not found", str(messages[0]))

        self.assertTrue(PeriodicTask.objects.filter(id=self.other_task.id).exists())
