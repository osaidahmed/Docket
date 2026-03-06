from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import (
    Game,
    MediaTypes,
    Sources,
    Status,
)
from integrations.imports import (
    hltb,
)
from integrations.imports.helpers import MediaImportError, MediaImportUnexpectedError

mock_path = Path(__file__).resolve().parent.parent / "mock_data"
app_mock_path = (
    Path(__file__).resolve().parent.parent.parent.parent / "app" / "tests" / "mock_data"
)


class ImportHowLongToBeat(TestCase):
    """Test importing media from HowLongToBeat CSV."""

    def setUp(self):
        """Create user for the tests."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        with Path(mock_path / "import_hltb_game.csv").open("rb") as file:
            self.import_results = hltb.importer(file, self.user, "new")

    def test_import_counts(self):
        """Test basic counts of imported games."""
        self.assertEqual(Game.objects.filter(user=self.user).count(), 1)

    def test_historical_records(self):
        """Test historical records creation during import."""
        game = Game.objects.filter(user=self.user).first()
        self.assertEqual(game.history.count(), 1)
        self.assertEqual(
            game.history.first().history_date,
            datetime(2024, 2, 9, 15, 54, 48, tzinfo=UTC),
        )

    def test_invalid_file_format(self):
        file = BytesIO(b"\x80\x81\x82")
        with self.assertRaises(MediaImportError):
            hltb.importer(file, self.user, "new")

    def test_format_time(self):
        importer_instance = hltb.HowLongToBeatImporter(
            BytesIO(b""), self.user, "new",
        )
        self.assertIsNone(importer_instance._format_time("--"))
        self.assertEqual(importer_instance._format_time(""), 0)
        self.assertEqual(importer_instance._format_time("8:35:30"), 8 * 60 + 35 + round(30 / 60))
        self.assertEqual(importer_instance._format_time("46:30"), 46 + round(30 / 60))
        self.assertEqual(importer_instance._format_time("32"), round(32 / 60))

    def test_determine_status(self):
        importer_instance = hltb.HowLongToBeatImporter(
            BytesIO(b""), self.user, "new",
        )
        row_completed = {
            "Completed": "X", "Playing": "", "Backlog": "",
            "Replay": "", "Retired": "",
        }
        self.assertEqual(
            importer_instance._determine_status(row_completed),
            Status.COMPLETED.value,
        )

        row_playing = {
            "Completed": "", "Playing": "X", "Backlog": "",
            "Replay": "", "Retired": "",
        }
        self.assertEqual(
            importer_instance._determine_status(row_playing),
            Status.IN_PROGRESS.value,
        )

        row_backlog = {
            "Completed": "", "Playing": "", "Backlog": "X",
            "Replay": "", "Retired": "",
        }
        self.assertEqual(
            importer_instance._determine_status(row_backlog),
            Status.PLANNING.value,
        )

        row_replay = {
            "Completed": "", "Playing": "", "Backlog": "",
            "Replay": "X", "Retired": "",
        }
        self.assertEqual(
            importer_instance._determine_status(row_replay),
            Status.IN_PROGRESS.value,
        )

        row_retired = {
            "Completed": "", "Playing": "", "Backlog": "",
            "Replay": "", "Retired": "X",
        }
        self.assertEqual(
            importer_instance._determine_status(row_retired),
            Status.DROPPED.value,
        )

        row_none = {
            "Completed": "", "Playing": "", "Backlog": "",
            "Replay": "", "Retired": "",
        }
        self.assertEqual(
            importer_instance._determine_status(row_none),
            Status.COMPLETED.value,
        )

    def test_parse_hltb_date(self):
        importer_instance = hltb.HowLongToBeatImporter(
            BytesIO(b""), self.user, "new",
        )
        self.assertIsNone(importer_instance._parse_hltb_date(""))
        result = importer_instance._parse_hltb_date("2024-02-09")
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 2)
        self.assertEqual(result.day, 9)

    @patch("app.providers.services.search")
    def test_search_game_not_found(self, mock_search):
        mock_search.return_value = {"results": []}
        importer_instance = hltb.HowLongToBeatImporter(
            BytesIO(b""), self.user, "new",
        )
        result = importer_instance._search_game({"Title": "Nonexistent"})
        self.assertIsNone(result)

    @patch("app.providers.services.search")
    def test_duplicate_games(self, mock_search):
        mock_search.return_value = {
            "results": [
                {
                    "media_id": "123",
                    "title": "Same Game",
                    "image": "img.jpg",
                },
            ],
        }

        csv_content = (
            '"Title","Platform","Playing","Backlog","Replay","Custom-1","Custom-2","Custom-3",'
            '"Completed","Retired","Retired Notes","Start Date","Completion Date","Playthrough",'
            '"Progress","Main Story","Main Story Notes","Main + Extras","Main + Extras Notes",'
            '"Completionist","Completionist Notes","Speed Any%","Speed Any% Notes",'
            '"Speed 100%","Speed 100% Notes","Co-Op","Multi-Player","General Notes",'
            '"Storefront","Review","Review Notes","Added","Updated"\n'
            'Game A,"PC","","","","","","","X","","","","","First-Play","--","--","","--","",'
            '"--","","--","","--","","--","--","","",70,"",2024-02-09 15:54:48,2024-02-09 15:54:48\n'
            'Game B,"PC","","","","","","","X","","","","","First-Play","--","--","","--","",'
            '"--","","--","","--","","--","--","","",70,"",2024-02-09 15:54:48,2024-02-09 15:54:48\n'
        )
        file = BytesIO(csv_content.encode("utf-8"))

        imported_counts, warnings = hltb.importer(file, self.user, "new")
        self.assertEqual(imported_counts.get(MediaTypes.GAME.value, 0), 0)
        self.assertIn("matched to the same ID", warnings)

    def test_format_notes(self):
        importer_instance = hltb.HowLongToBeatImporter(
            BytesIO(b""), self.user, "new",
        )
        row = {
            "General Notes": "Great game",
            "Review Notes": "",
            "Main Story Notes": "Short campaign",
            "Main + Extras Notes": "",
            "Completionist Notes": "   ",
        }
        result = importer_instance._format_notes(row)
        self.assertIn("General: Great game", result)
        self.assertIn("Main Story: Short campaign", result)
        self.assertNotIn("Review:", result)
