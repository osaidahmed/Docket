import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from app.models import TV, Anime, Episode, Item, MediaTypes, Movie, Season, Sources, Status
from integrations.webhooks.base import BaseWebhookProcessor
from integrations.webhooks.jellyfin import JellyfinWebhookProcessor


class JellyfinWebhookTests(TestCase):
    """Tests for Jellyfin webhook."""

    @classmethod
    def setUpTestData(cls):
        """Set up test data."""
        cls.user = get_user_model().objects.create_superuser(
            username="testuser",
            token="test-token",
        )
        cls.url = reverse("jellyfin_webhook", kwargs={"token": "test-token"})

    def setUp(self):
        self.client = Client()

    def test_invalid_token(self):
        """Test webhook with invalid token returns 401."""
        url = reverse("jellyfin_webhook", kwargs={"token": "invalid-token"})
        response = self.client.post(url, data={}, content_type="application/json")
        self.assertEqual(response.status_code, 401)

    def test_tv_episode_mark_played(self):
        """Test webhook handles TV episode mark played event."""
        payload = {
            "Event": "Stop",
            "Item": {
                "Type": "Episode",
                "Name": "The One Where Monica Gets a Roommate",
                "ProviderIds": {
                    "Tvdb": "303821",
                    "Imdb": "tt0583459",
                },
                "SeriesName": "Friends",
                "ParentIndexNumber": 1,
                "IndexNumber": 1,
                "UserData": {"Played": True},
            },
        }

        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        # Verify objects were created
        tv_item = Item.objects.get(media_type=MediaTypes.TV.value, media_id="1668")
        self.assertEqual(tv_item.title, "Friends")

        tv = TV.objects.get(item=tv_item, user=self.user)
        self.assertEqual(tv.status, Status.IN_PROGRESS.value)

        season = Season.objects.get(
            item__media_id="1668",
            item__season_number=1,
        )
        self.assertEqual(season.status, Status.IN_PROGRESS.value)

        episode = Episode.objects.get(
            item__media_id="1668",
            item__season_number=1,
            item__episode_number=1,
        )
        self.assertIsNotNone(episode.end_date)

    def test_movie_mark_played(self):
        """Test webhook handles movie mark played event."""
        payload = {
            "Event": "Stop",
            "Item": {
                "Name": "The Matrix",
                "ProductionYear": 1999,
                "Type": "Movie",
                "ProviderIds": {"Tmdb": "603"},
                "UserData": {"Played": True},
            },
        }

        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        # Verify movie was created and marked as completed
        movie = Movie.objects.get(
            item__media_id="603",
            user=self.user,
        )
        self.assertEqual(movie.status, Status.COMPLETED.value)
        self.assertEqual(movie.progress, 1)

    def test_anime_movie_mark_played(self):
        """Test webhook handles movie mark played event."""
        payload = {
            "Event": "Stop",
            "Item": {
                "Name": "Perfect Blue",
                "ProductionYear": 1997,
                "Type": "Movie",
                "ProviderIds": {"Imdb": "tt0156887"},
                "UserData": {"Played": True},
            },
        }

        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        # Verify movie was created and marked as completed
        movie = Anime.objects.get(
            item__media_id="437",
            user=self.user,
        )
        self.assertEqual(movie.status, Status.COMPLETED.value)
        self.assertEqual(movie.progress, 1)

    def test_anime_episode_mark_played(self):
        """Test webhook handles anime episode mark played event."""
        payload = {
            "Event": "Stop",
            "Item": {
                "Type": "Episode",
                "Name": "The Journey's End",
                "ProviderIds": {
                    "Tvdb": "9350138",
                    "Imdb": "tt23861604",
                },
                "UserData": {"Played": True},
                "SeriesName": "Frieren: Beyond Journey's End",
                "ParentIndexNumber": 1,
                "IndexNumber": 1,
            },
        }

        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)

        # Verify anime was created and marked as in progress
        anime = Anime.objects.get(
            item__media_id="52991",
            user=self.user,
        )
        self.assertEqual(anime.status, Status.IN_PROGRESS.value)
        self.assertEqual(anime.progress, 1)

    def test_ignored_event_types(self):
        """Test webhook ignores irrelevant event types."""
        payload = {
            "Event": "SomeOtherEvent",
            "Item": {
                "Type": "Movie",
                "ProviderIds": {"Tmdb": "12345"},
                "UserData": {"Played": True},
            },
        }

        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Movie.objects.count(), 0)

    def test_missing_tmdb_id(self):
        """Test webhook handles missing TMDB ID gracefully."""
        payload = {
            "Event": "Stop",
            "Item": {
                "Type": "Movie",
                "ProviderIds": {},
                "UserData": {"Played": True},
            },
        }

        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Movie.objects.count(), 0)

    def test_mark_unplayed(self):
        """Test webhook handles not finished events."""
        payload = {
            "Event": "Stop",
            "Item": {
                "Name": "The Matrix",
                "ProductionYear": 1999,
                "Type": "Movie",
                "ProviderIds": {"Tmdb": "603"},
                "UserData": {"Played": False},
            },
        }
        self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        movie = Movie.objects.get(item__media_id="603")
        self.assertEqual(movie.progress, 0)
        self.assertEqual(movie.status, Status.IN_PROGRESS.value)

    def test_repeated_watch(self):
        """Test webhook handles repeated watches."""
        payload = {
            "Event": "Stop",
            "Item": {
                "Type": "Movie",
                "ProductionYear": 1999,
                "Name": "The Matrix",
                "ProviderIds": {"Tmdb": "603"},
                "UserData": {"Played": True},
            },
        }

        # First watch
        self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        # Second watch
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        movie = Movie.objects.filter(item__media_id="603")
        self.assertEqual(movie.count(), 2)
        self.assertEqual(movie[0].status, Status.COMPLETED.value)
        self.assertEqual(movie[1].status, Status.COMPLETED.value)

    def test_extract_external_ids(self):
        """Test extracting external IDs from provider payload."""
        payload = {
            "Event": "Stop",
            "Item": {
                "Type": "Movie",
                "Name": "The Matrix",
                "ProductionYear": 1999,
                "ProviderIds": {
                    "Tmdb": "603",
                    "Tvdb": "169",
                },
            },
        }

        expected = {
            "tmdb_id": "603",
            "imdb_id": None,
            "tvdb_id": "169",
        }

        result = JellyfinWebhookProcessor()._extract_external_ids(payload)
        if result != expected:
            msg = f"Expected {expected}, got {result}"
            raise AssertionError(msg)

    def test_extract_external_ids_empty(self):
        """Test handling empty provider payload."""
        payload = {
            "Event": "Stop",
            "Item": {
                "Type": "Movie",
                "Name": "The Matrix",
                "ProductionYear": 1999,
                "ProviderIds": {},
            },
        }

        expected = {
            "tmdb_id": None,
            "imdb_id": None,
            "tvdb_id": None,
        }

        result = JellyfinWebhookProcessor()._extract_external_ids(payload)
        if result != expected:
            msg = f"Expected {expected}, got {result}"
            raise AssertionError(msg)

    def test_extract_external_ids_missing(self):
        """Test handling missing ProviderIds."""
        payload = {
            "Event": "Stop",
            "Item": {
                "Type": "Movie",
                "Name": "The Matrix",
                "ProductionYear": 1999,
            },
        }
        expected = {
            "tmdb_id": None,
            "imdb_id": None,
            "tvdb_id": None,
        }

        result = JellyfinWebhookProcessor()._extract_external_ids(payload)
        if result != expected:
            msg = f"Expected {expected}, got {result}"
            raise AssertionError(msg)

    @patch("integrations.webhooks.base.app.providers.tmdb.find")
    def test_movie_imdb_only_no_tmdb_match(self, mock_find):
        mock_find.return_value = {"movie_results": []}
        payload = {
            "Event": "Stop",
            "Item": {
                "Type": "Movie",
                "Name": "Unknown Movie",
                "ProductionYear": 2020,
                "ProviderIds": {"Imdb": "tt9999999"},
                "UserData": {"Played": True},
            },
        }
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Movie.objects.count(), 0)

    @patch("integrations.webhooks.base.app.providers.tmdb.find")
    def test_tv_episode_no_tmdb_match(self, mock_find):
        mock_find.return_value = {"tv_episode_results": []}
        payload = {
            "Event": "Stop",
            "Item": {
                "Type": "Episode",
                "Name": "Unknown Episode",
                "ProviderIds": {"Imdb": "tt9999999", "Tvdb": "9999999"},
                "SeriesName": "Unknown Show",
                "ParentIndexNumber": 1,
                "IndexNumber": 1,
                "UserData": {"Played": True},
            },
        }
        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(TV.objects.count(), 0)

    def test_anime_episode_same_progress_no_change(self):
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
            status=Status.IN_PROGRESS.value,
            progress=1,
        )

        payload = {
            "Event": "Stop",
            "Item": {
                "Type": "Episode",
                "Name": "The Journey's End",
                "ProviderIds": {
                    "Tvdb": "9350138",
                    "Imdb": "tt23861604",
                },
                "UserData": {"Played": True},
                "SeriesName": "Frieren: Beyond Journey's End",
                "ParentIndexNumber": 1,
                "IndexNumber": 1,
            },
        }

        response = self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        anime = Anime.objects.get(item=anime_item, user=self.user)
        self.assertEqual(anime.progress, 1)


