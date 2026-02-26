from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
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
from app.services import recent
from events.models import Event


class MediaDetailsViewTests(TestCase):
    """Test the media details views."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    @patch("app.providers.services.get_media_metadata")
    def test_media_details_view(self, mock_get_metadata):
        """Test the media details view."""
        mock_get_metadata.return_value = {
            "media_id": "238",
            "title": "Test Movie",
            "media_type": MediaTypes.MOVIE.value,
            "source": Sources.TMDB.value,
            "image": "http://example.com/image.jpg",
            "overview": "Test overview",
            "release_date": "2023-01-01",
        }

        response = self.client.get(
            reverse(
                "media_details",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "media_id": "238",
                    "title": "test-movie",
                },
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/media_details.html")

        self.assertIn("media", response.context)
        self.assertEqual(response.context["media"]["title"], "Test Movie")

        mock_get_metadata.assert_called_once_with(
            MediaTypes.MOVIE.value,
            "238",
            Sources.TMDB.value,
        )

    @patch("app.providers.services.get_media_metadata")
    @patch("app.providers.tmdb.process_episodes")
    def test_season_details_view(self, mock_process_episodes, mock_get_metadata):
        """Test the season details view."""
        mock_get_metadata.return_value = {
            "title": "Test TV Show",
            "media_id": "1668",
            "source": Sources.TMDB.value,
            "media_type": MediaTypes.TV.value,
            "image": "http://example.com/image.jpg",
            "season/1": {
                "title": "Season 1",
                "media_id": "1668",
                "media_type": MediaTypes.SEASON.value,
                "source": Sources.TMDB.value,
                "image": "http://example.com/season.jpg",
                "episodes": [],
            },
        }

        mock_process_episodes.return_value = [
            {
                "media_id": "1668",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.EPISODE.value,
                "season_number": 1,
                "episode_number": 1,
                "name": "Episode 1",
                "air_date": "2023-01-01",
                "watched": False,
            },
        ]

        response = self.client.get(
            reverse(
                "season_details",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_id": "1668",
                    "title": "test-tv-show",
                    "season_number": 1,
                },
            ),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/media_details.html")

        self.assertIn("media", response.context)
        self.assertEqual(response.context["media"]["title"], "Season 1")
        self.assertEqual(len(response.context["media"]["episodes"]), 1)

        mock_get_metadata.assert_called_once_with(
            "tv_with_seasons",
            "1668",
            Sources.TMDB.value,
            [1],
        )


@override_settings(REDIS_PREFIX=None)
class DetailViewTrackingTests(TestCase):
    """Test that detail views track recently viewed items."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)
        recent.redis_client.flushdb()

    @patch("app.providers.services.get_media_metadata")
    def test_media_details_tracks_view(self, mock_get_metadata):
        mock_get_metadata.return_value = {
            "media_id": "238",
            "title": "Fight Club",
            "english_title": "",
            "media_type": MediaTypes.MOVIE.value,
            "source": Sources.TMDB.value,
            "image": "http://example.com/image.jpg",
        }

        self.client.get(
            reverse(
                "media_details",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "media_id": "238",
                    "title": "fight-club",
                },
            ),
        )

        results = recent.get_recent(self.user.id)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Fight Club")
        self.assertEqual(results[0]["media_type"], MediaTypes.MOVIE.value)
        self.assertEqual(results[0]["media_id"], "238")

    @patch("app.providers.tmdb.process_episodes")
    @patch("app.providers.services.get_media_metadata")
    def test_season_details_does_not_track(
        self, mock_get_metadata, mock_process_episodes
    ):
        mock_get_metadata.return_value = {
            "title": "Test TV Show",
            "media_id": "1668",
            "source": Sources.TMDB.value,
            "media_type": MediaTypes.TV.value,
            "image": "http://example.com/image.jpg",
            "season/1": {
                "title": "Season 1",
                "media_id": "1668",
                "media_type": MediaTypes.SEASON.value,
                "source": Sources.TMDB.value,
                "image": "http://example.com/season.jpg",
                "episodes": [],
            },
        }
        mock_process_episodes.return_value = []

        self.client.get(
            reverse(
                "season_details",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_id": "1668",
                    "title": "test-tv-show",
                    "season_number": 1,
                },
            ),
        )

        results = recent.get_recent(self.user.id)
        self.assertEqual(len(results), 0)

    @patch("app.providers.services.get_media_metadata")
    def test_detail_page_shows_quick_actions_for_untracked(self, mock_get_metadata):
        mock_get_metadata.return_value = {
            "media_id": "500",
            "title": "Untracked Movie",
            "media_type": MediaTypes.MOVIE.value,
            "source": Sources.TMDB.value,
            "image": "http://example.com/image.jpg",
        }

        response = self.client.get(
            reverse(
                "media_details",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "media_id": "500",
                    "title": "untracked-movie",
                },
            ),
        )

        self.assertContains(response, "quick_add")
        self.assertContains(response, "quick_archive")
        self.assertNotContains(response, ">Actions<")

    @patch("app.providers.services.get_media_metadata")
    def test_detail_page_hides_quick_actions_for_tracked(self, mock_get_metadata):
        mock_get_metadata.return_value = {
            "media_id": "501",
            "title": "Tracked Movie",
            "media_type": MediaTypes.MOVIE.value,
            "source": Sources.TMDB.value,
            "image": "http://example.com/image.jpg",
            "max_progress": None,
        }

        item = Item.objects.create(
            media_id="501",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Tracked Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.COMPLETED.value,
        )

        response = self.client.get(
            reverse(
                "media_details",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "media_id": "501",
                    "title": "tracked-movie",
                },
            ),
        )

        self.assertNotContains(response, "quick_add")
        self.assertNotContains(response, "quick_archive")
        self.assertContains(response, ">Actions<")


