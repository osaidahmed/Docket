import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import (
    Anime,
    Manga,
    MediaTypes,
    Sources,
    Status,
)
from integrations.imports import (
    kitsu,
)
from integrations.imports.helpers import MediaImportError, MediaImportUnexpectedError

mock_path = Path(__file__).resolve().parent.parent / "mock_data"
app_mock_path = (
    Path(__file__).resolve().parent.parent.parent.parent / "app" / "tests" / "mock_data"
)


class ImportKitsu(TestCase):
    """Test importing media from Kitsu."""

    def setUp(self):
        """Create user for the tests."""
        credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**credentials)

        with Path(mock_path / "import_kitsu_anime.json").open() as file:
            self.sample_anime_response = json.load(file)

        with Path(mock_path / "import_kitsu_manga.json").open() as file:
            self.sample_manga_response = json.load(file)

        self.importer = kitsu.KitsuImporter("testuser", self.user, "new")

    @patch("app.providers.services.api_request")
    def test_get_kitsu_id(self, mock_api_request):
        """Test getting Kitsu ID from username."""
        mock_api_request.return_value = {
            "data": [{"id": "12345"}],
        }
        kitsu_id = self.importer._get_kitsu_id("testuser")
        self.assertEqual(kitsu_id, "12345")

    @patch("app.providers.services.api_request")
    def test_get_media_response(self, mock_api_request):
        """Test getting media response from Kitsu."""
        mock_api_request.side_effect = [
            self.sample_anime_response,
            self.sample_manga_response,
        ]

        imported_counts, warning_message = kitsu.importer(
            "123",
            self.user,
            "new",
        )
        self.assertEqual(imported_counts[MediaTypes.ANIME.value], 6)
        self.assertEqual(imported_counts[MediaTypes.MANGA.value], 6)
        self.assertEqual(warning_message, "")

        self.assertEqual(Anime.objects.count(), 6)
        self.assertEqual(Manga.objects.count(), 6)
        self.assertEqual(
            Anime.objects.get(item__title="Test Anime 2").history.first().history_date,
            datetime(2024, 4, 8, 16, 16, 59, 18000, tzinfo=UTC),
        )

    def test_get_rating(self):
        """Test getting rating from Kitsu."""
        self.assertEqual(self.importer._get_rating(20), 10)
        self.assertEqual(self.importer._get_rating(10), 5)
        self.assertEqual(self.importer._get_rating(1), 0.5)
        self.assertIsNone(self.importer._get_rating(None))

    def test_get_status(self):
        """Test getting status from Kitsu."""
        self.assertEqual(self.importer._get_status("completed"), Status.COMPLETED.value)
        self.assertEqual(self.importer._get_status("current"), Status.IN_PROGRESS.value)
        self.assertEqual(self.importer._get_status("planned"), Status.PLANNING.value)
        self.assertEqual(self.importer._get_status("on_hold"), Status.PAUSED.value)

    def test_process_entry(self):
        """Test processing an entry from Kitsu."""
        entry = self.sample_anime_response["data"][0]
        media_lookup = {
            item["id"]: item
            for item in self.sample_anime_response["included"]
            if item["type"] == "anime"
        }
        mapping_lookup = {
            item["id"]: item
            for item in self.sample_anime_response["included"]
            if item["type"] == "mappings"
        }

        self.importer._process_entry(
            entry,
            MediaTypes.ANIME.value,
            media_lookup,
            mapping_lookup,
        )

        instance = self.importer.bulk_media[MediaTypes.ANIME.value][0]

        self.assertEqual(instance.item.media_id, "1")
        self.assertIsInstance(instance, Anime)
        self.assertEqual(instance.score, 9)
        self.assertEqual(instance.progress, 26)
        self.assertEqual(instance.status, Status.COMPLETED.value)
        self.assertEqual(instance.notes, "Great series!")

    @patch("app.providers.services.api_request")
    def test_get_kitsu_id_not_found(self, mock_api_request):
        mock_api_request.return_value = {"data": []}
        with self.assertRaises(MediaImportError) as ctx:
            self.importer._get_kitsu_id("unknown_user")
        self.assertIn("not found", str(ctx.exception))

    @patch("app.providers.services.api_request")
    def test_get_kitsu_id_multiple_users(self, mock_api_request):
        mock_api_request.return_value = {
            "data": [{"id": "1"}, {"id": "2"}],
        }
        with self.assertRaises(MediaImportError) as ctx:
            self.importer._get_kitsu_id("common_name")
        self.assertIn("Multiple users", str(ctx.exception))

    @patch("app.providers.services.api_request")
    def test_import_with_username_resolution(self, mock_api_request):
        mock_api_request.side_effect = [
            {"data": [{"id": "123"}]},
            self.sample_anime_response,
            self.sample_manga_response,
        ]

        importer_instance = kitsu.KitsuImporter("username_not_id", self.user, "new")
        imported_counts, _ = importer_instance.import_data()
        self.assertEqual(imported_counts[MediaTypes.ANIME.value], 6)

    @patch("integrations.imports.kitsu.KitsuImporter._get_media_response")
    def test_process_media_type_import_error_becomes_warning(self, mock_response):
        mock_response.return_value = {
            "entries": [
                {
                    "attributes": {
                        "status": "completed",
                        "ratingTwenty": 18,
                        "progress": 26,
                        "startedAt": None,
                        "finishedAt": None,
                        "notes": "",
                        "updatedAt": "2024-04-08T16:16:59.018Z",
                        "reconsumeCount": 0,
                        "reconsuming": False,
                    },
                    "relationships": {
                        "anime": {
                            "data": {"id": "1"},
                            "links": {"related": ""},
                        },
                    },
                },
            ],
            "included": [
                {
                    "id": "1",
                    "type": "anime",
                    "attributes": {
                        "canonicalTitle": "No External",
                        "posterImage": {"medium": "img.jpg"},
                        "episodeCount": 26,
                    },
                    "relationships": {
                        "mappings": {"data": []},
                    },
                },
            ],
        }

        self.importer._process_media_type(MediaTypes.ANIME.value)
        self.assertTrue(
            any("No valid external ID" in w for w in self.importer.warnings)
        )

    @patch("integrations.imports.kitsu.KitsuImporter._get_media_response")
    def test_process_media_type_unexpected_error(self, mock_response):
        mock_response.return_value = {
            "entries": [
                {
                    "attributes": {},
                    "relationships": {
                        "anime": {
                            "data": {"id": "1"},
                        },
                    },
                },
            ],
            "included": [
                {
                    "id": "1",
                    "type": "anime",
                    "attributes": {"canonicalTitle": "Test"},
                },
            ],
        }

        with self.assertRaises(MediaImportUnexpectedError):
            self.importer._process_media_type(MediaTypes.ANIME.value)

    @patch("app.providers.services.api_request")
    def test_fetch_media_from_related_url(self, mock_api_request):
        mock_api_request.return_value = {
            "data": {
                "id": "1",
                "attributes": {
                    "canonicalTitle": "Test",
                    "posterImage": {"medium": "img.jpg"},
                },
                "relationships": {
                    "mappings": {"data": [{"id": "m1", "type": "mappings"}]},
                },
            },
            "included": [
                {
                    "id": "m1",
                    "type": "mappings",
                    "attributes": {
                        "externalSite": "myanimelist/anime",
                        "externalId": "1",
                    },
                },
            ],
        }

        relationship = {
            "data": None,
            "links": {"related": "https://kitsu.app/api/edge/anime/1"},
        }

        result_data, result_mappings = self.importer._fetch_media_from_related_url(
            relationship,
            MediaTypes.ANIME.value,
        )
        self.assertEqual(result_data["id"], "1")
        self.assertIn("m1", result_mappings)

    def test_fetch_media_from_related_url_no_url(self):
        relationship = {
            "data": None,
            "links": {"related": ""},
        }

        with self.assertRaises(MediaImportError) as ctx:
            self.importer._fetch_media_from_related_url(
                relationship,
                MediaTypes.ANIME.value,
            )
        self.assertIn("missing media data", str(ctx.exception))

    def test_create_or_get_item_mangaupdates(self):
        kitsu_metadata = {
            "attributes": {
                "canonicalTitle": "Test Manga",
                "posterImage": {"medium": "img.jpg"},
                "chapterCount": 100,
            },
            "relationships": {
                "mappings": {"data": [{"id": "m1", "type": "mappings"}]},
            },
        }
        mapping_lookup = {
            "m1": {
                "id": "m1",
                "attributes": {
                    "externalSite": "mangaupdates",
                    "externalId": "abc",
                },
            },
        }

        item = self.importer._create_or_get_item(
            MediaTypes.MANGA.value,
            kitsu_metadata,
            mapping_lookup,
        )
        self.assertEqual(item.source, Sources.MANGAUPDATES.value)
        self.assertEqual(item.media_id, str(int("abc", 36)))

    def test_create_or_get_item_mangaupdates_old_id(self):
        self.importer.kitsu_mu_mapping["12345"] = "abc"
        kitsu_metadata = {
            "attributes": {
                "canonicalTitle": "Old MU Manga",
                "posterImage": {"medium": "img.jpg"},
                "chapterCount": 50,
            },
            "relationships": {
                "mappings": {"data": [{"id": "m1", "type": "mappings"}]},
            },
        }
        mapping_lookup = {
            "m1": {
                "id": "m1",
                "attributes": {
                    "externalSite": "mangaupdates",
                    "externalId": "12345",
                },
            },
        }

        item = self.importer._create_or_get_item(
            MediaTypes.MANGA.value,
            kitsu_metadata,
            mapping_lookup,
        )
        self.assertEqual(item.source, Sources.MANGAUPDATES.value)

    def test_create_or_get_item_mangaupdates_old_id_not_in_mapping(self):
        kitsu_metadata = {
            "attributes": {
                "canonicalTitle": "Unknown MU Manga",
                "posterImage": {"medium": "img.jpg"},
                "chapterCount": 50,
            },
            "relationships": {
                "mappings": {"data": [{"id": "m1", "type": "mappings"}]},
            },
        }
        mapping_lookup = {
            "m1": {
                "id": "m1",
                "attributes": {
                    "externalSite": "mangaupdates",
                    "externalId": "99999999",
                },
            },
        }

        with self.assertRaises(MediaImportError):
            self.importer._create_or_get_item(
                MediaTypes.MANGA.value,
                kitsu_metadata,
                mapping_lookup,
            )

    def test_create_or_get_item_no_valid_id(self):
        kitsu_metadata = {
            "attributes": {
                "canonicalTitle": "No ID Anime",
                "posterImage": {"medium": "img.jpg"},
                "episodeCount": 26,
            },
            "relationships": {
                "mappings": {"data": []},
            },
        }

        with self.assertRaises(MediaImportError) as ctx:
            self.importer._create_or_get_item(
                MediaTypes.ANIME.value,
                kitsu_metadata,
                {},
            )
        self.assertIn("No valid external ID", str(ctx.exception))

    def test_create_or_get_item_non_digit_mal_id(self):
        kitsu_metadata = {
            "attributes": {
                "canonicalTitle": "Farmagia",
                "posterImage": {"medium": "img.jpg"},
                "episodeCount": 26,
            },
            "relationships": {
                "mappings": {"data": [{"id": "m1", "type": "mappings"}]},
            },
        }
        mapping_lookup = {
            "m1": {
                "id": "m1",
                "attributes": {
                    "externalSite": "myanimelist/anime",
                    "externalId": "anime",
                },
            },
        }

        with self.assertRaises(MediaImportError):
            self.importer._create_or_get_item(
                MediaTypes.ANIME.value,
                kitsu_metadata,
                mapping_lookup,
            )

    def test_get_image_url_no_medium(self):
        media = {
            "attributes": {
                "posterImage": {"original": "original.jpg"},
            },
        }
        result = self.importer._get_image_url(media)
        self.assertEqual(result, "original.jpg")

    def test_get_image_url_no_poster(self):
        media = {"attributes": {"posterImage": {}}}
        result = self.importer._get_image_url(media)
        self.assertEqual(result, settings.IMG_NONE)

    def test_get_status_dropped(self):
        self.assertEqual(self.importer._get_status("dropped"), Status.DROPPED.value)
