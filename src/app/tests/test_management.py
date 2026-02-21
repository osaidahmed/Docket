from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from app.models import Item, MediaTypes, Sources


class BackfillSynopsisTests(TestCase):
    """Test the backfill_synopsis management command."""

    def setUp(self):
        """Create items with empty synopsis."""
        self.item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
            synopsis="",
        )

    @patch("app.providers.services.get_media_metadata")
    def test_backfills_empty_synopsis(self, mock_metadata):
        """Test that the command populates empty synopsis from providers."""
        mock_metadata.return_value = {
            "synopsis": "A great test movie.",
            "title": "Test Movie",
            "image": "http://example.com/image.jpg",
        }
        call_command("backfill_synopsis", stdout=StringIO())
        self.item.refresh_from_db()
        self.assertEqual(self.item.synopsis, "A great test movie.")

    @patch("app.providers.services.get_media_metadata")
    def test_skips_manual_items(self, mock_metadata):
        """Test that manual items are excluded from backfill."""
        manual_item = Item.objects.create(
            media_id="1",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.MOVIE.value,
            title="Manual Movie",
            image="http://example.com/image.jpg",
            synopsis="",
        )
        mock_metadata.return_value = {
            "synopsis": "Should not appear.",
        }
        call_command("backfill_synopsis", stdout=StringIO())
        manual_item.refresh_from_db()
        self.assertEqual(manual_item.synopsis, "")

    @patch("app.providers.services.get_media_metadata")
    def test_dry_run_does_not_modify(self, mock_metadata):
        """Test that --dry-run shows results without saving."""
        mock_metadata.return_value = {
            "synopsis": "Should not be saved.",
        }
        call_command("backfill_synopsis", "--dry-run", stdout=StringIO())
        self.item.refresh_from_db()
        self.assertEqual(self.item.synopsis, "")

    @patch("app.providers.services.get_media_metadata")
    def test_skips_tv_season_episode_types(self, mock_metadata):
        """Test that tv, season, and episode items are excluded."""
        season_item = Item.objects.create(
            media_id="100",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Some Season",
            image="http://example.com/image.jpg",
            synopsis="",
            season_number=1,
        )
        mock_metadata.return_value = {
            "synopsis": "Fetched synopsis.",
        }
        call_command("backfill_synopsis", stdout=StringIO())
        season_item.refresh_from_db()
        self.assertEqual(season_item.synopsis, "")
