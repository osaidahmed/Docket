import json

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
from app.templatetags import app_tags


class MediaListViewTests(TestCase):
    """Test the media list view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

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
                user=cls.user,
                status=status,
                progress=1 if i < num_completed else 0,
                score=i,
            )

    def setUp(self):
        self.client.login(**self.credentials)

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

        self.user.refresh_from_db()
        self.assertEqual(self.user.movie_status, Status.COMPLETED.value)
        self.assertEqual(self.user.movie_sort, "score")
        self.assertEqual(self.user.movie_layout, "table")

    def test_dropped_items_appear_in_media_list(self):
        """Test that dropped items appear when filtering by Dropped status."""
        dropped_item = Item.objects.create(
            media_id="999",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Dropped Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=dropped_item,
            user=self.user,
            status=Status.DROPPED.value,
        )

        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value]) + "?status=Dropped",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["current_status"],
            Status.DROPPED.value,
        )
        self.assertEqual(response.context["media_list"].paginator.count, 1)
        self.assertContains(response, "Dropped Movie")

    def test_dropped_items_appear_in_htmx_partial(self):
        """Test that dropped items appear in HTMX partial responses."""
        dropped_item = Item.objects.create(
            media_id="998",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="HTMX Dropped Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=dropped_item,
            user=self.user,
            status=Status.DROPPED.value,
        )

        headers = {"HTTP_HX_REQUEST": "true", "HTTP_HX_TARGET": "media-cards-list"}
        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value])
            + "?status=Dropped&layout=cards",
            **headers,
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/media_cards_items.html")
        self.assertContains(response, "HTMX Dropped Movie")

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

    def test_table_view_shows_english_title(self):
        """Test that the table layout displays english_title when present."""
        item = Item.objects.create(
            media_id="999",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Shingeki no Kyojin",
            english_title="Attack on Titan",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=0,
        )

        response = self.client.get(
            reverse("medialist", args=[MediaTypes.ANIME.value]) + "?layout=table",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Attack on Titan")


class QuickUntrackTests(TestCase):
    """Test the quick_untrack action."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def test_quick_untrack_deletes_media(self):
        """Test that quick_untrack deletes the media entry."""
        item = Item.objects.create(
            media_id="777",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Movie to Untrack",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.DROPPED.value,
        )

        response = self.client.post(
            reverse("quick_untrack"),
            {"media_type": MediaTypes.MOVIE.value, "instance_id": movie.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Movie.objects.filter(id=movie.id).exists())

    def test_quick_untrack_renders_banner(self):
        """Test that quick_untrack renders the untracked banner template."""
        item = Item.objects.create(
            media_id="776",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Another Untrack Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.DROPPED.value,
        )

        response = self.client.post(
            reverse("quick_untrack"),
            {"media_type": MediaTypes.MOVIE.value, "instance_id": movie.id},
        )

        self.assertTemplateUsed(response, "app/components/backlog_untracked.html")
        self.assertContains(response, "Untracked")


class InlineStarRatingTests(TestCase):
    """Test that the inline star rating popup renders across all layouts."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test_star", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.scored_item = Item.objects.create(
            media_id="5001",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Scored Movie",
            image="http://example.com/image.jpg",
        )
        cls.scored_movie = Movie.objects.create(
            item=cls.scored_item,
            user=cls.user,
            status=Status.COMPLETED.value,
            score=8,
        )

        cls.unscored_item = Item.objects.create(
            media_id="5002",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Unscored Movie",
            image="http://example.com/image.jpg",
        )
        cls.unscored_movie = Movie.objects.create(
            item=cls.unscored_item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
        )

    def setUp(self):
        self.client.login(**self.credentials)

    def test_cards_layout_has_star_rating_trigger(self):
        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value]) + "?layout=cards",
        )
        self.assertContains(response, "Click to rate")
        self.assertContains(response, "update-score/movie/")

    def test_cards_layout_shows_score_in_alpine_state(self):
        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value]) + "?layout=cards",
        )
        self.assertContains(response, f"rating: {self.scored_movie.score}")

    def test_cards_layout_shows_null_for_unscored(self):
        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value]) + "?layout=cards",
        )
        self.assertContains(response, "rating: null")

    def test_table_layout_has_star_rating_trigger(self):
        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value]) + "?layout=table",
        )
        self.assertContains(response, "Click to rate")
        self.assertContains(response, "update-score/movie/")

    def test_table_layout_shows_score_in_alpine_state(self):
        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value]) + "?layout=table",
        )
        self.assertContains(response, f"rating: {self.scored_movie.score}")

    def test_table_layout_shows_null_for_unscored(self):
        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value]) + "?layout=table",
        )
        self.assertContains(response, "rating: null")

    def test_edit_form_score_uses_x_model(self):
        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value]) + "?layout=cards",
        )
        self.assertContains(response, 'x-model="rating"')


class InlineStarRatingPinnedTests(TestCase):
    """Test that pinned items in table layout have the interactive star rating."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test_pin_star", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.pinned_item = Item.objects.create(
            media_id="6001",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Pinned Movie",
            image="http://example.com/image.jpg",
        )
        cls.pinned_movie = Movie.objects.create(
            item=cls.pinned_item,
            user=cls.user,
            status=Status.PLANNING.value,
            score=7,
            pin_order=0,
        )

        cls.pinned_unscored_item = Item.objects.create(
            media_id="6002",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Pinned Unscored Movie",
            image="http://example.com/image.jpg",
        )
        cls.pinned_unscored_movie = Movie.objects.create(
            item=cls.pinned_unscored_item,
            user=cls.user,
            status=Status.PLANNING.value,
            pin_order=1,
        )

    def setUp(self):
        self.client.login(**self.credentials)

    def test_pinned_table_has_star_rating_trigger(self):
        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value])
            + "?layout=table&status=Planning",
        )
        self.assertContains(response, "Click to rate")
        self.assertContains(
            response,
            f"update-score/movie/{self.pinned_movie.id}",
        )

    def test_pinned_table_shows_score_in_alpine_state(self):
        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value])
            + "?layout=table&status=Planning",
        )
        self.assertContains(response, f"rating: {self.pinned_movie.score}")

    def test_pinned_table_shows_null_for_unscored(self):
        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value])
            + "?layout=table&status=Planning",
        )
        self.assertContains(response, "rating: null")

    def test_pinned_cards_has_star_rating_trigger(self):
        response = self.client.get(
            reverse("medialist", args=[MediaTypes.MOVIE.value])
            + "?layout=cards&status=Planning",
        )
        self.assertContains(response, "Click to rate")
        self.assertContains(
            response,
            f"update-score/movie/{self.pinned_movie.id}",
        )


