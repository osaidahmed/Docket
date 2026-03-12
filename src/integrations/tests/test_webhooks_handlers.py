from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import models
from django.test import TestCase
from django.utils import timezone

from app.models import (
    TV,
    Anime,
    Episode,
    Item,
    MediaTypes,
    Movie,
    Season,
    Sources,
    Status,
)
from integrations.webhooks.plex import PlexWebhookProcessor

MOVIE_METADATA = {
    "title": "The Matrix",
    "image": "http://example.com/matrix.jpg",
    "max_progress": 1,
}

TV_METADATA = {
    "title": "Friends",
    "image": "http://example.com/friends.jpg",
    "related": {
        "seasons": [
            {"season_number": 1, "image": "http://example.com/s1.jpg"},
        ],
    },
    "season/1": {
        "image": "http://example.com/s1.jpg",
        "max_progress": 10,
        "episodes": [
            {"episode_number": 1, "still_path": "/ep1.jpg"},
        ],
    },
}


def _get_media_metadata_side_effect(media_type, _media_id, _source, _seasons=None):
    if media_type == MediaTypes.MOVIE.value:
        return MOVIE_METADATA
    if media_type in ("tv_with_seasons", MediaTypes.TV.value):
        return TV_METADATA
    if media_type == MediaTypes.SEASON.value:
        return TV_METADATA["season/1"]
    return {}


def _plain_save(instance, *args, **kwargs):
    """Save without model-specific side effects."""
    models.Model.save(instance, *args, **kwargs)


