from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import Anime, Item, MediaTypes, Movie, Sources, Status
from app.tests.views.test_home import _flatten_group_titles


class BacklogActionTests(TestCase):
    """Tests for quick actions and backlog_save on backlog cards."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def _backlog_save_data(self, media):
        return {
            "media_id": media.item.media_id,
            "source": media.item.source,
            "media_type": media.item.media_type,
            "instance_id": media.id,
            "score": "",
            "progress": media.progress if media.progress is not None else "",
            "status": media.status,
            "start_date": "",
            "end_date": "",
            "notes": "",
            "link": "",
        }

    def test_planning_item_no_done_button(self):
        """Test that Planning items don't show a Done button."""
        movie_item = Item.objects.create(
            media_id="400",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Planning Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.get(reverse("home") + "?type=movie")
        self.assertNotContains(response, "quick_complete")

    def test_quick_drop(self):
        """Test that quick_drop sets status to Dropped and removes card."""
        movie_item = Item.objects.create(
            media_id="401",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Movie To Drop",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.post(
            reverse("quick_drop"),
            {"media_type": "movie", "instance_id": movie.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dropped")
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.DROPPED.value)

        response = self.client.get(reverse("home"))
        titles = _flatten_group_titles(response.context["groups"])
        self.assertNotIn("Movie To Drop", titles)

    def test_drop_uses_inline_confirmation_not_browser_confirm(self):
        """Test that drop button uses inline confirmation instead of hx-confirm."""
        Item.objects.create(
            media_id="401b",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Confirm Drop Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=Item.objects.get(media_id="401b"),
            user=self.user,
            status=Status.PLANNING.value,
        )
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "hx-confirm")
        self.assertContains(response, "confirmDrop")
        self.assertContains(response, "Drop this?")

    def test_quick_start_planning_to_in_progress(self):
        """Test that quick_status_transition moves Planning to In Progress."""
        item = Item.objects.create(
            media_id="501",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Movie To Start",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.post(
            reverse("quick_status_transition"),
            {
                "media_type": "movie",
                "instance_id": movie.id,
                "target_status": "In progress",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Refresh"], "true")
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.IN_PROGRESS.value)
        self.assertIsNotNone(movie.start_date)

    def test_quick_plan_paused_to_planning(self):
        """Test that quick_status_transition moves Paused to Planning."""
        item = Item.objects.create(
            media_id="502",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Movie To Plan",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.PAUSED.value,
        )

        response = self.client.post(
            reverse("quick_status_transition"),
            {
                "media_type": "movie",
                "instance_id": movie.id,
                "target_status": "Planning",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Refresh"], "true")
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.PLANNING.value)

    def test_quick_status_transition_invalid_source_status(self):
        """Test that In Progress items cannot use quick_status_transition."""
        item = Item.objects.create(
            media_id="503",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="In Progress Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        response = self.client.post(
            reverse("quick_status_transition"),
            {
                "media_type": "movie",
                "instance_id": movie.id,
                "target_status": "Planning",
            },
        )

        self.assertEqual(response.status_code, 400)
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.IN_PROGRESS.value)

    def test_quick_status_transition_wrong_target(self):
        """Test that Planning cannot transition to Completed."""
        item = Item.objects.create(
            media_id="504",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Planning Movie Wrong Target",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.post(
            reverse("quick_status_transition"),
            {
                "media_type": "movie",
                "instance_id": movie.id,
                "target_status": "Completed",
            },
        )

        self.assertEqual(response.status_code, 400)
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.PLANNING.value)

    def test_start_button_on_planning_card(self):
        """Test that Planning cards show the Start button."""
        Item.objects.create(
            media_id="505",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Planning Card Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=Item.objects.get(media_id="505"),
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.get(reverse("home"))
        content = response.content.decode()
        self.assertIn("Start", content)
        self.assertIn("quick_status_transition", content)

    def test_plan_button_on_paused_card(self):
        """Test that Paused cards show the Plan button."""
        Item.objects.create(
            media_id="506",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Paused Card Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=Item.objects.get(media_id="506"),
            user=self.user,
            status=Status.PAUSED.value,
        )

        response = self.client.get(reverse("home"))
        content = response.content.decode()
        self.assertIn("Plan", content)
        self.assertIn("quick_status_transition", content)

    def test_no_transition_button_on_in_progress_card(self):
        """Test that In Progress cards don't show Start or Plan buttons."""
        item = Item.objects.create(
            media_id="507",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="IP No Transition Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        response = self.client.get(reverse("home") + "?type=movie")
        content = response.content.decode()
        self.assertNotIn("quick_status_transition", content)

    @patch("app.providers.services.get_media_metadata")
    def test_backlog_save_complete_moves_to_archive(self, mock_metadata):
        """Test that saving with Completed status returns archive response."""
        mock_metadata.return_value = {"max_progress": None}
        movie_item = Item.objects.create(
            media_id="900",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Movie To Complete",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        data = self._backlog_save_data(movie)
        data["status"] = Status.COMPLETED.value
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/backlog_completed.html")
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.COMPLETED.value)

    def test_backlog_save_drop_removes_card(self):
        """Test that saving with Dropped status returns dropped response."""
        movie_item = Item.objects.create(
            media_id="901",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Movie To Drop Via Save",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        data = self._backlog_save_data(movie)
        data["status"] = Status.DROPPED.value
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/backlog_dropped.html")
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.DROPPED.value)

    def test_backlog_save_in_progress_no_events_shows_done(self):
        """Test that saving keeps Done button for In Progress items without events."""
        movie_item = Item.objects.create(
            media_id="902",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="IP Movie No Events",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        response = self.client.post(
            reverse("backlog_save"), self._backlog_save_data(movie)
        )

        self.assertContains(response, "quick_complete")

    def test_backlog_save_planning_no_done_button(self):
        """Test that saving a Planning item does not show Done button."""
        movie_item = Item.objects.create(
            media_id="903",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Planning Movie Save",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.post(
            reverse("backlog_save"), self._backlog_save_data(movie)
        )

        self.assertNotContains(response, "quick_complete")
        self.assertNotContains(response, "quick_catch_up")

    def test_backlog_save_status_change_triggers_refresh(self):
        """Test that changing status via inline edit triggers a page refresh."""
        movie_item = Item.objects.create(
            media_id="904",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Was Planning Now IP",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        data = self._backlog_save_data(movie)
        data["status"] = Status.IN_PROGRESS.value
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response["HX-Refresh"], "true")
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.IN_PROGRESS.value)

    def test_backlog_save_same_status_no_refresh(self):
        """Test that saving without status change does not trigger a refresh."""
        movie_item = Item.objects.create(
            media_id="906",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Same Status Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        data = self._backlog_save_data(movie)
        data["score"] = "8.5"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertNotIn("HX-Refresh", response)
        self.assertTemplateUsed(response, "app/components/backlog_card.html")

    def test_backlog_save_in_progress_to_paused_triggers_refresh(self):
        """Test that In Progress to Paused triggers refresh to regroup."""
        anime_item = Item.objects.create(
            media_id="907",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="IP to Paused Anime",
            image="http://example.com/image.jpg",
        )
        anime = Anime.objects.create(
            item=anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        data = self._backlog_save_data(anime)
        data["status"] = Status.PAUSED.value
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response["HX-Refresh"], "true")
        anime.refresh_from_db()
        self.assertEqual(anime.status, Status.PAUSED.value)

    def test_backlog_save_paused_no_done_button(self):
        """Test that saving a Paused item does not show Done button."""
        anime_item = Item.objects.create(
            media_id="905",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Paused Anime Save",
            image="http://example.com/image.jpg",
        )
        anime = Anime.objects.create(
            item=anime_item,
            user=self.user,
            status=Status.PAUSED.value,
        )

        response = self.client.post(
            reverse("backlog_save"), self._backlog_save_data(anime)
        )

        self.assertNotContains(response, "quick_complete")
        self.assertNotContains(response, "quick_catch_up")
