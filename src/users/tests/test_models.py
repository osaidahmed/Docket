from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from django_celery_results.models import TaskResult

from users.models import (
    HomeSortChoices,
    MediaTypes,
    QuickWatchDateChoices,
)


class UserUpdatePreferenceTests(TestCase):
    """Tests for the User.update_preference method."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = get_user_model().objects.create_user(
            username="test",
            password="12345",
        )

    def test_update_preference_no_new_value(self):
        """Test update_preference when no new value is provided."""
        # Set initial value
        self.user.home_sort = HomeSortChoices.UPCOMING
        self.user.save()

        # Call update_preference with no new value
        result = self.user.update_preference("home_sort", None)

        # Should return current value
        self.assertEqual(result, HomeSortChoices.UPCOMING)
        # Should not change the value
        self.user.refresh_from_db()
        self.assertEqual(self.user.home_sort, HomeSortChoices.UPCOMING)

    def test_update_preference_same_value(self):
        """Test update_preference when the new value is the same as current."""
        # Set initial value
        self.user.home_sort = HomeSortChoices.UPCOMING
        self.user.save()

        # Call update_preference with same value
        result = self.user.update_preference("home_sort", HomeSortChoices.UPCOMING)

        # Should return current value
        self.assertEqual(result, HomeSortChoices.UPCOMING)
        # Should not change the value
        self.user.refresh_from_db()
        self.assertEqual(self.user.home_sort, HomeSortChoices.UPCOMING)

    def test_update_preference_valid_value(self):
        """Test update_preference with a valid new value."""
        # Set initial value
        self.user.home_sort = HomeSortChoices.UPCOMING
        self.user.save()

        # Call update_preference with new valid value
        result = self.user.update_preference("home_sort", HomeSortChoices.TITLE)

        # Should return new value
        self.assertEqual(result, HomeSortChoices.TITLE)
        # Should change the value
        self.user.refresh_from_db()
        self.assertEqual(self.user.home_sort, HomeSortChoices.TITLE)

    def test_update_preference_invalid_value(self):
        """Test update_preference with an invalid new value."""
        # Set initial value
        self.user.home_sort = HomeSortChoices.UPCOMING
        self.user.save()

        # Call update_preference with invalid value
        result = self.user.update_preference("home_sort", "invalid_value")

        # Should return current value
        self.assertEqual(result, HomeSortChoices.UPCOMING)
        # Should not change the value
        self.user.refresh_from_db()
        self.assertEqual(self.user.home_sort, HomeSortChoices.UPCOMING)

    def test_update_preference_boolean_field(self):
        """Test update_preference with a per-type enabled field."""
        self.user.get_or_create_media_pref("tv")

        result = self.user.update_preference(field_name="tv_enabled", new_value=False)

        self.assertEqual(result, False)
        pref = self.user.media_preferences.get(media_type="tv")
        self.assertFalse(pref.enabled)

    def test_update_preference_last_search_type_valid(self):
        """Test update_preference with last_search_type and valid value."""
        # Set initial value
        self.user.last_search_type = MediaTypes.TV.value
        self.user.save()

        # Call update_preference with new valid value
        result = self.user.update_preference("last_search_type", MediaTypes.MOVIE.value)

        # Should return new value
        self.assertEqual(result, MediaTypes.MOVIE.value)
        # Should change the value
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_search_type, MediaTypes.MOVIE.value)

    def test_update_preference_last_search_type_invalid(self):
        """Test update_preference with last_search_type and invalid value."""
        # Set initial value
        self.user.last_search_type = MediaTypes.TV.value
        self.user.save()

        # Call update_preference with invalid value (SEASON is in EXCLUDED_SEARCH_TYPES)
        result = self.user.update_preference(
            "last_search_type",
            MediaTypes.SEASON.value,
        )

        # Should return current value
        self.assertEqual(result, MediaTypes.TV.value)
        # Should not change the value
        self.user.refresh_from_db()
        self.assertEqual(self.user.last_search_type, MediaTypes.TV.value)

    def test_update_preference_daily_digest_enabled(self):
        """Test update_preference with daily_digest_enabled field."""
        # Set initial value
        self.user.daily_digest_enabled = True
        self.user.save()

        # Call update_preference with new value
        result = self.user.update_preference(
            field_name="daily_digest_enabled",
            new_value=False,
        )

        # Should return new value
        self.assertEqual(result, False)
        # Should change the value
        self.user.refresh_from_db()
        self.assertEqual(self.user.daily_digest_enabled, False)

    def test_update_preference_release_notifications_enabled(self):
        """Test update_preference with release_notifications_enabled field."""
        # Set initial value
        self.user.release_notifications_enabled = True
        self.user.save()

        # Call update_preference with new value
        result = self.user.update_preference(
            field_name="release_notifications_enabled",
            new_value=False,
        )

        # Should return new value
        self.assertEqual(result, False)
        # Should change the value
        self.user.refresh_from_db()
        self.assertEqual(self.user.release_notifications_enabled, False)


class UserGetImportTasksTests(TestCase):
    """Tests for the User.get_import_tasks method."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = get_user_model().objects.create_user(
            username="test",
            password="12345",
        )
        cls.other_user = get_user_model().objects.create_user(
            username="otheruser",
            password="12345",
        )

        # Create a crontab schedule for periodic tasks
        cls.crontab = CrontabSchedule.objects.create(
            minute="0",
            hour="0",
            day_of_week="*",
            day_of_month="*",
            month_of_year="*",
        )

    @patch("users.helpers.process_task_result")
    def test_get_import_tasks_results(self, mock_process_task_result):
        """Test get_import_tasks returns correct task results."""
        # Create mock processed task
        mock_task = MagicMock()
        mock_task.summary = "Imported 10 items"
        mock_task.errors = []
        mock_task.mode = "overwrite"
        mock_process_task_result.return_value = mock_task

        # Create task results for the user
        TaskResult.objects.create(
            task_id="task1",
            task_name="Import from Trakt",
            task_kwargs=(f"{{'user_id': {self.user.id}, 'username': 'testuser'}}"),
            status="SUCCESS",
            date_done=timezone.now() - timedelta(days=1),
            result="{}",
        )

        TaskResult.objects.create(
            task_id="task2",
            task_name="Import from MyAnimeList",
            task_kwargs=(f"{{'user_id': {self.user.id}, 'username': 'testuser'}}"),
            status="FAILURE",
            date_done=timezone.now(),
            result="{}",
        )

        # Create task result for another user (should not be included)
        TaskResult.objects.create(
            task_id="task3",
            task_name="Import from Trakt",
            task_kwargs=(
                f"{{'user_id': {self.other_user.id}, 'username': 'otheruser'}}"
            ),
            status="SUCCESS",
            date_done=timezone.now(),
            result="{}",
        )

        # Get import tasks
        import_tasks = self.user.get_import_tasks()

        # Check results
        self.assertEqual(len(import_tasks["results"]), 2)

        # Check first result (most recent)
        self.assertEqual(import_tasks["results"][1]["task"], mock_task)
        self.assertEqual(import_tasks["results"][1]["source"], "trakt")
        self.assertEqual(import_tasks["results"][1]["status"], "SUCCESS")
        self.assertEqual(import_tasks["results"][1]["summary"], "Imported 10 items")
        self.assertEqual(import_tasks["results"][1]["errors"], [])

        # Check second result
        self.assertEqual(import_tasks["results"][0]["task"], mock_task)
        self.assertEqual(import_tasks["results"][0]["source"], "myanimelist")
        self.assertEqual(import_tasks["results"][0]["status"], "FAILURE")

    @patch("users.helpers.get_next_run_info")
    def test_get_import_tasks_schedules(self, mock_get_next_run_info):
        """Test get_import_tasks returns correct scheduled tasks."""
        # Create mock next run info
        mock_get_next_run_info.return_value = {
            "next_run": timezone.now() + timedelta(days=1),
            "frequency": "Daily at midnight",
            "mode": "overwrite",
        }

        # Create periodic tasks for the user
        periodic_task1 = PeriodicTask.objects.create(
            name="Import from Trakt for testuser at daily",
            task="Import from Trakt",
            kwargs=(f'{{"user_id": {self.user.id}, "username": "testuser"}}'),
            crontab=self.crontab,
            enabled=True,
        )

        periodic_task2 = PeriodicTask.objects.create(
            name="Import from AniList for testuser at weekly",
            task="Import from AniList",
            kwargs=(f'{{"user_id": {self.user.id}, "username": "testuser"}}'),
            crontab=self.crontab,
            enabled=True,
        )

        # Create disabled periodic task (should not be included)
        PeriodicTask.objects.create(
            name="Import from SIMKL for testuser at daily",
            task="Import from SIMKL",
            kwargs=(f'{{"user_id": {self.user.id}, "username": "testuser"}}'),
            crontab=self.crontab,
            enabled=False,
        )

        # Create periodic task for another user (should not be included)
        PeriodicTask.objects.create(
            name="Import from Trakt for otheruser at daily",
            task="Import from Trakt",
            kwargs=(f'{{"user_id": {self.other_user.id}, "username": "testuser"}}'),
            crontab=self.crontab,
            enabled=True,
        )

        # Get import tasks
        import_tasks = self.user.get_import_tasks()

        # Check schedules
        self.assertEqual(len(import_tasks["schedules"]), 2)

        # Check first schedule
        self.assertEqual(import_tasks["schedules"][0]["task"], periodic_task1)
        self.assertEqual(import_tasks["schedules"][0]["source"], "trakt")
        self.assertEqual(import_tasks["schedules"][0]["username"], "testuser")
        self.assertEqual(import_tasks["schedules"][0]["schedule"], "Daily at midnight")

        # Check second schedule
        self.assertEqual(import_tasks["schedules"][1]["task"], periodic_task2)
        self.assertEqual(import_tasks["schedules"][1]["source"], "anilist")
        self.assertEqual(import_tasks["schedules"][1]["username"], "testuser")

    @patch("users.helpers.process_task_result")
    @patch("users.helpers.get_next_run_info")
    def test_get_import_tasks_empty(
        self,
        mock_get_next_run_info,
        _,
    ):
        """Test get_import_tasks when there are no tasks."""
        # Set up mocks
        mock_get_next_run_info.return_value = None

        # Get import tasks
        import_tasks = self.user.get_import_tasks()

        # Check results
        self.assertEqual(len(import_tasks["results"]), 0)
        self.assertEqual(len(import_tasks["schedules"]), 0)

    @patch("users.helpers.process_task_result")
    def test_get_import_tasks_unknown_source(self, mock_process_task_result):
        """Test get_import_tasks with an unknown task source."""
        # Create mock processed task
        mock_task = MagicMock()
        mock_task.summary = "Imported 10 items"
        mock_task.errors = []
        mock_task.mode = "overwrite"
        mock_process_task_result.return_value = mock_task

        # Create task result with unknown source
        TaskResult.objects.create(
            task_id="task1",
            task_name="Import from Unknown",
            task_kwargs=(f"{{'user_id': {self.user.id}, 'username': 'testuser'}}"),
            status="SUCCESS",
            date_done=timezone.now(),
            result="{}",
        )

        # Get import tasks
        import_tasks = self.user.get_import_tasks()

        # Check results
        self.assertEqual(len(import_tasks["results"]), 0)


