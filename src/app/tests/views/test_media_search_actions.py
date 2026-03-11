from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from app.models import (
    Anime,
    Item,
    MediaTypes,
    Movie,
    Sources,
    Status,
)
from app.services import recent


class QuickCompleteViewTests(TestCase):
    """Test the quick_complete view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)
        cls.item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Test Anime",
            image="http://example.com/image.jpg",
        )
        cls.anime = Anime.objects.create(
            item=cls.item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
        )

    def setUp(self):
        self.client.login(**self.credentials)

    def test_quick_complete_marks_completed(self):
        response = self.client.post(
            reverse("quick_complete"),
            {
                "media_type": MediaTypes.ANIME.value,
                "instance_id": str(self.anime.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.anime.refresh_from_db()
        self.assertEqual(self.anime.status, Status.COMPLETED.value)

    def test_quick_complete_returns_confirmation_with_archive(self):
        response = self.client.post(
            reverse("quick_complete"),
            {
                "media_type": MediaTypes.ANIME.value,
                "instance_id": str(self.anime.id),
            },
        )

        self.assertTemplateUsed(response, "app/components/backlog_completed.html")
        self.assertTemplateUsed(response, "app/components/backlog_card_archived.html")
        self.assertContains(response, "hx-swap-oob")

    def test_quick_complete_updates_archive_count(self):
        response = self.client.post(
            reverse("quick_complete"),
            {
                "media_type": MediaTypes.ANIME.value,
                "instance_id": str(self.anime.id),
            },
        )

        content = response.content.decode()
        self.assertIn('id="archive-count"', content)
        self.assertIn("(1)", content)

    def test_quick_complete_archive_count_deduplicates_rewatches(self):
        self.anime.status = Status.COMPLETED.value
        self.anime.save()

        rewatch = Anime.objects.create(
            item=self.item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        response = self.client.post(
            reverse("quick_complete"),
            {
                "media_type": MediaTypes.ANIME.value,
                "instance_id": str(rewatch.id),
            },
        )

        content = response.content.decode()
        self.assertIn("(1)", content)
        self.assertNotIn("(2)", content)


class BacklogSaveViewTests(TestCase):
    """Test the backlog_save view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)
        cls.item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Test Anime",
            image="http://example.com/image.jpg",
        )
        cls.anime = Anime.objects.create(
            item=cls.item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
            progress=5,
        )

    def setUp(self):
        self.client.login(**self.credentials)

    def test_backlog_save_updates_fields(self):
        response = self.client.post(
            reverse("backlog_save"),
            {
                "media_id": "1",
                "source": Sources.MAL.value,
                "media_type": MediaTypes.ANIME.value,
                "instance_id": str(self.anime.id),
                "score": "8.5",
                "progress": "10",
                "status": Status.IN_PROGRESS.value,
                "start_date": "",
                "end_date": "",
                "link": "https://example.com",
                "notes": "Good show",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/backlog_card.html")
        self.anime.refresh_from_db()
        self.assertEqual(float(self.anime.score), 8.5)
        self.assertEqual(self.anime.progress, 10)
        self.assertEqual(self.anime.link, "https://example.com")
        self.assertEqual(self.anime.notes, "Good show")

    def test_backlog_save_requires_post(self):
        response = self.client.get(reverse("backlog_save"))
        self.assertEqual(response.status_code, 405)

    def test_backlog_save_validation_error(self):
        response = self.client.post(
            reverse("backlog_save"),
            {
                "media_id": "1",
                "source": Sources.MAL.value,
                "media_type": MediaTypes.ANIME.value,
                "instance_id": str(self.anime.id),
                "score": "15",
                "progress": "5",
                "status": Status.IN_PROGRESS.value,
                "start_date": "",
                "end_date": "",
                "link": "",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("form_errors", response.context)
        self.assertTrue(response.context["show_edit"])

    @patch("app.providers.services.get_media_metadata")
    def test_unflag_rewatch_deletes_planning_instance(self, mock_metadata):
        mock_metadata.return_value = {"max_progress": None}
        Anime.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
        )
        rewatch = Anime.objects.create(
            item=self.item,
            user=self.user,
            status=Status.PLANNING.value,
            is_rewatch=True,
        )

        response = self.client.post(
            reverse("backlog_save"),
            {
                "media_id": "1",
                "source": Sources.MAL.value,
                "media_type": MediaTypes.ANIME.value,
                "instance_id": str(rewatch.id),
                "score": "",
                "progress": "0",
                "status": Status.PLANNING.value,
                "start_date": "",
                "end_date": "",
                "link": "",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Anime.objects.filter(id=rewatch.id).exists())
        self.assertTrue("HX-Refresh" in response)


class QuickRewatchViewTests(TestCase):
    """Test the quick_rewatch view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)
        cls.item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )

    def setUp(self):
        self.client.login(**self.credentials)

    @patch("app.providers.services.get_media_metadata")
    def test_quick_rewatch_creates_planning_instance(self, mock_metadata):
        mock_metadata.return_value = {"max_progress": None}
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
        )

        response = self.client.post(
            reverse("quick_rewatch"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        self.assertEqual(response.status_code, 200)
        movies = Movie.objects.filter(item=self.item, user=self.user)
        self.assertEqual(movies.count(), 2)
        newest = movies.order_by("-created_at").first()
        self.assertEqual(newest.status, Status.PLANNING.value)

    @patch("app.providers.services.get_media_metadata")
    def test_quick_rewatch_returns_completed_with_has_active(self, mock_metadata):
        mock_metadata.return_value = {"max_progress": None}
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
        )

        response = self.client.post(
            reverse("quick_rewatch"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        self.assertTemplateUsed(response, "app/components/search_action.html")
        self.assertEqual(response.context["media"].status, Status.COMPLETED.value)
        self.assertTrue(response.context["has_active"])

        content = response.content.decode()
        self.assertIn("Completed", content)
        self.assertNotIn("Rewatch", content)
        self.assertNotIn("quick_rewatch", content)
        self.assertNotIn("Planning", content)

    def test_quick_rewatch_prevents_duplicate_active(self):
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.post(
            reverse("quick_rewatch"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Movie.objects.filter(item=self.item, user=self.user).count(),
            1,
        )

    @patch("app.providers.services.get_media_metadata")
    def test_quick_rewatch_archive_context(self, mock_metadata):
        mock_metadata.return_value = {"max_progress": None}
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
        )

        response = self.client.post(
            reverse("quick_rewatch"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
                "source_context": "archive",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "app/components/backlog_rewatch_confirmed.html"
        )


@override_settings(REDIS_PREFIX=None)
class RecentlyViewedSuggestTests(TestCase):
    """Test the search_suggest_recent view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)
        recent.redis_client.flushdb()

    def test_recently_viewed_returns_results(self):
        recent.track_view(
            self.user.id,
            {
                "media_type": MediaTypes.MOVIE.value,
                "media_id": "238",
                "source": Sources.TMDB.value,
                "title": "Test Movie",
                "english_title": "",
                "image": "http://example.com/img.jpg",
            },
        )

        response = self.client.get(
            reverse("search_suggest_recent") + "?type=all",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/search_suggest_local.html")
        self.assertEqual(len(response.context["results"]), 1)
        self.assertEqual(response.context["results"][0]["title"], "Test Movie")

    def test_recently_viewed_empty_returns_empty_template(self):
        response = self.client.get(
            reverse("search_suggest_recent") + "?type=all",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content.decode().strip(), "")

    def test_recently_viewed_respects_type_filter(self):
        recent.track_view(
            self.user.id,
            {
                "media_type": MediaTypes.MOVIE.value,
                "media_id": "1",
                "source": Sources.TMDB.value,
                "title": "A Movie",
                "english_title": "",
                "image": "http://example.com/img.jpg",
            },
        )
        recent.track_view(
            self.user.id,
            {
                "media_type": MediaTypes.ANIME.value,
                "media_id": "2",
                "source": Sources.MAL.value,
                "title": "An Anime",
                "english_title": "",
                "image": "http://example.com/img.jpg",
            },
        )

        response = self.client.get(
            reverse("search_suggest_recent") + "?type=anime",
        )

        self.assertEqual(len(response.context["results"]), 1)
        self.assertEqual(response.context["results"][0]["media_type"], "anime")

    def test_recently_viewed_type_all_returns_all(self):
        recent.track_view(
            self.user.id,
            {
                "media_type": MediaTypes.MOVIE.value,
                "media_id": "1",
                "source": Sources.TMDB.value,
                "title": "A Movie",
                "english_title": "",
                "image": "http://example.com/img.jpg",
            },
        )
        recent.track_view(
            self.user.id,
            {
                "media_type": MediaTypes.ANIME.value,
                "media_id": "2",
                "source": Sources.MAL.value,
                "title": "An Anime",
                "english_title": "",
                "image": "http://example.com/img.jpg",
            },
        )

        response = self.client.get(
            reverse("search_suggest_recent") + "?type=all",
        )

        self.assertEqual(len(response.context["results"]), 2)

    def test_recently_viewed_requires_auth(self):
        self.client.logout()

        response = self.client.get(
            reverse("search_suggest_recent") + "?type=all",
        )

        self.assertEqual(response.status_code, 302)

    def test_recently_viewed_section_title(self):
        recent.track_view(
            self.user.id,
            {
                "media_type": MediaTypes.MOVIE.value,
                "media_id": "1",
                "source": Sources.TMDB.value,
                "title": "Test",
                "english_title": "",
                "image": "http://example.com/img.jpg",
            },
        )

        response = self.client.get(
            reverse("search_suggest_recent") + "?type=all",
        )

        self.assertContains(response, "Recently Viewed")