class HandleMovieExistingInstanceTests(TestCase):
    """Tests for _handle_movie with existing non-completed instances."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="testuser",
            token="test-token",
            plex_usernames="testuser",
        )

    def setUp(self):
        self.processor = PlexWebhookProcessor()
        self.movie_item = Item.objects.create(
            media_id="603",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Matrix",
            image="http://example.com/matrix.jpg",
        )

    @patch("integrations.webhooks.base.app.providers.tmdb.movie")
    @patch("app.providers.services.get_media_metadata")
    def test_existing_planning_instance_marked_played(self, mock_meta, mock_movie):
        """Existing PLANNING movie completed via webhook."""
        mock_meta.side_effect = _get_media_metadata_side_effect
        mock_movie.return_value = MOVIE_METADATA
        Movie.objects.create(
            item=self.movie_item,
            user=self.user,
            status=Status.PLANNING.value,
            progress=0,
        )

        payload = {"event": "media.scrobble"}
        self.processor._handle_movie("603", payload, self.user)

        movie = Movie.objects.get(item=self.movie_item, user=self.user)
        self.assertEqual(movie.status, Status.COMPLETED.value)
        self.assertEqual(movie.progress, 1)
        self.assertIsNotNone(movie.end_date)

    @patch("integrations.webhooks.base.app.providers.tmdb.movie")
    @patch("app.providers.services.get_media_metadata")
    def test_existing_planning_instance_not_played(self, mock_meta, mock_movie):
        """Existing PLANNING movie set to IN_PROGRESS when not played."""
        mock_meta.side_effect = _get_media_metadata_side_effect
        mock_movie.return_value = MOVIE_METADATA
        Movie.objects.create(
            item=self.movie_item,
            user=self.user,
            status=Status.PLANNING.value,
            progress=0,
        )

        payload = {"event": "media.play"}
        self.processor._handle_movie("603", payload, self.user)

        movie = Movie.objects.get(item=self.movie_item, user=self.user)
        self.assertEqual(movie.status, Status.IN_PROGRESS.value)
        self.assertEqual(movie.progress, 0)
        self.assertIsNotNone(movie.start_date)

    @patch("integrations.webhooks.base.app.providers.tmdb.movie")
    @patch("app.providers.services.get_media_metadata")
    def test_existing_in_progress_instance_no_changes(self, mock_meta, mock_movie):
        """Existing IN_PROGRESS movie with same progress triggers no save."""
        mock_meta.side_effect = _get_media_metadata_side_effect
        mock_movie.return_value = MOVIE_METADATA
        instance = Movie.objects.create(
            item=self.movie_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=0,
        )
        original_progressed_at = instance.progressed_at

        payload = {"event": "media.play"}
        self.processor._handle_movie("603", payload, self.user)

        movie = Movie.objects.get(item=self.movie_item, user=self.user)
        self.assertEqual(movie.status, Status.IN_PROGRESS.value)
        self.assertEqual(movie.progress, 0)
        self.assertEqual(movie.progressed_at, original_progressed_at)


class HandleTVEpisodeTests(TestCase):
    """Tests for _handle_tv_episode edge cases."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="testuser",
            token="test-token",
            plex_usernames="testuser",
        )

    def setUp(self):
        self.processor = PlexWebhookProcessor()

    def _create_tv_setup(self, tv_status, season_status):
        """Create TV, season, and items with given statuses using plain saves."""
        tv_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Friends",
            image="http://example.com/friends.jpg",
        )
        tv_instance = TV(item=tv_item, user=self.user, status=tv_status)
        _plain_save(tv_instance)

        season_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            season_number=1,
            title="Friends",
            image="http://example.com/s1.jpg",
        )
        season_instance = Season(
            item=season_item,
            user=self.user,
            related_tv=tv_instance,
            status=season_status,
        )
        _plain_save(season_instance)
        return tv_item, tv_instance, season_item, season_instance

    @patch("app.providers.services.get_media_metadata")
    @patch("integrations.webhooks.base.app.providers.tmdb.tv_with_seasons")
    def test_existing_tv_instance_status_updated(self, mock_tv, mock_meta):
        """Existing COMPLETED TV instance set back to IN_PROGRESS."""
        mock_meta.side_effect = _get_media_metadata_side_effect
        mock_tv.return_value = TV_METADATA
        tv_item, _, _, _ = self._create_tv_setup(
            Status.COMPLETED.value, Status.IN_PROGRESS.value
        )

        payload = {"event": "media.scrobble"}
        self.processor._handle_tv_episode("1668", 1, 1, payload, self.user)

        tv_instance = TV.objects.get(item=tv_item, user=self.user)
        self.assertEqual(tv_instance.status, Status.IN_PROGRESS.value)

    @patch("app.providers.services.get_media_metadata")
    @patch("integrations.webhooks.base.app.providers.tmdb.tv_with_seasons")
    def test_existing_season_instance_status_updated(self, mock_tv, mock_meta):
        """Existing COMPLETED season set back to IN_PROGRESS."""
        mock_meta.side_effect = _get_media_metadata_side_effect
        mock_tv.return_value = TV_METADATA
        _, _, season_item, _ = self._create_tv_setup(
            Status.IN_PROGRESS.value, Status.COMPLETED.value
        )

        payload = {"event": "media.scrobble"}
        self.processor._handle_tv_episode("1668", 1, 1, payload, self.user)

        season = Season.objects.get(item=season_item, user=self.user)
        self.assertEqual(season.status, Status.IN_PROGRESS.value)

    @patch("app.providers.services.get_media_metadata")
    @patch("integrations.webhooks.base.app.providers.tmdb.tv_with_seasons")
    def test_duplicate_episode_detection(self, mock_tv, mock_meta):
        """Recent duplicate episode within threshold is skipped."""
        mock_meta.side_effect = _get_media_metadata_side_effect
        mock_tv.return_value = TV_METADATA
        _, _, _, season_instance = self._create_tv_setup(
            Status.IN_PROGRESS.value, Status.IN_PROGRESS.value
        )

        episode_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            season_number=1,
            episode_number=1,
            title="Friends",
            image="https://image.tmdb.org/t/p/original/ep1.jpg",
        )
        now = timezone.now().replace(second=0, microsecond=0)
        ep = Episode(
            item=episode_item,
            related_season=season_instance,
            end_date=now,
        )
        _plain_save(ep)

        payload = {"event": "media.scrobble"}
        self.processor._handle_tv_episode("1668", 1, 1, payload, self.user)

        self.assertEqual(Episode.objects.filter(item=episode_item).count(), 1)

    @patch("app.providers.services.get_media_metadata")
    @patch("integrations.webhooks.base.app.providers.tmdb.tv_with_seasons")
    def test_new_season_created_for_existing_tv(self, mock_tv, mock_meta):
        """New season created when TV exists but season doesn't."""
        mock_meta.side_effect = _get_media_metadata_side_effect
        mock_tv.return_value = TV_METADATA
        tv_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Friends",
            image="http://example.com/friends.jpg",
        )
        tv_instance = TV(item=tv_item, user=self.user, status=Status.IN_PROGRESS.value)
        _plain_save(tv_instance)

        payload = {"event": "media.play"}
        self.processor._handle_tv_episode("1668", 1, 1, payload, self.user)

        season = Season.objects.get(
            item__media_id="1668", item__season_number=1, user=self.user
        )
        self.assertEqual(season.status, Status.IN_PROGRESS.value)

    @patch("app.providers.services.get_media_metadata")
    @patch("integrations.webhooks.base.app.providers.tmdb.tv_with_seasons")
    def test_episode_not_played(self, mock_tv, mock_meta):
        """Episode not marked as played logs debug and creates nothing."""
        mock_meta.side_effect = _get_media_metadata_side_effect
        mock_tv.return_value = TV_METADATA

        payload = {"event": "media.play"}
        self.processor._handle_tv_episode("1668", 1, 1, payload, self.user)

        self.assertEqual(Episode.objects.count(), 0)

    @patch("app.providers.services.get_media_metadata")
    @patch("integrations.webhooks.base.app.providers.tmdb.tv_with_seasons")
    def test_episode_created_after_threshold(self, mock_tv, mock_meta):
        """Episode beyond time threshold is NOT considered duplicate."""
        mock_meta.side_effect = _get_media_metadata_side_effect
        mock_tv.return_value = TV_METADATA
        _, _, _, season_instance = self._create_tv_setup(
            Status.IN_PROGRESS.value, Status.IN_PROGRESS.value
        )

        episode_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            season_number=1,
            episode_number=1,
            title="Friends",
            image="https://image.tmdb.org/t/p/original/ep1.jpg",
        )
        old_time = timezone.now().replace(second=0, microsecond=0) - timedelta(
            seconds=10
        )
        ep = Episode(
            item=episode_item,
            related_season=season_instance,
            end_date=old_time,
        )
        _plain_save(ep)

        payload = {"event": "media.scrobble"}
        self.processor._handle_tv_episode("1668", 1, 1, payload, self.user)

        self.assertEqual(Episode.objects.filter(item=episode_item).count(), 2)


