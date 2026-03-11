from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app.models import Anime, Item, Manga, MediaTypes, Sources, Status
from events.models import Event


class OngoingCaughtUpTests(TestCase):
    """Tests for ongoing/caught-up badge logic and quick_catch_up action."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.anime_item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Test Anime",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
            item=cls.anime_item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
            progress=10,
        )

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

    def test_ongoing_caught_up_when_progress_matches(self):
        """Test that caught-up users see 'Caught Up' (no question mark)."""
        Event.objects.create(
            item=self.anime_item,
            content_number=11,
            datetime=timezone.now() + timedelta(days=2),
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "Caught Up?")

    @patch("app.providers.services.get_media_metadata")
    def test_ongoing_caught_up_uncertain_when_behind(self, mock_metadata):
        """Test that users behind on progress see 'Caught Up?' button."""
        mock_metadata.return_value = {"max_progress": 24}
        anime_item = Item.objects.create(
            media_id="2",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Behind Anime",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
            item=anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=5,
        )
        Event.objects.create(
            item=anime_item,
            content_number=11,
            datetime=timezone.now() + timedelta(days=2),
        )

        response = self.client.get(reverse("home") + "?type=anime")
        self.assertContains(response, "Caught Up?")
        self.assertContains(response, "quick_catch_up")

    @patch("app.providers.services.get_media_metadata")
    def test_quick_catch_up_updates_progress(self, mock_metadata):
        """Test that quick_catch_up sets progress to latest aired episode."""
        mock_metadata.return_value = {"max_progress": 24}
        anime_item = Item.objects.create(
            media_id="3",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Catch Up Anime",
            image="http://example.com/image.jpg",
        )
        anime = Anime.objects.create(
            item=anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=5,
        )
        Event.objects.create(
            item=anime_item,
            content_number=11,
            datetime=timezone.now() + timedelta(days=2),
        )

        response = self.client.post(
            reverse("quick_catch_up"),
            {"media_type": "anime", "instance_id": anime.id},
        )

        self.assertEqual(response.status_code, 200)
        anime.refresh_from_db()
        self.assertEqual(anime.progress, 10)
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "Caught Up?")

    def test_in_progress_item_shows_done(self):
        """Test that In Progress items with no future events show Done button."""
        movie_item = Item.objects.create(
            media_id="300",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="In Progress Movie",
            image="http://example.com/image.jpg",
        )
        from app.models import Movie

        Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        response = self.client.get(reverse("home") + "?type=movie")
        self.assertContains(response, "quick_complete")

    def test_sentinel_event_shows_done(self):
        """Test that sentinel-date events don't suppress the Done button."""
        Event.objects.create(
            item=self.anime_item,
            content_number=11,
            datetime=datetime(9999, 12, 31, 23, 59, 59, 999999, tzinfo=UTC),
        )

        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "quick_catch_up")
        self.assertContains(response, "quick_complete")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_manga_ongoing_shows_caught_up(self, _mock_releases, mock_metadata):
        """Test that ongoing manga with undated events shows Caught Up."""
        mock_metadata.return_value = {"max_progress": 100}
        manga_item = Item.objects.create(
            media_id="66296374554",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Ongoing Manga",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=50,
        )
        Event.objects.create(
            item=manga_item,
            content_number=50,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.get(reverse("home") + "?type=manga")
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "quick_complete")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_manga_ongoing_no_next_info(self, _mock_releases, mock_metadata):
        """Test that ongoing manga with undated events does not show Next: info."""
        mock_metadata.return_value = {"max_progress": 100}
        manga_item = Item.objects.create(
            media_id="66296374555",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Ongoing Manga No Next",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        Event.objects.create(
            item=manga_item,
            content_number=10,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.get(reverse("home") + "?type=manga")
        self.assertNotContains(response, "Next:")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_manga_no_events_shows_catch_up_button(self, _mock_releases, mock_metadata):
        """Test that manga with no events shows Caught Up? button."""
        mock_metadata.return_value = {"max_progress": None}
        manga_item = Item.objects.create(
            media_id="66296374556",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="No Events Manga",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        response = self.client.get(reverse("home") + "?type=manga")
        self.assertContains(response, "quick_catch_up")
        self.assertNotContains(response, "quick_complete")

    def test_season_ongoing_shows_caught_up(self):
        """Test that TV season with undated events shows Caught Up."""
        from app.models import Episode, Season

        season_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test TV Show",
            image="http://example.com/image.jpg",
            season_number=1,
        )
        season = Season.objects.create(
            item=season_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        for i in range(1, 6):
            episode_item = Item.objects.create(
                media_id="1668",
                source=Sources.TMDB.value,
                media_type=MediaTypes.EPISODE.value,
                title="Test TV Show",
                image="http://example.com/image.jpg",
                season_number=1,
                episode_number=i,
            )
            Episode.objects.create(
                item=episode_item,
                related_season=season,
                end_date=timezone.now() - timezone.timedelta(days=i),
            )
        Event.objects.create(
            item=season_item,
            content_number=6,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.get(reverse("home") + "?type=tv")
        self.assertContains(response, "Caught Up")

    def test_anime_min_datetime_shows_caught_up(self):
        """Test that anime with datetime.min events shows Caught Up."""
        Event.objects.create(
            item=self.anime_item,
            content_number=11,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.get(reverse("home") + "?type=anime")
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "quick_complete")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_paused_manga_no_caught_up(self, _mock_releases, mock_metadata):
        """Test that paused manga with events shows neither Caught Up nor Done."""
        mock_metadata.return_value = {"max_progress": 100}
        manga_item = Item.objects.create(
            media_id="66296374557",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Paused Manga",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.PAUSED.value,
        )
        Event.objects.create(
            item=manga_item,
            content_number=10,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.get(reverse("home") + "?type=manga")
        self.assertNotContains(response, "quick_catch_up")
        self.assertNotContains(response, "quick_complete")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_backlog_save_preserves_manga_caught_up(
        self, _mock_releases, mock_metadata
    ):
        """Test that saving ongoing manga preserves Caught Up badge."""
        mock_metadata.return_value = {"max_progress": 100}
        manga_item = Item.objects.create(
            media_id="66296374558",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Save Manga",
            image="http://example.com/image.jpg",
        )
        manga = Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=20,
        )
        Event.objects.create(
            item=manga_item,
            content_number=20,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.post(
            reverse("backlog_save"), self._backlog_save_data(manga)
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "quick_complete")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_mal_manga_ongoing_no_chapters_shows_catch_up_button(
        self, _mock_releases, mock_metadata
    ):
        """Test MAL manga with unknown chapters shows Caught Up? button."""
        mock_metadata.return_value = {"max_progress": None}
        manga_item = Item.objects.create(
            media_id="66296374559",
            source=Sources.MAL.value,
            media_type=MediaTypes.MANGA.value,
            title="MAL Ongoing Manga",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        Event.objects.create(
            item=manga_item,
            content_number=None,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.get(reverse("home") + "?type=manga")
        self.assertContains(response, "quick_catch_up")
        self.assertNotContains(response, "quick_complete")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_manga_caught_up_field_shows_badge(self, _mock_releases, mock_metadata):
        """Test that caught_up=True on model shows Caught Up badge."""
        mock_metadata.return_value = {"max_progress": None}
        manga_item = Item.objects.create(
            media_id="66296374570",
            source=Sources.MAL.value,
            media_type=MediaTypes.MANGA.value,
            title="Manual Caught Up Manga",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            caught_up=True,
        )

        response = self.client.get(reverse("home") + "?type=manga")
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "quick_catch_up")
        self.assertNotContains(response, "quick_complete")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_quick_catch_up_unknown_progress_sets_caught_up(
        self, _mock_releases, mock_metadata
    ):
        """Test quick_catch_up sets caught_up=True when max_progress unknown."""
        mock_metadata.return_value = {"max_progress": None}
        manga_item = Item.objects.create(
            media_id="66296374571",
            source=Sources.MAL.value,
            media_type=MediaTypes.MANGA.value,
            title="Unknown Progress Manga",
            image="http://example.com/image.jpg",
        )
        manga = Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        Event.objects.create(
            item=manga_item,
            content_number=None,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.post(
            reverse("quick_catch_up"),
            {
                "media_type": MediaTypes.MANGA.value,
                "instance_id": manga.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        manga.refresh_from_db()
        self.assertTrue(manga.caught_up)
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "quick_catch_up")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_manga_ongoing_behind_shows_catch_up_button(
        self, _mock_releases, mock_metadata
    ):
        """Test ongoing manga where user is behind shows Caught Up? button."""
        mock_metadata.return_value = {"max_progress": 100}
        manga_item = Item.objects.create(
            media_id="66296374560",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Behind Manga",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=20,
        )
        Event.objects.create(
            item=manga_item,
            content_number=50,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.get(reverse("home") + "?type=manga")
        self.assertContains(response, "quick_catch_up")
        self.assertNotContains(response, "quick_complete")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_manga_ongoing_zero_progress_shows_catch_up_button(
        self, _mock_releases, mock_metadata
    ):
        """Test ongoing manga at progress 0 shows Caught Up? button."""
        mock_metadata.return_value = {"max_progress": 100}
        manga_item = Item.objects.create(
            media_id="66296374561",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Zero Progress Manga",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=0,
        )
        Event.objects.create(
            item=manga_item,
            content_number=30,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.get(reverse("home") + "?type=manga")
        self.assertContains(response, "quick_catch_up")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_quick_catch_up_ongoing_manga(self, _mock_releases, mock_metadata):
        """Test quick_catch_up sets progress to max_progress for ongoing."""
        mock_metadata.return_value = {"max_progress": 100}
        manga_item = Item.objects.create(
            media_id="66296374562",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Catch Up Manga",
            image="http://example.com/image.jpg",
        )
        manga = Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=10,
        )
        Event.objects.create(
            item=manga_item,
            content_number=50,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.post(
            reverse("quick_catch_up"),
            {
                "media_type": MediaTypes.MANGA.value,
                "instance_id": manga.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        manga.refresh_from_db()
        self.assertEqual(manga.progress, 50)
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "quick_catch_up")

    def test_next_event_info_displayed(self):
        """Test that next event info appears on ongoing backlog cards."""
        Event.objects.create(
            item=self.anime_item,
            content_number=11,
            datetime=timezone.now() + timedelta(days=1),
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, "Next:")
        self.assertContains(response, "11")

    def test_backlog_save_preserves_caught_up(self):
        """Test that saving an ongoing In Progress item still shows Caught Up."""
        anime = Anime.objects.get(item=self.anime_item, user=self.user)
        Event.objects.create(
            item=self.anime_item,
            content_number=11,
            datetime=timezone.now() + timedelta(days=2),
        )

        response = self.client.post(
            reverse("backlog_save"), self._backlog_save_data(anime)
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "quick_complete")

    def test_backlog_save_preserves_next_event_info(self):
        """Test that saving preserves the next event info line."""
        anime = Anime.objects.get(item=self.anime_item, user=self.user)
        Event.objects.create(
            item=self.anime_item,
            content_number=11,
            datetime=timezone.now() + timedelta(days=2),
        )

        response = self.client.post(
            reverse("backlog_save"), self._backlog_save_data(anime)
        )

        self.assertContains(response, "Next:")
