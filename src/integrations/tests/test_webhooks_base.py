from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import (
    TV,
    Anime,
    MediaTypes,
    Movie,
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


class ProcessMovieTests(TestCase):
    """Tests for _process_movie in BaseWebhookProcessor."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="testuser",
            token="test-token",
            plex_usernames="testuser",
        )

    def setUp(self):
        self.processor = PlexWebhookProcessor()
        self.played_payload = {
            "event": "media.scrobble",
            "Account": {"title": "testuser"},
            "Metadata": {"type": "movie", "title": "Test Movie", "Guid": []},
        }

    @patch("integrations.webhooks.base.app.providers.tmdb.movie")
    @patch("app.providers.services.get_media_metadata")
    def test_process_movie_with_tmdb_id(self, mock_meta, mock_movie):
        mock_meta.side_effect = _get_media_metadata_side_effect
        mock_movie.return_value = MOVIE_METADATA
        ids = {"tmdb_id": "603", "imdb_id": None, "tvdb_id": None}
        self.user.anime_enabled = False
        self.user.save()

        self.processor._process_movie(self.played_payload, self.user, ids)

        movie = Movie.objects.get(item__media_id="603", user=self.user)
        self.assertEqual(movie.status, Status.COMPLETED.value)
        self.assertEqual(movie.progress, 1)

    @patch("integrations.webhooks.base.app.providers.tmdb.movie")
    @patch("integrations.webhooks.base.app.providers.tmdb.find")
    @patch("app.providers.services.get_media_metadata")
    def test_process_movie_imdb_fallback(self, mock_meta, mock_find, mock_movie):
        mock_meta.side_effect = _get_media_metadata_side_effect
        mock_find.return_value = {"movie_results": [{"id": "999"}]}
        mock_movie.return_value = {
            "title": "IMDB Fallback Movie",
            "image": "http://example.com/fallback.jpg",
            "max_progress": 1,
        }
        ids = {"tmdb_id": None, "imdb_id": "tt1234567", "tvdb_id": None}
        self.user.anime_enabled = False
        self.user.save()

        self.processor._process_movie(self.played_payload, self.user, ids)

        mock_find.assert_called_once_with("tt1234567", "imdb_id")
        movie = Movie.objects.get(item__media_id="999", user=self.user)
        self.assertEqual(movie.status, Status.COMPLETED.value)

    @patch("integrations.webhooks.base.app.providers.tmdb.find")
    def test_process_movie_imdb_fallback_no_results(self, mock_find):
        mock_find.return_value = {"movie_results": []}
        ids = {"tmdb_id": None, "imdb_id": "tt9999999", "tvdb_id": None}
        self.user.anime_enabled = False
        self.user.save()

        self.processor._process_movie(self.played_payload, self.user, ids)

        self.assertEqual(Movie.objects.count(), 0)

    def test_process_movie_no_ids(self):
        ids = {"tmdb_id": None, "imdb_id": None, "tvdb_id": None}
        self.user.anime_enabled = False
        self.user.save()

        self.processor._process_movie(self.played_payload, self.user, ids)

        self.assertEqual(Movie.objects.count(), 0)

    @patch("integrations.webhooks.base.app.providers.mal.anime")
    def test_process_movie_imdb_detects_anime(self, mock_mal_anime):
        """IMDB-only movie detected as anime via IMDB mapping."""
        mapping_data = {
            "1": {"imdb_id": "tt1234567", "mal_id": 500},
        }
        mock_mal_anime.return_value = {
            "title": "Anime Movie",
            "image": "http://example.com/anime.jpg",
            "max_progress": 1,
        }

        ids = {"tmdb_id": None, "imdb_id": "tt1234567", "tvdb_id": None}
        self.user.anime_enabled = True
        self.user.save()

        with patch.object(
            self.processor, "_fetch_mapping_data", return_value=mapping_data
        ):
            self.processor._process_movie(self.played_payload, self.user, ids)

        anime = Anime.objects.get(item__media_id="500", user=self.user)
        self.assertEqual(anime.status, Status.COMPLETED.value)
        self.assertEqual(anime.progress, 1)
        self.assertEqual(Movie.objects.count(), 0)

    @patch("integrations.webhooks.base.app.providers.mal.anime")
    def test_process_movie_tmdb_detects_anime(self, mock_mal_anime):
        """TMDB movie detected as anime via TMDB movie mapping."""
        mapping_data = {
            "1": {"tmdb_movie_id": "10494", "mal_id": 437},
        }
        mock_mal_anime.return_value = {
            "title": "Perfect Blue",
            "image": "http://example.com/perfect_blue.jpg",
            "max_progress": 1,
        }

        ids = {"tmdb_id": "10494", "imdb_id": None, "tvdb_id": None}
        self.user.anime_enabled = True
        self.user.save()

        with patch.object(
            self.processor, "_fetch_mapping_data", return_value=mapping_data
        ):
            self.processor._process_movie(self.played_payload, self.user, ids)

        anime = Anime.objects.get(item__media_id="437", user=self.user)
        self.assertEqual(anime.status, Status.COMPLETED.value)
        self.assertEqual(Movie.objects.count(), 0)


class ProcessTVNoTVDBTests(TestCase):
    """Tests for _process_tv when no TVDB ID is found."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="testuser",
            token="test-token",
            plex_usernames="testuser",
        )

    def setUp(self):
        self.processor = PlexWebhookProcessor()

    @patch("integrations.webhooks.base.app.providers.tmdb.find")
    @patch("integrations.webhooks.base.app.providers.tmdb.tv_with_seasons")
    def test_process_tv_no_tvdb_id(self, mock_tv_with_seasons, mock_find):
        """_process_tv returns early when tvdb_id is None."""
        mock_find.return_value = {
            "tv_episode_results": [
                {"show_id": "1668", "season_number": 1, "episode_number": 1}
            ],
        }
        mock_tv_with_seasons.return_value = {"tvdb_id": None}

        ids = {"tmdb_id": None, "imdb_id": "tt0583459", "tvdb_id": None}
        self.processor._process_tv(
            {"event": "media.scrobble"},
            self.user,
            ids,
        )

        self.assertEqual(TV.objects.count(), 0)


