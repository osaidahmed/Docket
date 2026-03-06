from collections import defaultdict
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django_celery_beat.models import CrontabSchedule, PeriodicTask

from app.models import (
    TV,
    Anime,
    Episode,
    Item,
    MediaTypes,
    Movie,
    Season,
    Sources,
    Status,
)
from integrations.imports import (
    helpers,
)

mock_path = Path(__file__).resolve().parent.parent / "mock_data"
app_mock_path = (
    Path(__file__).resolve().parent.parent.parent.parent / "app" / "tests" / "mock_data"
)


class HelpersTest(TestCase):
    """Test helper functions for imports."""

    def setUp(self):
        """Set up test data."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)

    def test_update_season_references(self):
        """Test updating season references with actual TV instances."""
        item = Item.objects.create(
            media_id="1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Test Show",
        )
        tv = TV.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        new_season = Season(
            item=item,
            user=self.user,
            related_tv=TV(item=item, user=self.user),
        )

        helpers.update_season_references([new_season], self.user)

        self.assertEqual(new_season.related_tv.id, tv.id)

    def test_update_episode_references(self):
        """Test updating episode references with actual Season instances."""
        tv_item = Item.objects.create(
            media_id="1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Test Show",
        )
        tv = TV.objects.create(
            item=tv_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        season_item = Item.objects.create(
            media_id="1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test Show",
            season_number=1,
        )
        season = Season.objects.create(
            item=season_item,
            user=self.user,
            related_tv=tv,
            status=Status.PLANNING.value,
        )

        episode_item = Item.objects.create(
            media_id="1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            title="Test Show",
            season_number=1,
            episode_number=1,
        )

        new_episode = Episode(
            item=episode_item,
            related_season=Season(item=season_item, related_tv=tv, user=self.user),
        )

        helpers.update_episode_references([new_episode], self.user)

        self.assertEqual(new_episode.related_season.id, season.id)

    @patch("django.contrib.messages.error")
    def test_create_import_schedule(self, mock_messages):
        """Test creating import schedule."""
        request = Mock()
        request.user = self.user

        helpers.create_import_schedule(
            "testuser",
            request,
            "new",
            "daily",
            "14:30",
            "TestSource",
        )

        schedule = PeriodicTask.objects.first()
        self.assertIsNotNone(schedule)
        self.assertEqual(
            schedule.name,
            "Import from TestSource for testuser at 14:30:00 daily",
        )

        helpers.create_import_schedule(
            "testuser",
            request,
            "new",
            "daily",
            "14:30",
            "TestSource",
        )
        mock_messages.assert_called_with(
            request,
            "The same import task is already scheduled.",
        )

    @patch("django.contrib.messages.error")
    def test_create_import_schedule_invalid_time(self, mock_messages):
        """Test creating import schedule with invalid time."""
        request = Mock()
        request.user = self.user

        helpers.create_import_schedule(
            "testuser",
            request,
            "new",
            "daily",
            "25:00",  # Invalid time
            "TestSource",
        )

        mock_messages.assert_called_with(request, "Invalid import time.")
        self.assertEqual(PeriodicTask.objects.count(), 0)

    def test_create_import_schedule_every_2_days(self):
        """Test creating import schedule for every 2 days."""
        request = Mock()
        request.user = self.user

        helpers.create_import_schedule(
            "testuser",
            request,
            "new",
            "every_2_days",
            "14:30",
            "TestSource",
        )

        schedule = CrontabSchedule.objects.first()
        self.assertEqual(schedule.day_of_week, "*/2")

    def test_get_existing_media(self):
        item = Item.objects.create(
            media_id="1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
        )
        from simple_history.utils import bulk_create_with_history
        movie = Movie(item=item, user=self.user, status=Status.COMPLETED.value)
        bulk_create_with_history([movie], Movie, default_user=self.user)

        existing = helpers.get_existing_media(self.user)
        self.assertIn("1", existing[MediaTypes.MOVIE.value][Sources.TMDB.value])

    def test_get_existing_media_empty(self):
        existing = helpers.get_existing_media(self.user)
        self.assertEqual(len(existing[MediaTypes.MOVIE.value][Sources.TMDB.value]), 0)

    def test_should_process_media_new_mode_exists(self):
        existing_media = defaultdict(lambda: defaultdict(dict))
        existing_media[MediaTypes.MOVIE.value][Sources.TMDB.value]["123"] = True
        to_delete = defaultdict(lambda: defaultdict(set))

        result = helpers.should_process_media(
            existing_media, to_delete,
            MediaTypes.MOVIE.value, Sources.TMDB.value, "123", "new",
        )
        self.assertFalse(result)

    def test_should_process_media_new_mode_not_exists(self):
        existing_media = defaultdict(lambda: defaultdict(dict))
        to_delete = defaultdict(lambda: defaultdict(set))

        result = helpers.should_process_media(
            existing_media, to_delete,
            MediaTypes.MOVIE.value, Sources.TMDB.value, "123", "new",
        )
        self.assertTrue(result)

    def test_should_process_media_overwrite_mode_exists(self):
        existing_media = defaultdict(lambda: defaultdict(dict))
        existing_media[MediaTypes.MOVIE.value][Sources.TMDB.value]["123"] = True
        to_delete = defaultdict(lambda: defaultdict(set))

        result = helpers.should_process_media(
            existing_media, to_delete,
            MediaTypes.MOVIE.value, Sources.TMDB.value, "123", "overwrite",
        )
        self.assertTrue(result)
        self.assertIn("123", to_delete[MediaTypes.MOVIE.value][Sources.TMDB.value])

    def test_cleanup_existing_media(self):
        item = Item.objects.create(
            media_id="1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="To Delete Movie",
        )
        from simple_history.utils import bulk_create_with_history
        movie = Movie(item=item, user=self.user, status=Status.COMPLETED.value)
        bulk_create_with_history([movie], Movie, default_user=self.user)

        to_delete = defaultdict(lambda: defaultdict(set))
        to_delete[MediaTypes.MOVIE.value][Sources.TMDB.value].add("1")

        helpers.cleanup_existing_media(to_delete, self.user)
        self.assertEqual(Movie.objects.filter(user=self.user).count(), 0)

    def test_cleanup_existing_media_empty(self):
        to_delete = defaultdict(lambda: defaultdict(set))
        helpers.cleanup_existing_media(to_delete, self.user)

    def test_bulk_create_media_with_seasons_and_episodes(self):
        from simple_history.utils import bulk_create_with_history

        tv_item = Item.objects.create(
            media_id="1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Test Show",
        )
        tv = TV(item=tv_item, user=self.user, status=Status.IN_PROGRESS.value)
        bulk_create_with_history([tv], TV, default_user=self.user)
        tv = TV.objects.get(item=tv_item, user=self.user)

        season_item = Item.objects.create(
            media_id="1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test Show",
            season_number=1,
        )

        episode_item = Item.objects.create(
            media_id="1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            title="Test Show",
            season_number=1,
            episode_number=1,
        )

        season_obj = Season(
            item=season_item,
            user=self.user,
            related_tv=tv,
            status=Status.IN_PROGRESS.value,
        )

        bulk_media = defaultdict(list)
        bulk_media[MediaTypes.SEASON.value].append(season_obj)

        helpers.bulk_create_media(bulk_media, self.user)
        self.assertEqual(Season.objects.filter(user=self.user).count(), 1)

        saved_season = Season.objects.get(user=self.user)
        episode_obj = Episode(
            item=episode_item,
            related_season=saved_season,
        )

        bulk_media2 = defaultdict(list)
        bulk_media2[MediaTypes.EPISODE.value].append(episode_obj)

        helpers.bulk_create_media(bulk_media2, self.user)
        self.assertEqual(Episode.objects.count(), 1)

    @patch("django.contrib.messages.success")
    def test_create_import_schedule_with_token(self, mock_messages):
        request = Mock()
        request.user = self.user

        helpers.create_import_schedule(
            "testuser",
            request,
            "new",
            "daily",
            "10:00",
            "TestSource",
            token="encrypted_token",
        )

        task = PeriodicTask.objects.first()
        self.assertIsNotNone(task)
        import json
        kwargs = json.loads(task.kwargs)
        self.assertEqual(kwargs["token"], "encrypted_token")

    def test_join_with_commas_and(self):
        self.assertEqual(helpers.join_with_commas_and([]), "")
        self.assertEqual(helpers.join_with_commas_and(["a"]), "a")
        self.assertEqual(helpers.join_with_commas_and(["a", "b"]), "a and b")
        self.assertEqual(
            helpers.join_with_commas_and(["a", "b", "c"]),
            "a, b and c",
        )

    def test_encrypt_decrypt_roundtrip(self):
        original = "test_secret_value"
        encrypted = helpers.encrypt(original)
        decrypted = helpers.decrypt(encrypted)
        self.assertEqual(decrypted, original)
        self.assertNotEqual(encrypted, original)
