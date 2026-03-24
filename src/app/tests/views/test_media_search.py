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


class MediaSearchViewTests(TestCase):
    """Test the media search view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    @patch("app.providers.services.search")
    def test_media_search_view(self, mock_search):
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

    def test_typed_search_empty_query_returns_blank_page(self):
        """Empty query on a specific media type returns search page with no results."""
        response = self.client.get(
            reverse("search") + "?media_type=movie&q=",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/search.html")
        self.assertEqual(response.context["data"]["results"], [])

    def test_unified_search_empty_query_returns_blank_page(self):
        """Empty query on unified search returns unified page with no results."""
        response = self.client.get(
            reverse("search") + "?media_type=all&q=",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/search_unified.html")
        self.assertEqual(response.context["grouped_results"], [])


class QuickAddViewTests(TestCase):
    """Test the quick_add view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    @patch("app.providers.services.get_media_metadata")
    def test_quick_add_creates_planning_media(self, mock_metadata):
        mock_metadata.return_value = {
            "title": "Test Movie",
            "image": "http://example.com/image.jpg",
        }

        response = self.client.post(
            reverse("quick_add"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/search_action.html")
        movie = Movie.objects.get(item__media_id="238", user=self.user)
        self.assertEqual(movie.status, Status.PLANNING.value)
        self.assertIsNone(movie.score)
        self.assertEqual(movie.progress, 0)

    @patch("app.providers.services.get_media_metadata")
    def test_quick_add_creates_item(self, mock_metadata):
        mock_metadata.return_value = {
            "title": "Test Anime",
            "image": "http://example.com/anime.jpg",
        }

        self.client.post(
            reverse("quick_add"),
            {
                "media_id": "1",
                "source": Sources.MAL.value,
                "media_type": MediaTypes.ANIME.value,
            },
        )

        item = Item.objects.get(media_id="1", source=Sources.MAL.value)
        self.assertEqual(item.title, "Test Anime")
        self.assertEqual(item.image, "http://example.com/anime.jpg")

    def test_quick_add_already_tracked_no_duplicate(self):
        item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        response = self.client.post(
            reverse("quick_add"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Movie.objects.filter(item__media_id="238", user=self.user).count(),
            1,
        )

    def test_quick_add_existing_item_skips_metadata_fetch(self):
        Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )

        with patch(
            "app.providers.services.get_media_metadata",
        ) as mock_metadata:
            self.client.post(
                reverse("quick_add"),
                {
                    "media_id": "238",
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                },
            )
            mock_metadata.assert_not_called()

        self.assertTrue(
            Movie.objects.filter(
                item__media_id="238",
                user=self.user,
            ).exists(),
        )

    @patch("app.providers.services.get_media_metadata")
    def test_quick_add_populates_synopsis(self, mock_metadata):
        mock_metadata.return_value = {
            "title": "Test Movie",
            "image": "http://example.com/image.jpg",
            "synopsis": "A great movie about testing.",
        }

        self.client.post(
            reverse("quick_add"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        item = Item.objects.get(media_id="238", source=Sources.TMDB.value)
        self.assertEqual(item.synopsis, "A great movie about testing.")


class QuickArchiveViewTests(TestCase):
    """Test the quick_archive view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    @patch("app.providers.services.get_media_metadata")
    def test_quick_archive_creates_completed_media(self, mock_metadata):
        mock_metadata.return_value = {
            "title": "Test Movie",
            "image": "http://example.com/image.jpg",
            "max_progress": None,
        }

        response = self.client.post(
            reverse("quick_archive"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/search_action.html")
        movie = Movie.objects.get(item__media_id="238", user=self.user)
        self.assertEqual(movie.status, Status.COMPLETED.value)

    def test_quick_archive_already_tracked_no_duplicate(self):
        item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        response = self.client.post(
            reverse("quick_archive"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Movie.objects.filter(item__media_id="238", user=self.user).count(),
            1,
        )

    @patch("app.providers.services.get_media_metadata")
    def test_quick_archive_existing_item_skips_metadata_fetch(self, mock_metadata):
        mock_metadata.return_value = {"max_progress": None}
        Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )

        self.client.post(
            reverse("quick_archive"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        mock_metadata.assert_called_once()
        movie = Movie.objects.get(item__media_id="238", user=self.user)
        self.assertEqual(movie.status, Status.COMPLETED.value)