class BaseWebhookProcessorTests(TestCase):
    def test_abstract_methods_raise_not_implemented(self):
        processor = BaseWebhookProcessor()
        with self.assertRaises(NotImplementedError):
            processor.process_payload({}, None)
        with self.assertRaises(NotImplementedError):
            processor._is_supported_event("test")
        with self.assertRaises(NotImplementedError):
            processor._is_played({})
        with self.assertRaises(NotImplementedError):
            processor._extract_external_ids({})
        with self.assertRaises(NotImplementedError):
            processor._get_media_type({})
        with self.assertRaises(NotImplementedError):
            processor._get_media_title({})

    def test_parse_mal_id_single(self):
        processor = BaseWebhookProcessor()
        self.assertEqual(processor._parse_mal_id(12345), 12345)

    def test_parse_mal_id_comma_separated(self):
        processor = BaseWebhookProcessor()
        self.assertEqual(processor._parse_mal_id("123,456,789"), "123")

    def test_parse_mal_id_string_no_comma(self):
        processor = BaseWebhookProcessor()
        self.assertEqual(processor._parse_mal_id("12345"), "12345")

    def test_get_mal_id_from_tvdb_no_match(self):
        processor = BaseWebhookProcessor()
        mapping_data = {
            "1": {
                "tvdb_id": 999,
                "tvdb_season": 1,
                "mal_id": 100,
                "tvdb_epoffset": 0,
            },
        }
        mal_id, offset = processor._get_mal_id_from_tvdb(
            mapping_data, 888, 1, 1
        )
        self.assertIsNone(mal_id)
        self.assertIsNone(offset)

    def test_get_mal_id_from_tvdb_episode_out_of_range(self):
        processor = BaseWebhookProcessor()
        mapping_data = {
            "1": {
                "tvdb_id": 100,
                "tvdb_season": 1,
                "mal_id": 200,
                "tvdb_epoffset": 10,
            },
        }
        mal_id, offset = processor._get_mal_id_from_tvdb(
            mapping_data, 100, 1, 5
        )
        self.assertIsNone(mal_id)
        self.assertIsNone(offset)

    def test_get_mal_id_from_tmdb_movie_no_match(self):
        processor = BaseWebhookProcessor()
        mapping_data = {
            "1": {"tmdb_movie_id": 999, "mal_id": 100},
        }
        result = processor._get_mal_id_from_tmdb_movie(mapping_data, 888)
        self.assertIsNone(result)

    def test_get_mal_id_from_imdb_no_match(self):
        processor = BaseWebhookProcessor()
        mapping_data = {
            "1": {"imdb_id": "tt999", "mal_id": 100},
        }
        result = processor._get_mal_id_from_imdb(mapping_data, "tt888")
        self.assertIsNone(result)
