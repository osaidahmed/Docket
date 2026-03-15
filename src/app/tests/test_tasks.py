from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import Anime, Item, ItemRelationship, MediaTypes, Sources, Status

_IMG = "http://example.com/image.jpg"


class RefreshAnimeRelationshipsTaskTests(TestCase):
    """Test the refresh_anime_relationships_task Celery task."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="tasktest", password="12345"
        )

    def setUp(self):
        patcher = patch(
            "app.providers.services.get_media_metadata",
            return_value={"max_progress": None},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _make_anime(self, media_id):
        item = Item.objects.create(
            media_id=media_id,
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title=f"Anime {media_id}",
            image=_IMG,
        )
        return Anime.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

    @patch("time.sleep")
    @patch("app.providers.mal._save_anime_relationships")
    @patch("app.providers.mal.anime")
    def test_fetches_relationships_for_anime_without_existing(
        self, mock_anime, mock_save, mock_sleep
    ):
        a = self._make_anime("100")
        mock_anime.return_value = {
            "related": {"related_anime": [{"media_id": 200, "title": "Sequel"}]}
        }

        from app.tasks import refresh_anime_relationships_task

        refresh_anime_relationships_task(self.user.id)

        mock_anime.assert_called_once_with("100")
        mock_save.assert_called_once_with(
            "100", [{"media_id": 200, "title": "Sequel"}]
        )

    @patch("time.sleep")
    @patch("app.providers.mal._save_anime_relationships")
    @patch("app.providers.mal.anime")
    def test_skips_anime_with_existing_relationships(
        self, mock_anime, mock_save, mock_sleep
    ):
        a = self._make_anime("101")
        other_item = Item.objects.create(
            media_id="201",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Related",
            image=_IMG,
        )
        ItemRelationship.objects.create(
            from_item=a.item, to_item=other_item, relation_type="sequel"
        )

        from app.tasks import refresh_anime_relationships_task

        refresh_anime_relationships_task(self.user.id)

        mock_anime.assert_not_called()
        mock_save.assert_not_called()

    @patch("time.sleep")
    @patch("app.providers.mal.anime")
    def test_skips_on_exception(self, mock_anime, mock_sleep):
        self._make_anime("102")
        mock_anime.side_effect = RuntimeError("API error")

        from app.tasks import refresh_anime_relationships_task

        refresh_anime_relationships_task(self.user.id)
        mock_anime.assert_called_once()

    @patch("time.sleep")
    @patch("app.providers.mal.anime")
    def test_skips_when_no_related_anime(self, mock_anime, mock_sleep):
        self._make_anime("103")
        mock_anime.return_value = {"related": {"related_anime": []}}

        from app.tasks import refresh_anime_relationships_task

        refresh_anime_relationships_task(self.user.id)

        mock_anime.assert_called_once()

    @patch("time.sleep")
    @patch("app.providers.mal.anime")
    def test_no_tracked_anime_does_nothing(self, mock_anime, mock_sleep):
        from app.tasks import refresh_anime_relationships_task

        refresh_anime_relationships_task(self.user.id)

        mock_anime.assert_not_called()


class ComputeRecommendationsTaskTests(TestCase):
    """Test the compute_recommendations_task Celery task."""

    @patch("app.services.recommendations.compute_recommendations")
    def test_success_delegates_to_compute_recommendations(self, mock_compute):
        """Test that the task delegates to compute_recommendations on success."""
        from app.tasks import compute_recommendations_task

        compute_recommendations_task(user_id=1, media_type="anime")

        mock_compute.assert_called_once_with(1, "anime")

    @patch("app.services.recommendations.get_progress_key", return_value="prog:1:anime")
    @patch("app.services.recommendations.get_cache_key", return_value="recs:1:anime")
    @patch("django.core.cache.cache.delete")
    @patch("django.core.cache.cache.set")
    @patch("app.services.recommendations.compute_recommendations")
    def test_exception_caches_empty_result_and_deletes_progress(
        self,
        mock_compute,
        mock_cache_set,
        mock_cache_delete,
        mock_cache_key,
        mock_prog_key,
    ):
        """Test that on exception, empty result is cached and progress key deleted."""
        mock_compute.side_effect = RuntimeError("provider down")

        from app.tasks import compute_recommendations_task

        compute_recommendations_task(user_id=1, media_type="anime")

        mock_cache_set.assert_called_once()
        args, _kwargs = mock_cache_set.call_args
        self.assertEqual(args[0], "recs:1:anime")
        self.assertEqual(args[1], {"active": [], "full": [], "genres": []})

        mock_cache_delete.assert_called_once_with("prog:1:anime")
