from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import (
    Anime,
    Item,
    MediaTypes,
    Movie,
    Sources,
    Status,
)


class BacklogSaveTests(TestCase):
    """Test the backlog_save view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def _backlog_save_data(self, media, source_context=None):
        """Build POST data for backlog_save from a media instance."""
        data = {
            "media_id": media.item.media_id,
            "source": media.item.source,
            "media_type": media.item.media_type,
            "instance_id": media.id,
            "score": "",
            "status": media.status,
            "start_date": "",
            "end_date": "",
            "notes": "",
            "link": "",
        }
        # Include progress only for types that have it on the form
        if media.item.media_type not in (MediaTypes.MOVIE.value,):
            data["progress"] = media.progress if media.progress is not None else ""
        if source_context:
            data["source_context"] = source_context
        return data

    def _make_movie(self, media_id, title, status, **kwargs):
        item = Item.objects.create(
            media_id=media_id,
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title=title,
            image="http://example.com/image.jpg",
        )
        return Movie.objects.create(item=item, user=self.user, status=status, **kwargs)

    def _make_anime(self, media_id, title, status, **kwargs):
        item = Item.objects.create(
            media_id=media_id,
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title=title,
            image="http://example.com/image.jpg",
        )
        return Anime.objects.create(item=item, user=self.user, status=status, **kwargs)

    # --- Valid form, default context (backlog) ---

    def test_valid_form_returns_200_backlog_card(self):
        """POST with valid form data returns 200 and renders backlog card."""
        movie = self._make_movie("100", "Backlog Movie", Status.PLANNING.value)
        data = self._backlog_save_data(movie)

        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/backlog_card.html")

    def test_valid_form_archive_context_renders_archive_card(self):
        """POST with source_context=archive renders the archive card template."""
        movie = self._make_movie("101", "Archive Movie", Status.COMPLETED.value)
        data = self._backlog_save_data(movie, source_context="archive")

        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/backlog_card_archived.html")

    @patch("app.providers.services.get_media_metadata")
    def test_valid_form_medialist_context_renders_medialist_card(self, mock_metadata):
        """POST with source_context=medialist renders media list card."""
        mock_metadata.return_value = {"max_progress": None}
        anime = self._make_anime(
            "102", "List Anime", Status.IN_PROGRESS.value, progress=5
        )
        data = self._backlog_save_data(anime, source_context="medialist")

        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/media_list_card.html")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_status_completed_renders_completed_card(
        self, mock_releases, mock_metadata
    ):
        """Changing status to COMPLETED renders the completed card template."""
        mock_metadata.return_value = {"max_progress": None}
        movie = self._make_movie("103", "Complete Movie", Status.IN_PROGRESS.value)
        data = self._backlog_save_data(movie)
        data["status"] = Status.COMPLETED.value

        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/backlog_completed.html")

    @patch("app.models.Item.fetch_releases")
    def test_status_dropped_renders_dropped_card_with_refresh(self, mock_releases):
        """Changing status to DROPPED renders dropped card."""
        movie = self._make_movie("104", "Drop Movie", Status.IN_PROGRESS.value)
        data = self._backlog_save_data(movie)
        data["status"] = Status.DROPPED.value

        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/backlog_dropped.html")

    # --- Invalid form ---

    def test_invalid_form_score_out_of_range_shows_errors(self):
        """Invalid form (score > 10) returns form_errors in backlog card."""
        movie = self._make_movie("105", "Bad Score Movie", Status.PLANNING.value)
        data = self._backlog_save_data(movie)
        data["score"] = "15"

        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/backlog_card.html")
        self.assertIn("form_errors", response.context)
        self.assertTrue(response.context["show_edit"])

    def test_invalid_form_medialist_context_shows_errors(self):
        """Invalid form with source_context=medialist renders medialist error."""
        anime = self._make_anime(
            "106", "Bad Score Anime", Status.IN_PROGRESS.value, progress=5
        )
        data = self._backlog_save_data(anime, source_context="medialist")
        data["score"] = "15"

        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/media_list_card.html")
        self.assertIn("form_errors", response.context)
        self.assertTrue(response.context["show_edit"])

    def test_invalid_form_archive_context_shows_errors(self):
        """Invalid form with source_context=archive renders archive error."""
        movie = self._make_movie("107", "Bad Archive Movie", Status.COMPLETED.value)
        data = self._backlog_save_data(movie, source_context="archive")
        data["score"] = "15"

        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/backlog_card_archived.html")
        self.assertIn("form_errors", response.context)
        self.assertTrue(response.context["show_edit"])


class PinOrderTests(TestCase):
    """Test pin_order handling in backlog_save."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def _backlog_save_data(self, media):
        data = {
            "media_id": media.item.media_id,
            "source": media.item.source,
            "media_type": media.item.media_type,
            "instance_id": media.id,
            "score": "",
            "status": media.status,
            "start_date": "",
            "end_date": "",
            "notes": "",
            "link": "",
        }
        if media.item.media_type not in (MediaTypes.MOVIE.value,):
            data["progress"] = media.progress if media.progress is not None else ""
        return data

    def test_newly_pinned_gets_pin_order(self):
        """Submitting is_pinned when not previously pinned sets pin_order."""
        item = Item.objects.create(
            media_id="200",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Pin Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )
        self.assertIsNone(movie.pin_order)

        data = self._backlog_save_data(movie)
        data["is_pinned"] = "on"

        self.client.post(reverse("backlog_save"), data)

        movie.refresh_from_db()
        self.assertIsNotNone(movie.pin_order)
        self.assertEqual(movie.pin_order, 0)

    def test_newly_pinned_increments_max_order(self):
        """Pin order is set to max existing + 1 when other pins exist."""
        item1 = Item.objects.create(
            media_id="201",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Existing Pinned",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=item1,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=3,
        )

        item2 = Item.objects.create(
            media_id="202",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="New Pin Movie",
            image="http://example.com/image.jpg",
        )
        movie2 = Movie.objects.create(
            item=item2, user=self.user, status=Status.PLANNING.value
        )

        data = self._backlog_save_data(movie2)
        data["is_pinned"] = "on"

        self.client.post(reverse("backlog_save"), data)

        movie2.refresh_from_db()
        self.assertEqual(movie2.pin_order, 4)

    def test_unpinned_clears_pin_order(self):
        """Not submitting is_pinned when previously pinned sets pin_order to None."""
        item = Item.objects.create(
            media_id="203",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Unpin Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=5,
        )
        self.assertTrue(movie.is_pinned)

        data = self._backlog_save_data(movie)
        # is_pinned absent means unchecked

        self.client.post(reverse("backlog_save"), data)

        movie.refresh_from_db()
        self.assertIsNone(movie.pin_order)
        self.assertFalse(movie.is_pinned)


