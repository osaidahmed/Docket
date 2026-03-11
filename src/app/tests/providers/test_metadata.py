import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import requests
from django.conf import settings
from django.core.cache import cache
from django.test import TestCase

from app.models import Episode, Item, MediaTypes, Sources
from app.providers import (
    comicvine,
    hardcover,
    igdb,
    mal,
    mangaupdates,
    manual,
    openlibrary,
    services,
    tmdb,
)

mock_path = Path(__file__).resolve().parent.parent / "mock_data"


class MALMetadataTests(TestCase):
    """Test MAL provider metadata for anime and manga."""

    def test_anime(self):
        response = mal.anime("1")
        self.assertEqual(response["title"], "Cowboy Bebop")
        self.assertEqual(response["details"]["start_date"], "1998-04-03")
        self.assertEqual(response["details"]["status"], "Finished")
        self.assertEqual(response["details"]["episodes"], 26)

    @patch("requests.Session.get")
    def test_anime_unknown(self, mock_data):
        with Path(mock_path / "metadata_anime_unknown.json").open() as file:
            anime_response = json.load(file)
        mock_data.return_value.json.return_value = anime_response
        mock_data.return_value.status_code = 200

        response = mal.anime("0")
        self.assertEqual(response["title"], "Unknown Example")
        self.assertEqual(response["image"], settings.IMG_NONE)
        self.assertEqual(response["synopsis"], "No synopsis available.")
        self.assertEqual(response["details"]["episodes"], None)
        self.assertEqual(response["details"]["runtime"], None)

    def test_manga(self):
        response = mal.manga("1")
        self.assertEqual(response["title"], "Monster")
        self.assertEqual(response["details"]["start_date"], "1994-12-05")
        self.assertEqual(response["details"]["status"], "Finished")
        self.assertEqual(response["details"]["number_of_chapters"], 162)


class MangaUpdatesMetadataTests(TestCase):
    """Test MangaUpdates provider metadata."""

    def test_mangaupdates(self):
        response = mangaupdates.manga("72274276213")
        self.assertEqual(response["title"], "Monster")
        self.assertEqual(response["details"]["year"], "1994")
        self.assertEqual(response["details"]["format"], "Manga")