class UserResolveWatchDateTests(TestCase):
    """Tests for the User.resolve_watch_date method."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.QuickWatchDateChoices = QuickWatchDateChoices
        cls.user = get_user_model().objects.create_user(
            username="test_watch",
            password="12345",
        )
        cls.now = timezone.now()
        cls.release_date = datetime(2020, 5, 15, 20, 0, tzinfo=UTC)

    def test_resolve_watch_date_current_date(self):
        """Test resolve_watch_date returns current date for CURRENT_DATE."""
        self.user.quick_watch_date = self.QuickWatchDateChoices.CURRENT_DATE
        self.user.save()

        result = self.user.resolve_watch_date(self.now, self.release_date)

        self.assertEqual(result, self.now)

    def test_resolve_watch_date_release_date(self):
        """Test resolve_watch_date returns release date for RELEASE_DATE."""
        self.user.quick_watch_date = self.QuickWatchDateChoices.RELEASE_DATE
        self.user.save()

        result = self.user.resolve_watch_date(self.now, self.release_date)

        self.assertEqual(result, self.release_date)

    def test_resolve_watch_date_release_date_none(self):
        """Test resolve_watch_date returns None when release_date is None."""
        self.user.quick_watch_date = self.QuickWatchDateChoices.RELEASE_DATE
        self.user.save()

        result = self.user.resolve_watch_date(self.now, None)

        self.assertIsNone(result)

    def test_resolve_watch_date_no_date(self):
        """Test resolve_watch_date returns None when preference is NO_DATE."""
        self.user.quick_watch_date = self.QuickWatchDateChoices.NO_DATE
        self.user.save()

        result = self.user.resolve_watch_date(self.now, self.release_date)

        self.assertIsNone(result)

    def test_resolve_watch_date_default_is_current_date(self):
        """Test that default preference is CURRENT_DATE."""
        self.assertEqual(
            self.user.quick_watch_date,
            self.QuickWatchDateChoices.CURRENT_DATE,
        )

        result = self.user.resolve_watch_date(self.now, self.release_date)

        self.assertEqual(result, self.now)


class UserMediaTypeOrderTests(TestCase):
    """Tests for custom media type ordering."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="ordertest",
            password="12345",
        )

    def test_default_order_follows_enum(self):
        """Empty media_type_order falls back to MediaTypes enum order."""
        self.user.media_type_order = []
        self.user.save()

        result = self.user.get_enabled_media_types()

        skip = {MediaTypes.EPISODE.value, MediaTypes.SEASON.value}
        expected = [mt for mt in MediaTypes.values if mt not in skip]
        self.assertEqual(result, expected)

    def test_custom_order_respected(self):
        """Custom order is applied to enabled types."""
        self.user.media_type_order = [
            MediaTypes.GAME.value,
            MediaTypes.TV.value,
            MediaTypes.ANIME.value,
        ]
        self.user.save()

        result = self.user.get_enabled_media_types()

        self.assertEqual(result[0], MediaTypes.GAME.value)
        self.assertEqual(result[1], MediaTypes.TV.value)
        self.assertEqual(result[2], MediaTypes.ANIME.value)

    def test_partial_order_appends_missing(self):
        """Types not in custom order are appended in enum order."""
        self.user.media_type_order = [MediaTypes.GAME.value]
        self.user.save()

        result = self.user.get_enabled_media_types()

        self.assertEqual(result[0], MediaTypes.GAME.value)
        self.assertGreater(len(result), 1)

    def test_disabled_types_excluded_from_custom_order(self):
        """Disabled types don't appear even if in custom order."""
        from users.models import UserMediaPreference  # noqa: PLC0415

        pref = self.user.get_or_create_media_pref(MediaTypes.GAME.value)
        pref.enabled = False
        pref.save(update_fields=["enabled"])
        if hasattr(self.user, "_pref_cache"):
            del self.user._pref_cache
        self.user.media_type_order = [
            MediaTypes.GAME.value,
            MediaTypes.TV.value,
        ]
        self.user.save()

        result = self.user.get_enabled_media_types()

        self.assertNotIn(MediaTypes.GAME.value, result)

    def test_episode_excluded_from_custom_order(self):
        """Episode type is always excluded from enabled types."""
        self.user.media_type_order = [MediaTypes.EPISODE.value, MediaTypes.TV.value]
        self.user.save()

        result = self.user.get_enabled_media_types()

        self.assertNotIn(MediaTypes.EPISODE.value, result)

    def test_active_types_season_after_tv(self):
        """SEASON is inserted right after TV in get_active_media_types."""
        self.user.media_type_order = [
            MediaTypes.GAME.value,
            MediaTypes.TV.value,
            MediaTypes.ANIME.value,
        ]
        self.user.save()

        result = self.user.get_active_media_types()

        tv_idx = result.index(MediaTypes.TV.value)
        season_idx = result.index(MediaTypes.SEASON.value)
        self.assertEqual(season_idx, tv_idx + 1)


class PreferencesViewOrderTests(TestCase):
    """Tests for saving media_type_order via the preferences view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "preftest", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def test_saves_media_type_order(self):
        """POST with media_type_order JSON saves the order."""
        import json  # noqa: PLC0415

        from django.urls import reverse  # noqa: PLC0415

        order = ["game", "tv", "anime", "manga", "movie", "book", "comic", "boardgame"]
        self.client.post(
            reverse("preferences"),
            {
                "media_types_checkboxes": order,
                "media_type_order": json.dumps(order),
            },
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.media_type_order, order)

    def test_get_returns_ordered_media_types(self):
        """GET preferences returns media types in custom order."""
        from django.urls import reverse  # noqa: PLC0415

        self.user.media_type_order = ["game", "tv", "anime"]
        self.user.save()

        response = self.client.get(reverse("preferences"))

        media_types = response.context["media_types"]
        self.assertEqual(media_types[0], "game")
        self.assertEqual(media_types[1], "tv")
        self.assertEqual(media_types[2], "anime")
