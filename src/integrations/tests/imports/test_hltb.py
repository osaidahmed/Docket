from datetime import UTC, datetime
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import (
    Game,
)
from integrations.imports import (
    hltb,
)

mock_path = Path(__file__).resolve().parent.parent / "mock_data"
app_mock_path = (
    Path(__file__).resolve().parent.parent.parent.parent / "app" / "tests" / "mock_data"
)


class ImportHowLongToBeat(TestCase):
    """Test importing media from HowLongToBeat CSV."""

    @classmethod
    def setUpTestData(cls):
        """Create user for the tests."""
        cls.user = get_user_model().objects.create_user(
            username="test",
            password="12345",
        )
        with Path(mock_path / "import_hltb_game.csv").open("rb") as file:
            cls.import_results = hltb.importer(file, cls.user, "new")

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