class DetailAnnouncedMediaTests(TestCase):
    """Test that detail page gates actions for announced/unreleased media."""

    def setUp(self):
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    @patch("app.providers.services.get_media_metadata")
    def test_detail_page_hides_archive_for_announced(self, mock_get_metadata):
        mock_get_metadata.return_value = {
            "media_id": "7000",
            "title": "Upcoming Anime",
            "media_type": MediaTypes.ANIME.value,
            "source": Sources.MAL.value,
            "image": "http://example.com/image.jpg",
            "details": {"status": "Upcoming"},
        }

        response = self.client.get(
            reverse(
                "media_details",
                kwargs={
                    "source": Sources.MAL.value,
                    "media_type": MediaTypes.ANIME.value,
                    "media_id": "7000",
                    "title": "upcoming-anime",
                },
            ),
        )

        self.assertContains(response, "quick_add")
        self.assertNotContains(response, "quick_archive")

    @patch("app.providers.services.get_media_metadata")
    def test_detail_page_shows_archive_for_released(self, mock_get_metadata):
        mock_get_metadata.return_value = {
            "media_id": "7001",
            "title": "Released Movie",
            "media_type": MediaTypes.MOVIE.value,
            "source": Sources.TMDB.value,
            "image": "http://example.com/image.jpg",
            "details": {"status": "Released"},
        }

        response = self.client.get(
            reverse(
                "media_details",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "media_id": "7001",
                    "title": "released-movie",
                },
            ),
        )

        self.assertContains(response, "quick_add")
        self.assertContains(response, "quick_archive")


class DetailScoreGatingTests(TestCase):
    """Test that score widget is disabled for not-yet-airing media on detail page."""

    def setUp(self):
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    @patch("app.providers.services.get_media_metadata")
    def test_detail_page_hides_score_for_not_yet_airing(self, mock_get_metadata):
        mock_get_metadata.return_value = {
            "media_id": "8000",
            "title": "Future Anime",
            "media_type": MediaTypes.ANIME.value,
            "source": Sources.MAL.value,
            "image": "http://example.com/image.jpg",
        }
        item = Item.objects.create(
            media_id="8000",
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
        Anime.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        response = self.client.get(
            reverse(
                "media_details",
                kwargs={
                    "source": Sources.MAL.value,
                    "media_type": MediaTypes.ANIME.value,
                    "media_id": "8000",
                    "title": "future-anime",
                },
            ),
        )

        self.assertContains(response, "Not yet released")
        self.assertNotContains(response, "Click to edit")

    @patch("app.providers.services.get_media_metadata")
    def test_detail_page_shows_score_for_airing_media(self, mock_get_metadata):
        mock_get_metadata.return_value = {
            "media_id": "8001",
            "title": "Airing Anime",
            "media_type": MediaTypes.ANIME.value,
            "source": Sources.MAL.value,
            "image": "http://example.com/image.jpg",
        }
        item = Item.objects.create(
            media_id="8001",
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

        response = self.client.get(
            reverse(
                "media_details",
                kwargs={
                    "source": Sources.MAL.value,
                    "media_type": MediaTypes.ANIME.value,
                    "media_id": "8001",
                    "title": "airing-anime",
                },
            ),
        )

        self.assertContains(response, "Click to edit")
        self.assertNotContains(response, "Not yet released")
