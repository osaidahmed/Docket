from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import (
    MediaTypes,
    Sources,
)


class MediaSearchViewTests(TestCase):
    """Test the media search view."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    @patch("app.providers.services.search")
    def test_media_search_view(self, mock_search):
        """Test the media search view."""
        mock_search.return_value = {
            "page": 1,
            "total_results": 1,
            "total_pages": 1,
            "results": [
                {
                    "media_id": "238",
                    "title": "Test Movie",
                    "media_type": MediaTypes.MOVIE.value,
                    "source": Sources.TMDB.value,
                    "image": "http://example.com/image.jpg",
                    "synopsis": "A test movie synopsis.",
                },
            ],
        }

        response = self.client.get(
            reverse("search") + "?media_type=movie&q=test",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/search.html")

        self.user.refresh_from_db()
        self.assertEqual(self.user.last_search_type, MediaTypes.MOVIE.value)

        mock_search.assert_called_once_with(
            MediaTypes.MOVIE.value,
            "test",
            1,
            Sources.TMDB.value,
        )

    @patch("app.providers.services.search_all")
    def test_unified_search_view(self, mock_search_all):
        """Test the unified search view with media_type=all."""
        mock_search_all.return_value = [
            {
                "media_type": MediaTypes.ANIME.value,
                "results": [
                    {
                        "media_id": "1",
                        "title": "Test Anime",
                        "media_type": MediaTypes.ANIME.value,
                        "source": Sources.MAL.value,
                        "image": "http://example.com/anime.jpg",
                        "synopsis": "An anime synopsis.",
                    },
                ],
            },
            {
                "media_type": MediaTypes.TV.value,
                "results": [
                    {
                        "media_id": "2",
                        "title": "Test TV",
                        "media_type": MediaTypes.TV.value,
                        "source": Sources.TMDB.value,
                        "image": "http://example.com/tv.jpg",
                        "synopsis": "A TV synopsis.",
                    },
                ],
            },
        ]

        response = self.client.get(
            reverse("search") + "?media_type=all&q=test",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/search_unified.html")

        self.user.refresh_from_db()
        self.assertNotEqual(self.user.last_search_type, "all")

        mock_search_all.assert_called_once()

    @patch("app.providers.services.search_all")
    def test_unified_search_no_results(self, mock_search_all):
        """Test the unified search view with no results."""
        mock_search_all.return_value = []

        response = self.client.get(
            reverse("search") + "?media_type=all&q=nonexistent",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/search_unified.html")
        self.assertEqual(
            response.context["grouped_results"],
            [],
        )
