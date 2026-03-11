from unittest.mock import patch

from django.test import TestCase


class CreateTaskResultOnPublishTests(TestCase):
    """Test the create_task_result_on_publish signal handler."""

    @patch("django_celery_results.models.TaskResult.objects.store_result")
    def test_missing_task_key_returns_early(self, mock_store):
        """Test that missing 'task' key in headers causes early return."""
        from app.signals import create_task_result_on_publish

        create_task_result_on_publish(
            sender=None,
            headers={"id": "abc-123"},
            body=None,
        )

        mock_store.assert_not_called()

    @patch("django_celery_results.models.TaskResult.objects.store_result")
    def test_with_task_key_stores_result(self, mock_store):
        """Test that headers with 'task' key stores a PENDING result."""
        from app.signals import create_task_result_on_publish

        create_task_result_on_publish(
            sender=None,
            headers={
                "id": "abc-123",
                "task": "my_task",
                "argsrepr": "(1, 2)",
                "kwargsrepr": "{}",
            },
            body=None,
        )

        mock_store.assert_called_once()
        kwargs = mock_store.call_args[1]
        self.assertEqual(kwargs["task_id"], "abc-123")
        self.assertEqual(kwargs["task_name"], "my_task")
        self.assertEqual(kwargs["status"], "PENDING")
