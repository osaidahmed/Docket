from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app.models import (
    Anime,
    Item,
    MediaTypes,
    Movie,
    Sources,
    Status,
)
from events.models import Event


class TrackModalViewTests(TestCase):
    """Test the track modal view."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

        self.item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )
        self.movie = Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=0,
        )

    def test_track_modal_view_existing_media(self):
        """Test the track modal view for existing media."""
        response = self.client.get(
            reverse(
                "track_modal",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "media_id": "238",
                },
            )
            + "?return_url=/home",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/fill_track.html")

        self.assertIn("form", response.context)
        self.assertIn("media", response.context)
        self.assertEqual(response.context["media"], self.movie)
        self.assertEqual(response.context["return_url"], "/home")

    @patch("app.providers.services.get_media_metadata")
    def test_track_modal_view_new_media(self, mock_get_metadata):
        """Test the track modal view for new media."""
        mock_get_metadata.return_value = {
            "media_id": "278",
            "title": "New Movie",
            "media_type": MediaTypes.MOVIE.value,
            "source": Sources.TMDB.value,
            "image": "http://example.com/image.jpg",
            "max_progress": 1,
        }

        response = self.client.get(
            reverse(
                "track_modal",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "media_id": "278",
                },
            )
            + "?return_url=/home&title=New+Movie",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/fill_track.html")

        self.assertIn("form", response.context)
        self.assertEqual(response.context["form"].initial["media_id"], "278")
        self.assertEqual(
            response.context["form"].initial["media_type"],
            MediaTypes.MOVIE.value,
        )


class TrackModalAnnouncedMediaTests(TestCase):
    """Test that track modal restricts fields/status for announced media."""

    def setUp(self):
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    @patch("app.providers.services.get_media_metadata")
    def test_track_modal_restricts_status_for_announced_media(self, mock_get_metadata):
        mock_get_metadata.return_value = {
            "media_id": "99999",
            "title": "Upcoming Anime",
            "media_type": MediaTypes.ANIME.value,
            "source": Sources.MAL.value,
            "image": "http://example.com/image.jpg",
            "details": {"status": "Upcoming"},
        }

        response = self.client.get(
            reverse(
                "track_modal",
                kwargs={
                    "source": Sources.MAL.value,
                    "media_type": MediaTypes.ANIME.value,
                    "media_id": "99999",
                },
            )
            + "?return_url=/home",
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        status_values = [c[0] for c in form.fields["status"].choices]
        self.assertEqual(status_values, [Status.PLANNING.value])

    @patch("app.providers.services.get_media_metadata")
    def test_track_modal_strips_fields_for_announced_media(self, mock_get_metadata):
        mock_get_metadata.return_value = {
            "media_id": "99998",
            "title": "Announced Movie",
            "media_type": MediaTypes.MOVIE.value,
            "source": Sources.TMDB.value,
            "image": "http://example.com/image.jpg",
            "details": {"status": "Announced"},
        }

        response = self.client.get(
            reverse(
                "track_modal",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "media_id": "99998",
                },
            )
            + "?return_url=/home",
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertNotIn("score", form.fields)
        self.assertNotIn("progress", form.fields)
        self.assertIn("status", form.fields)
        self.assertIn("notes", form.fields)

    @patch("app.providers.services.get_media_metadata")
    def test_track_modal_all_statuses_for_released_media(self, mock_get_metadata):
        mock_get_metadata.return_value = {
            "media_id": "99997",
            "title": "Released Movie",
            "media_type": MediaTypes.MOVIE.value,
            "source": Sources.TMDB.value,
            "image": "http://example.com/image.jpg",
            "details": {"status": "Released"},
        }

        response = self.client.get(
            reverse(
                "track_modal",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "media_id": "99997",
                },
            )
            + "?return_url=/home",
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        status_values = [c[0] for c in form.fields["status"].choices]
        self.assertIn(Status.IN_PROGRESS.value, status_values)
        self.assertIn(Status.COMPLETED.value, status_values)
        self.assertIn("score", form.fields)


class TrackModalNotYetAiringTests(TestCase):
    """Test that track modal strips fields for not-yet-airing media."""

    def setUp(self):
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    def test_track_modal_strips_fields_for_not_yet_airing(self):
        item = Item.objects.create(
            media_id="9000",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Future Anime",
            image="http://example.com/image.jpg",
        )
        Event.objects.create(
            item=item,
            content_number=1,
            datetime=timezone.now() + timedelta(days=30),
        )
        anime = Anime.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        response = self.client.get(
            reverse(
                "track_modal",
                kwargs={
                    "source": Sources.MAL.value,
                    "media_type": MediaTypes.ANIME.value,
                    "media_id": "9000",
                },
            )
            + f"?return_url=/home&instance_id={anime.id}",
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertNotIn("score", form.fields)
        self.assertNotIn("progress", form.fields)
        self.assertNotIn("caught_up", form.fields)
        self.assertNotIn("is_rewatch", form.fields)
        self.assertIn("status", form.fields)
        self.assertIn("notes", form.fields)

    def test_track_modal_restricts_status_for_not_yet_airing(self):
        item = Item.objects.create(
            media_id="9002",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Future Anime 2",
            image="http://example.com/image.jpg",
        )
        Event.objects.create(
            item=item,
            content_number=1,
            datetime=timezone.now() + timedelta(days=30),
        )
        anime = Anime.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        response = self.client.get(
            reverse(
                "track_modal",
                kwargs={
                    "source": Sources.MAL.value,
                    "media_type": MediaTypes.ANIME.value,
                    "media_id": "9002",
                },
            )
            + f"?return_url=/home&instance_id={anime.id}",
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        status_values = [c[0] for c in form.fields["status"].choices]
        self.assertIn(Status.PLANNING.value, status_values)
        self.assertIn(Status.DROPPED.value, status_values)
        self.assertNotIn(Status.IN_PROGRESS.value, status_values)
        self.assertNotIn(Status.COMPLETED.value, status_values)
        self.assertNotIn(Status.PAUSED.value, status_values)

    def test_track_modal_keeps_fields_for_airing_media(self):
        item = Item.objects.create(
            media_id="9001",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Airing Anime",
            image="http://example.com/image.jpg",
        )
        Event.objects.create(
            item=item,
            content_number=1,
            datetime=timezone.now() - timedelta(days=7),
        )
        Event.objects.create(
            item=item,
            content_number=2,
            datetime=timezone.now() + timedelta(days=7),
        )
        # create with PLANNING to avoid process_status calling get_media_metadata,
        # then update via queryset to bypass save() hooks entirely
        anime = Anime.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )
        Anime.objects.filter(id=anime.id).update(
            status=Status.IN_PROGRESS.value, progress=1
        )
        anime.refresh_from_db()

        response = self.client.get(
            reverse(
                "track_modal",
                kwargs={
                    "source": Sources.MAL.value,
                    "media_type": MediaTypes.ANIME.value,
                    "media_id": "9001",
                },
            )
            + f"?return_url=/home&instance_id={anime.id}",
        )

        self.assertEqual(response.status_code, 200)
        form = response.context["form"]
        self.assertIn("score", form.fields)
        self.assertIn("progress", form.fields)
        self.assertIn("is_rewatch", form.fields)
