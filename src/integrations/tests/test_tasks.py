from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import MediaTypes
from integrations import tasks
from integrations.tasks import (
    format_import_message,
    format_media_type_display,
    import_media,
)


class FormatMediaTypeDisplayTests(TestCase):
    def test_zero_count(self):
        result = format_media_type_display(0, MediaTypes.MOVIE.value)
        self.assertIsNone(result)

    def test_single_count(self):
        result = format_media_type_display(1, MediaTypes.MOVIE.value)
        self.assertIn("1", result)

    def test_plural_count(self):
        result = format_media_type_display(3, MediaTypes.MOVIE.value)
        self.assertIn("3", result)


class FormatImportMessageTests(TestCase):
    def test_no_imports(self):
        result = format_import_message({})
        self.assertEqual(result, "No media was imported.")

    def test_with_imports(self):
        result = format_import_message(
            {MediaTypes.MOVIE.value: 2, MediaTypes.ANIME.value: 1}
        )
        self.assertIn("Imported", result)

    def test_with_warnings(self):
        result = format_import_message(
            {MediaTypes.MOVIE.value: 1}, "Warning: Something failed"
        )
        self.assertIn("Imported", result)
        self.assertIn("Warning", result)

    def test_no_imports_with_warnings(self):
        result = format_import_message({}, "Some warnings")
        self.assertIn("No media was imported.", result)
        self.assertIn("Some warnings", result)

    def test_all_zero_counts(self):
        result = format_import_message(
            {MediaTypes.MOVIE.value: 0, MediaTypes.ANIME.value: 0}
        )
        self.assertEqual(result, "No media was imported.")


class ImportMediaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="import_test", password="12345"
        )

    @patch("integrations.tasks.events.tasks.reload_calendar.delay")
    def test_import_media_basic(self, mock_reload):
        def mock_importer(identifier, user, mode):
            return {MediaTypes.MOVIE.value: 2}, None

        result = import_media(mock_importer, "test_id", self.user.id, "full")
        self.assertIn("Imported", result)
        mock_reload.assert_called_once()

    @patch("integrations.tasks.events.tasks.reload_calendar.delay")
    def test_import_media_with_oauth_username(self, mock_reload):
        def mock_importer(identifier, user, mode, username=None):
            return {MediaTypes.ANIME.value: 1}, None

        result = import_media(
            mock_importer, "token", self.user.id, "full", "oauth_user"
        )
        self.assertIn("Imported", result)
        mock_reload.assert_called_once()

    @patch("integrations.tasks.events.tasks.reload_calendar.delay")
    def test_import_media_with_warnings(self, mock_reload):
        def mock_importer(identifier, user, mode):
            return {MediaTypes.MOVIE.value: 1}, "Failed: Some title"

        result = import_media(mock_importer, "test_id", self.user.id, "full")
        self.assertIn("Imported", result)
        self.assertIn("Failed", result)


class TaskWrapperTests(TestCase):
    """Test that each @shared_task wrapper calls import_media correctly."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="task_wrap", password="12345"
        )

    @patch("integrations.tasks.import_media", return_value="ok")
    def test_task_wrappers_call_import_media(self, mock_import):
        cases = [
            ("import_trakt", {"user_id": self.user.id, "mode": "new", "token": "t"}),
            ("import_simkl", {"token": "t", "user_id": self.user.id, "mode": "new"}),
            ("import_mal", {"username": "u", "user_id": self.user.id, "mode": "new"}),
            ("import_anilist", {"user_id": self.user.id, "mode": "new", "token": "t"}),
            ("import_kitsu", {"username": "u", "user_id": self.user.id, "mode": "new"}),
            ("import_docket", {"file": "f", "user_id": self.user.id, "mode": "new"}),
            ("import_hltb", {"file": "f", "user_id": self.user.id, "mode": "new"}),
            ("import_steam", {"username": "u", "user_id": self.user.id, "mode": "new"}),
            ("import_imdb", {"file": "f", "user_id": self.user.id, "mode": "new"}),
            (
                "import_goodreads",
                {"file": "f", "user_id": self.user.id, "mode": "new"},
            ),
        ]
        for task_name, kwargs in cases:
            mock_import.reset_mock()
            with self.subTest(task=task_name):
                task_func = getattr(tasks, task_name)
                result = task_func(**kwargs)
                self.assertEqual(result, "ok")
                mock_import.assert_called_once()