class HandleAnimeTests(TestCase):
    """Tests for _handle_anime edge cases."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="testuser",
            token="test-token",
            plex_usernames="testuser",
        )

    def setUp(self):
        self.processor = PlexWebhookProcessor()

    @patch("integrations.webhooks.base.app.providers.mal.anime")
    def test_handle_anime_not_played_decrements_episode(self, mock_mal_anime):
        """Not-played anime decrements episode number by 1."""
        mock_mal_anime.return_value = {
            "title": "Frieren",
            "image": "http://example.com/frieren.jpg",
            "max_progress": 28,
        }

        payload = {"event": "media.play"}
        self.processor._handle_anime("52991", 5, payload, self.user)

        anime = Anime.objects.get(item__media_id="52991", user=self.user)
        self.assertEqual(anime.progress, 4)
        self.assertEqual(anime.status, Status.IN_PROGRESS.value)

    @patch("app.providers.services.get_media_metadata")
    @patch("integrations.webhooks.base.app.providers.mal.anime")
    def test_handle_anime_existing_completed_by_played(self, mock_mal_anime, mock_meta):
        """Existing PLANNING anime completed when max_progress reached."""
        mock_mal_anime.return_value = {
            "title": "Frieren",
            "image": "http://example.com/frieren.jpg",
            "max_progress": 5,
        }
        mock_meta.return_value = {"max_progress": 5}
        anime_item = Item.objects.create(
            media_id="52991",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Frieren",
            image="http://example.com/frieren.jpg",
        )
        Anime.objects.create(
            item=anime_item,
            user=self.user,
            status=Status.PLANNING.value,
            progress=0,
        )

        payload = {"event": "media.scrobble"}
        self.processor._handle_anime("52991", 5, payload, self.user)

        anime = Anime.objects.get(item=anime_item, user=self.user)
        self.assertEqual(anime.status, Status.COMPLETED.value)
        self.assertEqual(anime.progress, 5)
        self.assertIsNotNone(anime.end_date)

    @patch("integrations.webhooks.base.app.providers.mal.anime")
    def test_handle_anime_existing_not_played_sets_in_progress(self, mock_mal_anime):
        """Existing PLANNING anime set to IN_PROGRESS when not played."""
        mock_mal_anime.return_value = {
            "title": "Frieren",
            "image": "http://example.com/frieren.jpg",
            "max_progress": 28,
        }
        anime_item = Item.objects.create(
            media_id="52991",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Frieren",
            image="http://example.com/frieren.jpg",
        )
        Anime.objects.create(
            item=anime_item,
            user=self.user,
            status=Status.PLANNING.value,
            progress=0,
        )

        payload = {"event": "media.play"}
        self.processor._handle_anime("52991", 5, payload, self.user)

        anime = Anime.objects.get(item=anime_item, user=self.user)
        self.assertEqual(anime.status, Status.IN_PROGRESS.value)
        self.assertEqual(anime.progress, 4)
        self.assertIsNotNone(anime.start_date)

    @patch("integrations.webhooks.base.app.providers.mal.anime")
    def test_handle_anime_existing_no_changes(self, mock_mal_anime):
        """Existing IN_PROGRESS anime with same progress triggers no save."""
        mock_mal_anime.return_value = {
            "title": "Frieren",
            "image": "http://example.com/frieren.jpg",
            "max_progress": 28,
        }
        anime_item = Item.objects.create(
            media_id="52991",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Frieren",
            image="http://example.com/frieren.jpg",
        )
        instance = Anime.objects.create(
            item=anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=5,
        )
        original_progressed_at = instance.progressed_at

        payload = {"event": "media.scrobble"}
        self.processor._handle_anime("52991", 5, payload, self.user)

        anime = Anime.objects.get(item=anime_item, user=self.user)
        self.assertEqual(anime.progress, 5)
        self.assertEqual(anime.progressed_at, original_progressed_at)
