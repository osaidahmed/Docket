from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import (
    Item,
    MediaTypes,
    Game,
    Movie,
    Season,
    Sources,
    Status,
)


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

    def test_track_modal_with_instance_id(self):
        response = self.client.get(
            reverse(
                "track_modal",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "media_id": "238",
                },
            )
            + f"?return_url=/home&instance_id={self.movie.id}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["media"], self.movie)

    @patch("app.providers.services.get_media_metadata")
    def test_track_modal_is_create(self, mock_get_metadata):
        mock_get_metadata.return_value = {
            "media_id": "999",
            "title": "Brand New Movie",
            "media_type": MediaTypes.MOVIE.value,
            "source": Sources.TMDB.value,
            "image": "http://example.com/image.jpg",
        }
        response = self.client.get(
            reverse(
                "track_modal",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "media_id": "999",
                },
            )
            + "?return_url=/home&is_create=true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["media"])
        self.assertEqual(response.context["title"], "Brand New Movie")

    def test_track_modal_game_progress(self):
        game_item = Item.objects.create(
            media_id="1",
            source=Sources.IGDB.value,
            media_type=MediaTypes.GAME.value,
            title="Test Game",
            image="http://example.com/image.jpg",
        )
        game = Game.objects.create(
            item=game_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=120,
        )
        response = self.client.get(
            reverse(
                "track_modal",
                kwargs={
                    "source": Sources.IGDB.value,
                    "media_type": MediaTypes.GAME.value,
                    "media_id": "1",
                },
            )
            + f"?return_url=/home&instance_id={game.id}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].initial["progress"], "2h 00min")

    @patch("app.providers.services.get_media_metadata")
    def test_track_modal_season_title(self, mock_get_metadata):
        mock_get_metadata.return_value = {
            "media_id": "1668",
            "title": "Test TV Show",
            "media_type": MediaTypes.SEASON.value,
            "source": Sources.TMDB.value,
            "image": "http://example.com/image.jpg",
            "season/1": {
                "title": "Test TV Show",
                "image": "http://example.com/season.jpg",
            },
        }
        response = self.client.get(
            reverse(
                "track_modal",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.SEASON.value,
                    "media_id": "1668",
                    "season_number": 1,
                },
            )
            + "?return_url=/home&is_create=true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("S1", response.context["title"])