class TMDBMetadataTests(TestCase):
    """Test TMDB provider metadata for movies and TV shows."""

    def test_tv(self):
        response = tmdb.tv("1396")
        self.assertEqual(response["title"], "Breaking Bad")
        self.assertEqual(response["details"]["first_air_date"], "2008-01-20")
        self.assertEqual(response["details"]["status"], "Ended")
        self.assertEqual(response["details"]["episodes"], 62)

    def test_process_episodes(self):
        Item.objects.create(
            media_id="5",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Process Episodes Test",
            image="http://example.com/process.jpg",
        )

        Item.objects.create(
            media_id="5",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Process Episodes Test",
            image="http://example.com/process_s1.jpg",
            season_number=1,
        )

        for i in range(1, 4):
            Item.objects.create(
                media_id="5",
                source=Sources.TMDB.value,
                media_type=MediaTypes.EPISODE.value,
                title=f"Process Episode {i}",
                image=f"http://example.com/process_s1e{i}.jpg",
                season_number=1,
                episode_number=i,
            )

        season_metadata = {
            "media_id": "1396",  # Breaking Bad
            "season_number": 1,
            "episodes": [
                {
                    "episode_number": 1,
                    "air_date": "2008-01-20",
                    "still_path": "/path/to/still1.jpg",
                    "name": "Pilot",
                    "overview": "overview of the episode",
                    "runtime": 23,
                },
                {
                    "episode_number": 2,
                    "air_date": "2008-01-27",
                    "still_path": "/path/to/still2.jpg",
                    "name": "Cat's in the Bag...",
                    "overview": "overview of the episode",
                    "runtime": 23,
                },
                {
                    "episode_number": 3,
                    "air_date": "2008-02-10",
                    "still_path": "/path/to/still3.jpg",
                    "name": "...And the Bag's in the River",
                    "overview": "overview of the episode",
                    "runtime": 23,
                },
            ],
        }
        episode_item_1 = Item.objects.get(
            media_id="5",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            season_number=1,
            episode_number=1,
        )
        episode_1 = Episode(item=episode_item_1)

        episode_item_2 = Item.objects.get(
            media_id="5",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            season_number=1,
            episode_number=2,
        )
        episode_2 = Episode(item=episode_item_2)

        episodes_in_db = [episode_1, episode_2]

        result = tmdb.process_episodes(season_metadata, episodes_in_db)

        self.assertEqual(len(result), 3)

        self.assertEqual(result[0]["episode_number"], 1)
        self.assertEqual(result[0]["title"], "Pilot")
        self.assertEqual(result[0]["air_date"], "2008-01-20")
        self.assertTrue(result[0]["history"], [episode_1])

        self.assertEqual(result[1]["episode_number"], 2)
        self.assertEqual(result[1]["title"], "Cat's in the Bag...")
        self.assertEqual(result[1]["air_date"], "2008-01-27")
        self.assertTrue(result[1]["history"], [episode_2])

        self.assertEqual(result[2]["episode_number"], 3)
        self.assertEqual(result[2]["title"], "...And the Bag's in the River")
        self.assertEqual(result[2]["air_date"], "2008-02-10")
        self.assertFalse(result[2]["history"], [])

    @patch("app.providers.tmdb.tv_with_seasons")
    def test_episode(self, mock_tv_with_seasons):
        mock_tv_with_seasons.return_value = {
            "title": "Breaking Bad",
            "season/1": {
                "title": "Breaking Bad",
                "season_title": "Season 1",
                "episodes": [
                    {
                        "episode_number": 1,
                        "name": "Pilot",
                        "still_path": "/path/to/still1.jpg",
                    },
                    {
                        "episode_number": 2,
                        "name": "Cat's in the Bag...",
                        "still_path": "/path/to/still2.jpg",
                    },
                ],
            },
        }

        result = tmdb.episode("1396", "1", "1")

        self.assertEqual(result["title"], "Breaking Bad")
        self.assertEqual(result["season_title"], "Season 1")
        self.assertEqual(result["episode_title"], "Pilot")
        self.assertEqual(result["image"], tmdb.get_image_url("/path/to/still1.jpg"))

        with self.assertRaises(services.ProviderAPIError) as cm:
            tmdb.episode("1396", "1", "3")

        self.assertIn("Episode 3 not found in season 1", str(cm.exception))
        self.assertIn("The Movie Database with ID 1396", str(cm.exception))

        mock_tv_with_seasons.assert_called_with("1396", ["1"])

    def test_find_next_episode(self):
        episodes_metadata = [
            {"episode_number": 1, "title": "Episode 1"},
            {"episode_number": 2, "title": "Episode 2"},
            {"episode_number": 3, "title": "Episode 3"},
        ]

        next_episode = tmdb.find_next_episode(1, episodes_metadata)
        self.assertEqual(next_episode, 2)

        next_episode = tmdb.find_next_episode(3, episodes_metadata)
        self.assertIsNone(next_episode)

        next_episode = tmdb.find_next_episode(5, episodes_metadata)
        self.assertIsNone(next_episode)

    def test_movie(self):
        response = tmdb.movie("10494")
        self.assertEqual(response["title"], "Perfect Blue")
        self.assertEqual(response["details"]["release_date"], "1998-02-28")
        self.assertEqual(response["details"]["status"], "Released")

    @patch("requests.Session.get")
    def test_movie_unknown(self, mock_data):
        with Path(mock_path / "metadata_movie_unknown.json").open() as file:
            movie_response = json.load(file)
        mock_data.return_value.json.return_value = movie_response
        mock_data.return_value.status_code = 200

        response = tmdb.movie("0")
        self.assertEqual(response["title"], "Unknown Movie")
        self.assertEqual(response["image"], settings.IMG_NONE)
        self.assertEqual(response["synopsis"], "No synopsis available.")
        self.assertEqual(response["details"]["release_date"], None)
        self.assertEqual(response["details"]["runtime"], None)
        self.assertEqual(response["genres"], None)
        self.assertEqual(response["details"]["studios"], None)
        self.assertEqual(response["details"]["country"], None)
        self.assertEqual(response["details"]["languages"], None)