class ProcessMediaRoutingTests(TestCase):
    """Tests for _process_media routing logic."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="testuser",
            token="test-token",
            plex_usernames="testuser",
        )

    def setUp(self):
        self.processor = PlexWebhookProcessor()

    def test_unsupported_media_type_ignored(self):
        payload = {
            "event": "media.scrobble",
            "Account": {"title": "testuser"},
            "Metadata": {"type": "photo", "title": "My Photo", "Guid": []},
        }
        ids = {"tmdb_id": "123", "imdb_id": None, "tvdb_id": None}

        self.processor._process_media(payload, self.user, ids)

        self.assertEqual(Movie.objects.count(), 0)
        self.assertEqual(TV.objects.count(), 0)


class GetMalIdFromTvdbOffsetTests(TestCase):
    """Tests for _get_mal_id_from_tvdb with episode offset matching."""

    def setUp(self):
        self.processor = PlexWebhookProcessor()

    def test_single_entry_match(self):
        mapping_data = {
            "1": {
                "tvdb_id": 100,
                "tvdb_season": 1,
                "mal_id": 200,
                "tvdb_epoffset": 0,
            },
        }
        mal_id, offset = self.processor._get_mal_id_from_tvdb(mapping_data, 100, 1, 5)
        self.assertEqual(mal_id, 200)
        self.assertEqual(offset, 5)

    def test_multiple_entries_offset_matching(self):
        mapping_data = {
            "1": {
                "tvdb_id": 100,
                "tvdb_season": 1,
                "mal_id": 200,
                "tvdb_epoffset": 0,
            },
            "2": {
                "tvdb_id": 100,
                "tvdb_season": 1,
                "mal_id": 300,
                "tvdb_epoffset": 12,
            },
        }
        mal_id, offset = self.processor._get_mal_id_from_tvdb(mapping_data, 100, 1, 15)
        self.assertEqual(mal_id, 300)
        self.assertEqual(offset, 3)

    def test_first_entry_selected_for_early_episode(self):
        mapping_data = {
            "1": {
                "tvdb_id": 100,
                "tvdb_season": 1,
                "mal_id": 200,
                "tvdb_epoffset": 0,
            },
            "2": {
                "tvdb_id": 100,
                "tvdb_season": 1,
                "mal_id": 300,
                "tvdb_epoffset": 12,
            },
        }
        mal_id, offset = self.processor._get_mal_id_from_tvdb(mapping_data, 100, 1, 5)
        self.assertEqual(mal_id, 200)
        self.assertEqual(offset, 5)

    def test_comma_separated_mal_id(self):
        mapping_data = {
            "1": {
                "tvdb_id": 100,
                "tvdb_season": 1,
                "mal_id": "123,456,789",
                "tvdb_epoffset": 0,
            },
        }
        mal_id, offset = self.processor._get_mal_id_from_tvdb(mapping_data, 100, 1, 1)
        self.assertEqual(mal_id, "123")
        self.assertEqual(offset, 1)
