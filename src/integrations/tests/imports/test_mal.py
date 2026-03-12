import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import (
    Anime,
    Manga,
    Status,
)
from integrations.imports import (
    helpers,
    mal,
)

mock_path = Path(__file__).resolve().parent.parent / "mock_data"
app_mock_path = (
    Path(__file__).resolve().parent.parent.parent.parent / "app" / "tests" / "mock_data"
)


class ImportMAL(TestCase):
    """Test importing media from MyAnimeList."""

    @classmethod
    def setUpTestData(cls):
        """Create user for the tests."""
        cls.user = get_user_model().objects.create_user(
            username="test",
            password="12345",
        )

    @patch("requests.Session.get")
    def test_import_animelist(self, mock_request):
        """Basic test importing anime and manga from MyAnimeList."""
        with Path(mock_path / "import_mal_anime.json").open() as file:
            anime_response = json.load(file)
        with Path(mock_path / "import_mal_manga.json").open() as file:
            manga_response = json.load(file)

        anime_mock = MagicMock()
        anime_mock.json.return_value = anime_response
        manga_mock = MagicMock()
        manga_mock.json.return_value = manga_response
        mock_request.side_effect = [anime_mock, manga_mock]

        mal.importer("bloodthirstiness", self.user, "new")
        self.assertEqual(Anime.objects.filter(user=self.user).count(), 5)
        self.assertEqual(Manga.objects.filter(user=self.user).count(), 3)

        self.assertEqual(
            Anime.objects.filter(
                user=self.user,
                item__title="Ama Gli Animali",
            )
            .first()
            .item.image,
            settings.IMG_NONE,
        )
        self.assertEqual(
            Anime.objects.get(user=self.user, item__title="FLCL").status,
            Status.PAUSED.value,
        )
        self.assertEqual(
            Manga.objects.get(user=self.user, item__title="Fire Punch").score,
            7,
        )

        self.assertEqual(
            Anime.objects.filter(
                user=self.user,
                item__title="Chainsaw Man",
            )
            .first()
            .history.first()
            .history_date,
            datetime(2022, 12, 28, 19, 20, 54, tzinfo=UTC),
        )

        # Rewatch instances should have is_rewatch=True
        self.assertEqual(
            Anime.objects.filter(
                user=self.user,
                item__title="Ama Gli Animali",
                is_rewatch=True,
            ).count(),
            1,
        )
        self.assertEqual(
            Anime.objects.filter(
                user=self.user,
                item__title="Ama Gli Animali",
                is_rewatch=False,
            ).count(),
            1,
        )
        self.assertEqual(
            Manga.objects.filter(
                user=self.user,
                item__title="One Punch-Man",
                is_rewatch=True,
            ).count(),
            1,
        )

    def test_user_not_found(self):
        """Test that an error is raised if the user is not found."""
        self.assertRaises(
            helpers.MediaImportError,
            mal.importer,
            "fhdsufdsu",
            self.user,
            "new",
        )


class MALHelperTests(TestCase):
    """Test MAL importer helper methods."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="mal_helper", password="12345"
        )
        cls.importer = mal.MyAnimeListImporter("testuser", cls.user, "new")

    def test_parse_mal_date_year_only(self):
        result = self.importer._parse_mal_date("2024")
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 1)

    def test_parse_mal_date_year_month(self):
        result = self.importer._parse_mal_date("2024-06")
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 6)
        self.assertEqual(result.day, 1)

    def test_parse_mal_date_none(self):
        self.assertIsNone(self.importer._parse_mal_date(None))

    def test_english_title_equals_main_title(self):
        node = {"title": "Test Title", "alternative_titles": {"en": "Test Title"}}
        self.assertEqual(mal.MyAnimeListImporter._get_english_title(node), "")

    def test_english_title_different(self):
        node = {"title": "Original Title", "alternative_titles": {"en": "EN Title"}}
        self.assertEqual(mal.MyAnimeListImporter._get_english_title(node), "EN Title")

    @patch("requests.Session.get")
    def test_pagination(self, mock_get):
        page1 = MagicMock()
        page1.json.return_value = {
            "data": [
                {
                    "node": {
                        "id": 1,
                        "title": "Anime 1",
                        "main_picture": {"large": "http://example.com/1.jpg"},
                    },
                    "list_status": {
                        "status": "completed",
                        "score": 8,
                        "num_episodes_watched": 12,
                        "num_times_rewatched": 0,
                        "is_rewatching": False,
                        "start_date": None,
                        "finish_date": None,
                        "comments": "",
                        "updated_at": "2024-01-01T00:00:00+00:00",
                    },
                },
            ],
            "paging": {"next": "https://api.myanimelist.net/v2/next"},
        }
        page2 = MagicMock()
        page2.json.return_value = {
            "data": [],
            "paging": {},
        }
        manga_empty = MagicMock()
        manga_empty.json.return_value = {"data": [], "paging": {}}
        mock_get.side_effect = [page1, page2, manga_empty]

        mal.importer("pagtest", self.user, "new")
        self.assertEqual(mock_get.call_count, 3)