class UpdateMediaScoreTests(TestCase):
    """Test the update_media_score endpoint used by the inline star rating."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test_score", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.item = Item.objects.create(
            media_id="7001",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.MOVIE.value,
            title="Score Test Movie",
            image="http://example.com/image.jpg",
        )
        cls.movie = Movie.objects.create(
            item=cls.item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
        )

    def setUp(self):
        self.client.login(**self.credentials)

    def test_update_score_returns_json(self):
        response = self.client.post(
            reverse(
                "update_media_score",
                args=[MediaTypes.MOVIE.value, self.movie.id],
            ),
            {"score": 9},
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertTrue(data["success"])
        self.assertEqual(data["score"], 9.0)

    def test_update_score_persists(self):
        self.client.post(
            reverse(
                "update_media_score",
                args=[MediaTypes.MOVIE.value, self.movie.id],
            ),
            {"score": 6},
        )
        self.movie.refresh_from_db()
        self.assertEqual(float(self.movie.score), 6.0)

    def test_update_score_decimal(self):
        self.client.post(
            reverse(
                "update_media_score",
                args=[MediaTypes.MOVIE.value, self.movie.id],
            ),
            {"score": 7.5},
        )
        self.movie.refresh_from_db()
        self.assertEqual(float(self.movie.score), 7.5)

    def test_update_score_rejects_get(self):
        response = self.client.get(
            reverse(
                "update_media_score",
                args=[MediaTypes.MOVIE.value, self.movie.id],
            ),
        )
        self.assertEqual(response.status_code, 405)

    def test_update_score_requires_auth(self):
        self.client.logout()
        response = self.client.post(
            reverse(
                "update_media_score",
                args=[MediaTypes.MOVIE.value, self.movie.id],
            ),
            {"score": 5},
        )
        self.assertNotEqual(response.status_code, 200)
