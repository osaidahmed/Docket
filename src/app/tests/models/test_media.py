from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import (
    Anime,
    Item,
    MediaTypes,
    Sources,
    Status,
)

mock_path = Path(__file__).resolve().parent.parent / "mock_data"


class MediaModel(TestCase):
    """Test the custom save of the Media model."""

    @classmethod
    def setUpTestData(cls):
        """Create a user."""
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        item_anime = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Cowboy Bebop",
            image="http://example.com/image.jpg",
        )

        cls.anime = Anime.objects.create(
            item=item_anime,
            user=cls.user,
            status=Status.PLANNING.value,
        )

    def test_completed_progress(self):
        """When completed, the progress should be the total number of episodes."""
        self.anime.status = Status.COMPLETED.value
        self.anime.save()
        self.assertEqual(
            Anime.objects.get(item__media_id="1", user=self.user).progress,
            26,
        )

    def test_progress_is_max(self):
        """When progress is maximum number of episodes.

        Status should be completed and end_date the current date if not specified.
        """
        self.anime.status = Status.IN_PROGRESS.value
        self.anime.progress = 26
        self.anime.save()

        self.assertEqual(
            Anime.objects.get(item__media_id="1", user=self.user).status,
            Status.COMPLETED.value,
        )
        self.assertIsNotNone(
            Anime.objects.get(item__media_id="1", user=self.user).end_date,
        )

    def test_progress_bigger_than_max(self):
        """When progress is bigger than max, it should be set to max."""
        self.anime.status = Status.IN_PROGRESS.value
        self.anime.progress = 30
        self.anime.save()
        self.assertEqual(
            Anime.objects.get(item__media_id="1", user=self.user).progress,
            26,
        )


class AnimeOngoingCompletionTests(TestCase):
    """Test that ongoing/upcoming anime cannot be fully completed."""

    @classmethod
    def setUpTestData(cls):
        """Create a user and anime instance."""
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.anime_item = Item.objects.create(
            media_id="99999",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Test Anime",
            image="http://example.com/image.jpg",
        )

        cls.anime = Anime.objects.create(
            item=cls.anime_item,
            user=cls.user,
            status=Status.PLANNING.value,
        )

    @patch("app.models.providers.services.get_media_metadata")
    def test_upcoming_anime_redirects_to_caught_up(self, mock_get_metadata):
        """Completing an upcoming anime should redirect to IN_PROGRESS + caught_up."""
        mock_get_metadata.return_value = {
            "max_progress": None,
            "is_ongoing": True,
        }

        self.anime.status = Status.COMPLETED.value
        self.anime.save()

        self.anime.refresh_from_db()
        self.assertEqual(self.anime.status, Status.IN_PROGRESS.value)
        self.assertTrue(self.anime.caught_up)
        self.assertEqual(self.anime.progress, 0)

    @patch("app.models.providers.services.get_media_metadata")
    def test_airing_anime_redirects_to_caught_up(self, mock_get_metadata):
        """Completing a currently airing anime should redirect to caught_up."""
        mock_get_metadata.return_value = {
            "max_progress": 12,
            "is_ongoing": True,
        }

        self.anime.status = Status.COMPLETED.value
        self.anime.save()

        self.anime.refresh_from_db()
        self.assertEqual(self.anime.status, Status.IN_PROGRESS.value)
        self.assertTrue(self.anime.caught_up)

    @patch("app.models.providers.services.get_media_metadata")
    def test_finished_anime_completes_normally(self, mock_get_metadata):
        """Completing a finished anime should set progress and stay completed."""
        mock_get_metadata.return_value = {
            "max_progress": 26,
            "is_ongoing": False,
        }

        self.anime.status = Status.COMPLETED.value
        self.anime.save()

        self.anime.refresh_from_db()
        self.assertEqual(self.anime.status, Status.COMPLETED.value)
        self.assertEqual(self.anime.progress, 26)
        self.assertFalse(self.anime.caught_up)

    @patch("app.models.providers.services.get_media_metadata")
    def test_stale_cache_fallback_uses_detail_status(self, mock_get_metadata):
        """Stale cache without is_ongoing should fall back to details.status."""
        mock_get_metadata.return_value = {
            "max_progress": None,
            "details": {"status": "Upcoming"},
        }

        self.anime.status = Status.COMPLETED.value
        self.anime.save()

        self.anime.refresh_from_db()
        self.assertEqual(self.anime.status, Status.IN_PROGRESS.value)
        self.assertTrue(self.anime.caught_up)


class MetadataPassthroughTests(TestCase):
    """Test that _metadata attribute skips API calls in save hooks."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="meta_pass", password="12345"
        )
        cls.item = Item.objects.create(
            media_id="900",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Test Anime",
            image="http://example.com/image.jpg",
        )

    def _make_anime(self, status=Status.IN_PROGRESS.value, progress=0):
        return Anime.objects.create(
            item=self.item,
            user=self.user,
            status=status,
            progress=progress,
        )

    @patch("app.models.providers.services.get_media_metadata")
    def test_process_progress_uses_metadata_when_set(self, mock_meta):
        """Pre-set _metadata prevents API call during progress change."""
        mock_meta.return_value = {"max_progress": 12}
        anime = self._make_anime(progress=5)
        mock_meta.reset_mock()

        anime._metadata = {"max_progress": 12}
        anime.progress = 6
        anime.save()

        mock_meta.assert_not_called()
        anime.refresh_from_db()
        self.assertEqual(anime.progress, 6)

    @patch("app.models.providers.services.get_media_metadata")
    def test_process_progress_falls_back_to_api(self, mock_meta):
        """Without _metadata, API is called on progress change."""
        mock_meta.return_value = {"max_progress": 12}
        anime = self._make_anime(progress=5)
        anime.progress = 6
        anime.save()

        mock_meta.assert_called()

    @patch("app.models.Item.fetch_releases")
    @patch("app.models.providers.services.get_media_metadata")
    def test_process_status_uses_metadata_when_set(self, mock_meta, _rel):
        """Pre-set _metadata prevents API call on status completion."""
        mock_meta.return_value = {"max_progress": 12}
        anime = self._make_anime(progress=5)
        mock_meta.reset_mock()

        anime._metadata = {"max_progress": 12, "is_ongoing": False}
        anime.status = Status.COMPLETED.value
        anime.save()

        mock_meta.assert_not_called()
        anime.refresh_from_db()
        self.assertEqual(anime.progress, 12)

    @patch("app.models.Item.fetch_releases")
    @patch("app.models.providers.services.get_media_metadata")
    def test_process_status_falls_back_to_api(self, mock_meta, _rel):
        """Without _metadata, API is called on status completion."""
        mock_meta.return_value = {"max_progress": 12, "is_ongoing": False}
        anime = self._make_anime(progress=5)
        anime.status = Status.COMPLETED.value
        anime.save()

        mock_meta.assert_called()

    @patch("app.models.Item.fetch_releases")
    def test_process_status_non_completed_skips_metadata(self, _rel):
        """Status change to non-COMPLETED doesn't need metadata at all."""
        anime = self._make_anime()
        anime.status = Status.PAUSED.value
        anime.save()

        anime.refresh_from_db()
        self.assertEqual(anime.status, Status.PAUSED.value)
