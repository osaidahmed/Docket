from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import (
    Item,
    MediaTypes,
    Movie,
    Sources,
    Status,
)
from app.templatetags import app_tags


class MediaListViewTests(TestCase):
    """Test the media list view."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

        movies_id = ["278", "238", "129", "424", "680"]
        num_completed = 3
        for i in range(1, 6):
            item = Item.objects.create(
                media_id=movies_id[i - 1],
                source=Sources.TMDB.value,
                media_type=MediaTypes.MOVIE.value,
                title=f"Test Movie {i}",
                image="http://example.com/image.jpg",
            )
            status = (
                Status.COMPLETED.value
                if i < num_completed
                else Status.IN_PROGRESS.value
            )
            Movie.objects.create(
                item=item,
                user=self.user,
                status=status,
                progress=1 if i < num_completed else 0,
                score=i,
            )

    def test_media_list_view(self):
        """Test the media list view displays media items."""
        response = self.client.get(reverse("medialist", args=[MediaTypes.MOVIE.value]))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/media_list.html")

        self.assertIn("media_list", response.context)
        self.assertEqual(response.context["media_list"].paginator.count, 5)

        self.assertIn("sort_choices", response.context)
        self.assertIn("status_choices", response.context)
        self.assertEqual(response.context["media_type"], MediaTypes.MOVIE.value)
        self.assertEqual(
            response.context["media_type_plural"],
            app_tags.media_type_readable_plural(MediaTypes.MOVIE.value).lower(),
        )

    def test_media_list_with_filters(self):
        """Test the media list view with filters."""
        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value])
            + "?status=Completed&sort=score&layout=table",
        )

        self.assertEqual(response.status_code, 200)

        self.assertEqual(
            response.context["current_status"],
            Status.COMPLETED.value,
        )
        self.assertEqual(response.context["current_sort"], "score")
        self.assertEqual(response.context["current_layout"], "table")

        self.assertEqual(response.context["media_list"].paginator.count, 2)

        pref = self.user.media_preferences.get(media_type=MediaTypes.MOVIE.value)
        self.assertEqual(pref.status_filter, Status.COMPLETED.value)
        self.assertEqual(pref.sort, "score")
        self.assertEqual(pref.layout, "table")

    def test_media_list_htmx_request(self):
        """Test the media list view with HTMX request."""
        headers = {"HTTP_HX_REQUEST": "true"}

        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value]) + "?layout=grid",
            **headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/media_grid_items.html")

        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value]) + "?layout=table",
            **headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/media_table_items.html")

    def test_media_list_htmx_empty_list_redirect(self):
        headers = {
            "HTTP_HX_REQUEST": "true",
            "HTTP_HX_TARGET": "empty_list",
        }
        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value]) + "?status=Completed",
            **headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["HX-Redirect"],
            reverse("medialist", args=[MediaTypes.MOVIE.value]),
        )

    def test_media_list_htmx_planning_page1_redirect(self):
        headers = {"HTTP_HX_REQUEST": "true"}
        url = (
            reverse("medialist", args=[MediaTypes.MOVIE.value])
            + "?status=Planning&page=1"
        )
        response = self.client.get(url, **headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn("HX-Redirect", response)

    def test_media_list_default_status_filter(self):
        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value]),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_status"], "All")


class RecommendationsSectionViewTests(TestCase):
    """Test the recommendations_section view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "recs_test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)
        self.url = reverse(
            "recommendations_section",
            kwargs={"media_type": MediaTypes.MOVIE.value},
        )

    def test_unsupported_type_returns_empty(self):
        url = reverse(
            "recommendations_section",
            kwargs={"media_type": MediaTypes.BOARDGAME.value},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"")

    @patch("app.services.recommendations.get_cache_key", return_value="test_recs_key")
    def test_cache_hit_renders_recommendations(self, _mock_key):
        from django.core.cache import cache

        cache.set("test_recs_key", {"active": [], "full": [], "genres": []}, timeout=30)
        self.addCleanup(cache.delete, "test_recs_key")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/recommendations_section.html")

    @patch("app.tasks.compute_recommendations_task.delay")
    @patch("app.views.home.recs_service.get_progress", return_value=None)
    def test_cache_miss_dispatches_task(self, _progress, mock_delay):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "app/components/recommendations_progress.html"
        )
        mock_delay.assert_called_once()

    @patch("app.views.home.recs_service.get_progress")
    def test_in_progress_renders_progress_bar(self, mock_progress):
        mock_progress.return_value = {"current": 5, "total": 10}
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "app/components/recommendations_progress.html"
        )
        self.assertEqual(response.context["progress_pct"], 50)
