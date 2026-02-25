import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import (
    Anime,
    Manga,
    MediaTypes,
    Status,
)
from integrations.imports import (
    kitsu,
)

mock_path = Path(__file__).resolve().parent.parent / "mock_data"
app_mock_path = (
    Path(__file__).resolve().parent.parent.parent.parent / "app" / "tests" / "mock_data"
)


class ImportKitsu(TestCase):
    """Test importing media from Kitsu."""

    @classmethod
    def setUpTestData(cls):
        """Create user for the tests."""
        cls.user = get_user_model().objects.create_user(
            username="test", password="12345",
        )

        with Path(mock_path / "import_kitsu_anime.json").open() as file:
            cls.sample_anime_response = json.load(file)

        with Path(mock_path / "import_kitsu_manga.json").open() as file:
            cls.sample_manga_response = json.load(file)

        cls.importer = kitsu.KitsuImporter("testuser", cls.user, "new")

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

        # Rewatch instances should have is_rewatch=True
        self.assertEqual(
            Anime.objects.filter(
                item__title="Test Anime 1",
                is_rewatch=True,
            ).count(),
            1,
        )
        self.assertEqual(
            Manga.objects.filter(
                item__title="Test Manga 1",
                is_rewatch=True,
            ).count(),
            1,
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
        self.assertTrue(instance.is_rewatch)

    def test_reconsuming_with_zero_count(self):
        """Test that reconsuming=True with reconsumeCount=0 creates a rewatch."""
        entry = {
            "id": "9999",
            "type": "libraryEntries",
            "attributes": {
                "updatedAt": "2024-04-08T16:16:59.018Z",
                "status": "current",
                "progress": 5,
                "reconsuming": True,
                "reconsumeCount": 0,
                "notes": "",
                "ratingTwenty": 18,
                "startedAt": "2023-08-01T00:00:00.000Z",
                "finishedAt": None,
            },
            "relationships": {
                "anime": {
                    "data": {"type": "anime", "id": "1"},
                },
            },
        }
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

        instances = self.importer.bulk_media[MediaTypes.ANIME.value]
        self.assertEqual(len(instances), 2)

        rewatch = instances[0]
        self.assertTrue(rewatch.is_rewatch)
        self.assertEqual(rewatch.status, Status.COMPLETED.value)

        current = instances[1]
        self.assertFalse(current.is_rewatch)
        self.assertEqual(current.status, Status.IN_PROGRESS.value)