class IGDBMetadataTests(TestCase):
    """Test IGDB provider metadata for games."""

    def test_game(self):
        response = igdb.game("1942")
        self.assertEqual(response["title"], "The Witcher 3: Wild Hunt")
        self.assertEqual(response["details"]["format"], "Main game")
        self.assertEqual(response["details"]["release_date"], "2015-05-19")
        self.assertEqual(
            response["details"]["themes"],
            ["Action", "Fantasy", "Open world"],
        )

    def test_external_game_steam(self):
        igdb_game_id = igdb.external_game("292030", igdb.ExternalGameSource.STEAM)
        self.assertEqual(igdb_game_id, 1942)

    def test_external_game_not_found(self):
        igdb_game_id = igdb.external_game("999999999", igdb.ExternalGameSource.STEAM)
        self.assertIsNone(igdb_game_id)


class OpenLibraryMetadataTests(TestCase):
    """Test OpenLibrary provider metadata for books."""

    def setUp(self):
        cache.delete("openlibrary_book_OL21733390M")

    @patch("app.providers.services.api_request")
    @patch("app.providers.openlibrary.get_ratings", new_callable=AsyncMock)
    @patch("app.providers.openlibrary.get_editions", new_callable=AsyncMock)
    @patch("app.providers.openlibrary.get_authors", new_callable=AsyncMock)
    def test_book(self, mock_authors, mock_editions, mock_ratings, mock_api):
        mock_api.side_effect = [
            {
                "title": "Nineteen Eighty-Four",
                "works": [{"key": "/works/OL1168083W"}],
                "number_of_pages": 328,
            },
            {
                "title": "Nineteen Eighty-Four",
                "subjects": ["Dystopian fiction"],
            },
        ]

        mock_authors.return_value = ["George Orwell"]
        mock_editions.return_value = {
            "format": "Paperback",
            "publisher": "Penguin",
            "isbn": [],
        }
        mock_ratings.return_value = (8.5, 1000)

        response = openlibrary.book("OL21733390M")
        self.assertEqual(response["title"], "Nineteen Eighty-Four")
        self.assertEqual(response["details"]["author"], ["George Orwell"])