class RewatchCancellationTests(TestCase):
    """Test rewatch cancellation logic in backlog_save."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def _backlog_save_data(self, media):
        data = {
            "media_id": media.item.media_id,
            "source": media.item.source,
            "media_type": media.item.media_type,
            "instance_id": media.id,
            "score": "",
            "status": media.status,
            "start_date": "",
            "end_date": "",
            "notes": "",
            "link": "",
        }
        if media.item.media_type not in (MediaTypes.MOVIE.value,):
            data["progress"] = media.progress if media.progress is not None else ""
        return data

    @patch("app.models.Item.fetch_releases")
    def test_rewatch_cancelled_with_finished_entry_deletes_media(self, mock_releases):
        """Unchecking is_rewatch on a Planning rewatch with a finished entry deletes it."""
        item = Item.objects.create(
            media_id="300",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Rewatch Cancel Movie",
            image="http://example.com/image.jpg",
        )
        # The finished (completed) entry
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)
        # The rewatch entry (Planning + is_rewatch=True)
        rewatch = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
            is_rewatch=True,
        )

        data = self._backlog_save_data(rewatch)
        # is_rewatch absent = unchecked, status stays Planning

        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Movie.objects.filter(id=rewatch.id).exists(),
            "Rewatch entry should be deleted when cancelled with a finished entry",
        )

    def test_rewatch_cancelled_without_finished_entry_keeps_media(self):
        """Unchecking is_rewatch with no finished entry does not delete media."""
        item = Item.objects.create(
            media_id="301",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Rewatch Keep Movie",
            image="http://example.com/image.jpg",
        )
        # Only the rewatch entry, no completed/dropped sibling
        rewatch = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
            is_rewatch=True,
        )

        data = self._backlog_save_data(rewatch)
        # is_rewatch absent = unchecked

        self.client.post(reverse("backlog_save"), data)

        self.assertTrue(
            Movie.objects.filter(id=rewatch.id).exists(),
            "Media should not be deleted when no finished entry exists",
        )
        rewatch.refresh_from_db()
        self.assertFalse(rewatch.is_rewatch)


class BulkActionTests(TestCase):
    """Test the bulk_action view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def _make_movies(self, count=3, status=Status.PLANNING.value):
        """Create multiple movies and return the list of Movie instances."""
        movies = []
        for i in range(count):
            item = Item.objects.create(
                media_id=str(400 + i),
                source=Sources.TMDB.value,
                media_type=MediaTypes.MOVIE.value,
                title=f"Bulk Movie {i}",
                image="http://example.com/image.jpg",
            )
            movie = Movie.objects.create(item=item, user=self.user, status=status)
            movies.append(movie)
        return movies

    @patch("app.models.Item.fetch_releases")
    def test_bulk_status_change(self, mock_releases):
        """Bulk status change updates all items and returns HX-Refresh."""
        movies = self._make_movies()
        ids = ",".join(str(m.id) for m in movies)

        response = self.client.post(
            reverse("bulk_action"),
            {
                "media_type": "movie",
                "instance_ids": ids,
                "action": "status",
                "value": Status.IN_PROGRESS.value,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Refresh"], "true")
        for m in movies:
            m.refresh_from_db()
            self.assertEqual(m.status, Status.IN_PROGRESS.value)

    def test_bulk_score_change(self):
        """Bulk score change sets score on all items."""
        movies = self._make_movies()
        ids = ",".join(str(m.id) for m in movies)

        response = self.client.post(
            reverse("bulk_action"),
            {
                "media_type": "movie",
                "instance_ids": ids,
                "action": "score",
                "value": "7.5",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Refresh"], "true")
        for m in movies:
            m.refresh_from_db()
            self.assertEqual(m.score, Decimal("7.5"))

    def test_bulk_delete(self):
        """Bulk delete removes all selected items."""
        movies = self._make_movies()
        ids = ",".join(str(m.id) for m in movies)

        response = self.client.post(
            reverse("bulk_action"),
            {
                "media_type": "movie",
                "instance_ids": ids,
                "action": "delete",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Refresh"], "true")
        self.assertEqual(Movie.objects.filter(id__in=[m.id for m in movies]).count(), 0)

    def test_invalid_action_returns_400(self):
        """An unrecognized action returns 400."""
        movies = self._make_movies(1)
        ids = str(movies[0].id)

        response = self.client.post(
            reverse("bulk_action"),
            {
                "media_type": "movie",
                "instance_ids": ids,
                "action": "invalid_action",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_no_instance_ids_returns_400(self):
        """Missing instance_ids returns 400."""
        response = self.client.post(
            reverse("bulk_action"),
            {
                "media_type": "movie",
                "instance_ids": "",
                "action": "status",
                "value": Status.COMPLETED.value,
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_invalid_score_non_numeric_returns_400(self):
        """Non-numeric score value returns 400."""
        movies = self._make_movies(1)
        ids = str(movies[0].id)

        response = self.client.post(
            reverse("bulk_action"),
            {
                "media_type": "movie",
                "instance_ids": ids,
                "action": "score",
                "value": "abc",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_score_out_of_range_returns_400(self):
        """Score > 10 returns 400."""
        movies = self._make_movies(1)
        ids = str(movies[0].id)

        response = self.client.post(
            reverse("bulk_action"),
            {
                "media_type": "movie",
                "instance_ids": ids,
                "action": "score",
                "value": "11",
            },
        )

        self.assertEqual(response.status_code, 400)

    @patch("app.models.Item.fetch_releases")
    def test_status_change_to_in_progress_sets_start_date(self, mock_releases):
        """Bulk status change to IN_PROGRESS sets start_date on items without one."""
        movies = self._make_movies(2)
        ids = ",".join(str(m.id) for m in movies)

        response = self.client.post(
            reverse("bulk_action"),
            {
                "media_type": "movie",
                "instance_ids": ids,
                "action": "status",
                "value": Status.IN_PROGRESS.value,
            },
        )

        self.assertEqual(response.status_code, 200)
        for m in movies:
            m.refresh_from_db()
            self.assertIsNotNone(m.start_date)
            self.assertEqual(m.status, Status.IN_PROGRESS.value)

    def test_bulk_score_clear_sets_none(self):
        """Bulk score with empty value clears score."""
        movies = self._make_movies(1, status=Status.PLANNING.value)
        movies[0].score = Decimal(5)
        movies[0].save(update_fields=["score"])
        ids = str(movies[0].id)

        response = self.client.post(
            reverse("bulk_action"),
            {
                "media_type": "movie",
                "instance_ids": ids,
                "action": "score",
                "value": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        movies[0].refresh_from_db()
        self.assertIsNone(movies[0].score)

    def test_invalid_status_value_returns_400(self):
        """Bulk status with an invalid status value returns 400."""
        movies = self._make_movies(1)
        ids = str(movies[0].id)

        response = self.client.post(
            reverse("bulk_action"),
            {
                "media_type": "movie",
                "instance_ids": ids,
                "action": "status",
                "value": "NotAStatus",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_negative_score_returns_400(self):
        """Score < 0 returns 400."""
        movies = self._make_movies(1)
        ids = str(movies[0].id)

        response = self.client.post(
            reverse("bulk_action"),
            {
                "media_type": "movie",
                "instance_ids": ids,
                "action": "score",
                "value": "-1",
            },
        )

        self.assertEqual(response.status_code, 400)
