from unittest.mock import patch

from django.test import TestCase


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
        self, mock_compute, mock_cache_set, mock_cache_delete, mock_cache_key, mock_prog_key
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