class HardcoverMetadataTests(TestCase):
    """Test Hardcover provider metadata and helper functions."""

    def test_book(self):
        response = hardcover.book("377193")
        self.assertEqual(response["title"], "The Great Gatsby")
        self.assertEqual(response["details"]["author"], "F. Scott Fitzgerald")
        self.assertIn("Fiction", response["genres"])
        self.assertIn("Young Adult", response["genres"])
        self.assertIn("Classics", response["genres"])
        self.assertAlmostEqual(response["score"], 7.4, delta=0.1)

    def test_book_unknown(self):
        response = hardcover.book("1265528")
        self.assertEqual(response["title"], "MiNRS")
        self.assertEqual(response["details"]["author"], "Kevin Sylvester")
        self.assertEqual(response["details"]["publish_date"], "2015-09-22")
        self.assertEqual(response["synopsis"], "No synopsis available.")
        self.assertEqual(response["details"]["format"], "Unknown")
        self.assertIsNone(response["genres"])

    def test_get_tags(self):
        tags_data = [{"tag": "Science Fiction"}, {"tag": "Fantasy"}]
        result = hardcover.get_tags(tags_data)
        self.assertEqual(result, ["Science Fiction", "Fantasy"])
        self.assertIsNone(hardcover.get_tags(None))

    def test_get_ratings(self):
        self.assertEqual(hardcover.get_ratings(4.5), 9.0)
        self.assertIsNone(hardcover.get_ratings(None))

    def test_get_edition_details(self):
        edition_data = {
            "edition_format": "Paperback",
            "isbn_13": "9781234567890",
            "isbn_10": "1234567890",
            "publisher": {"name": "Test Publisher"},
        }

        result = hardcover.get_edition_details(edition_data)
        self.assertEqual(result["format"], "Paperback")
        self.assertEqual(result["publisher"], "Test Publisher")
        self.assertEqual(result["isbn"], ["1234567890", "9781234567890"])

        self.assertEqual(hardcover.get_edition_details(None), {})

        no_publisher = {
            "edition_format": "Paperback",
            "isbn_13": "9781234567890",
        }
        result = hardcover.get_edition_details(no_publisher)
        self.assertEqual(result["publisher"], None)

    def test_handle_error_unauthorized(self):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "Invalid API key"}

        error = requests.exceptions.HTTPError("401 Unauthorized")
        error.response = mock_response

        with self.assertRaises(services.ProviderAPIError) as cm:
            hardcover.handle_error(error)

        self.assertEqual(cm.exception.provider, Sources.HARDCOVER.value)

    def test_handle_error_server(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"error": "Server error"}

        error = requests.exceptions.HTTPError("500 Server Error")
        error.response = mock_response

        with self.assertRaises(services.ProviderAPIError) as cm:
            hardcover.handle_error(error)

        self.assertEqual(cm.exception.provider, Sources.HARDCOVER.value)

    def test_handle_error_json_decode(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = requests.exceptions.JSONDecodeError(
            "Invalid JSON",
            "",
            0,
        )

        error = requests.exceptions.HTTPError("500 Server Error")
        error.response = mock_response

        with self.assertRaises(services.ProviderAPIError) as cm:
            hardcover.handle_error(error)

        self.assertEqual(cm.exception.provider, Sources.HARDCOVER.value)


class ComicVineMetadataTests(TestCase):
    """Test Comic Vine provider metadata."""

    def test_comic(self):
        response = comicvine.comic("155969")
        self.assertEqual(response["title"], "Ultimate Spider-Man")


class ManualMetadataTests(TestCase):
    """Test manual provider metadata for user-created entries."""

    def test_tv(self):
        Item.objects.create(
            media_id="1",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.TV.value,
            title="Manual TV Show",
            image="http://example.com/manual.jpg",
        )

        Item.objects.create(
            media_id="1",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.SEASON.value,
            title="Manual TV Show",
            image="http://example.com/manual_s1.jpg",
            season_number=1,
        )

        for i in range(1, 4):
            Item.objects.create(
                media_id="1",
                source=Sources.MANUAL.value,
                media_type=MediaTypes.EPISODE.value,
                title=f"Episode {i}",
                image=f"http://example.com/manual_s1e{i}.jpg",
                season_number=1,
                episode_number=i,
            )

        response = manual.metadata("1", MediaTypes.TV.value)

        self.assertEqual(response["title"], "Manual TV Show")
        self.assertEqual(response["media_id"], "1")
        self.assertEqual(response["source"], Sources.MANUAL.value)
        self.assertEqual(response["media_type"], MediaTypes.TV.value)
        self.assertEqual(response["synopsis"], "No synopsis available.")

        self.assertEqual(response["details"]["seasons"], 1)
        self.assertEqual(response["details"]["episodes"], 3)
        self.assertEqual(response["max_progress"], 3)
        self.assertEqual(len(response["related"]["seasons"]), 1)

        season_data = response["season/1"]
        self.assertEqual(season_data["season_number"], 1)
        self.assertEqual(season_data["max_progress"], 3)
        self.assertEqual(len(season_data["episodes"]), 3)

    def test_movie(self):
        Item.objects.create(
            media_id="2",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.MOVIE.value,
            title="Manual Movie",
            image="http://example.com/manual_movie.jpg",
        )

        response = manual.metadata("2", MediaTypes.MOVIE.value)

        self.assertEqual(response["title"], "Manual Movie")
        self.assertEqual(response["media_id"], "2")
        self.assertEqual(response["source"], Sources.MANUAL.value)
        self.assertEqual(response["media_type"], MediaTypes.MOVIE.value)
        self.assertEqual(response["synopsis"], "No synopsis available.")
        self.assertEqual(response["max_progress"], 1)

    def test_season(self):
        Item.objects.create(
            media_id="3",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.TV.value,
            title="Another TV Show",
            image="http://example.com/another.jpg",
        )

        Item.objects.create(
            media_id="3",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.SEASON.value,
            title="Another TV Show",
            image="http://example.com/another_s1.jpg",
            season_number=1,
        )

        for i in range(1, 3):
            Item.objects.create(
                media_id="3",
                source=Sources.MANUAL.value,
                media_type=MediaTypes.EPISODE.value,
                title=f"Episode {i}",
                image=f"http://example.com/another_s1e{i}.jpg",
                season_number=1,
                episode_number=i,
            )

        response = manual.season("3", 1)

        self.assertEqual(response["season_number"], 1)
        self.assertEqual(response["title"], "Another TV Show")
        self.assertEqual(response["season_title"], "Season 1")
        self.assertEqual(response["max_progress"], 2)
        self.assertEqual(len(response["episodes"]), 2)

    def test_episode(self):
        Item.objects.create(
            media_id="4",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.TV.value,
            title="Third TV Show",
            image="http://example.com/third.jpg",
        )

        Item.objects.create(
            media_id="4",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.SEASON.value,
            title="Third TV Show",
            image="http://example.com/third_s1.jpg",
            season_number=1,
        )

        Item.objects.create(
            media_id="4",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.EPISODE.value,
            title="Special Episode",
            image="http://example.com/third_s1e1.jpg",
            season_number=1,
            episode_number=1,
        )

        response = manual.episode("4", 1, 1)

        self.assertEqual(response["media_type"], MediaTypes.EPISODE.value)
        self.assertEqual(response["title"], "Third TV Show")
        self.assertEqual(response["season_title"], "Season 1")
        self.assertEqual(response["episode_title"], "Special Episode")

        result = manual.episode("4", 1, 2)
        self.assertIsNone(result)

    def test_process_episodes(self):
        Item.objects.create(
            media_id="5",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.TV.value,
            title="Process Episodes Test",
            image="http://example.com/process.jpg",
        )

        Item.objects.create(
            media_id="5",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.SEASON.value,
            title="Process Episodes Test",
            image="http://example.com/process_s1.jpg",
            season_number=1,
        )

        for i in range(1, 4):
            Item.objects.create(
                media_id="5",
                source=Sources.MANUAL.value,
                media_type=MediaTypes.EPISODE.value,
                title=f"Process Episode {i}",
                image=f"http://example.com/process_s1e{i}.jpg",
                season_number=1,
                episode_number=i,
            )

        season_metadata = {
            "season_number": 1,
            "episodes": [
                {
                    "media_id": "5",
                    "episode_number": 1,
                    "air_date": "2025-01-01",
                    "image": "http://example.com/process_s1e1.jpg",
                    "title": "Process Episode 1",
                },
                {
                    "media_id": "5",
                    "episode_number": 2,
                    "air_date": "2025-01-08",
                    "image": "http://example.com/process_s1e2.jpg",
                    "title": "Process Episode 2",
                },
                {
                    "media_id": "5",
                    "episode_number": 3,
                    "air_date": "2025-01-15",
                    "image": "http://example.com/process_s1e3.jpg",
                    "title": "Process Episode 3",
                },
            ],
        }

        ep_item1 = Item.objects.get(
            media_id="5",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.EPISODE.value,
            season_number=1,
            episode_number=1,
        )
        ep_item2 = Item.objects.get(
            media_id="5",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.EPISODE.value,
            season_number=1,
            episode_number=2,
        )

        episode_1 = Episode(item=ep_item1)
        episode_2 = Episode(item=ep_item2)

        episodes_in_db = [episode_1, episode_2]

        result = manual.process_episodes(season_metadata, episodes_in_db)

        self.assertEqual(len(result), 3)

        self.assertEqual(result[0]["episode_number"], 1)
        self.assertEqual(result[0]["title"], "Process Episode 1")
        self.assertEqual(result[0]["air_date"], "2025-01-01")
        self.assertTrue(result[0]["history"], [episode_1])

        self.assertEqual(result[1]["episode_number"], 2)
        self.assertEqual(result[1]["title"], "Process Episode 2")
        self.assertEqual(result[1]["air_date"], "2025-01-08")
        self.assertTrue(result[0]["history"], [episode_2])

        self.assertEqual(result[2]["episode_number"], 3)
        self.assertEqual(result[2]["title"], "Process Episode 3")
        self.assertEqual(result[2]["air_date"], "2025-01-15")
        self.assertFalse(result[2]["history"], [])
