from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase

from app.models import Item, MediaTypes, Sources
from app.providers.services import ProviderAPIError


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

    @patch("app.management.commands.backfill_synopsis.services.get_media_metadata")
    def test_handles_provider_error(self, mock_metadata):
        error_response = Mock()
        error_response.status_code = 500
        error_response.text = "Server error"
        mock_metadata.side_effect = ProviderAPIError(
            provider=Sources.TMDB.value,
            error=error_response,
            details="boom",
        )
        stderr = StringIO()
        stdout = StringIO()
        call_command("backfill_synopsis", stderr=stderr, stdout=stdout)
        self.assertIn("Error", stderr.getvalue())
        self.assertIn("Errors: 1", stdout.getvalue())


class BackfillEnglishTitlesTests(TestCase):
    """Test the backfill_english_titles management command."""

    def setUp(self):
        self.item = Item.objects.create(
            media_id="437",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Perfect Blue",
            image="http://example.com/image.jpg",
            english_title="",
        )

    @patch(
        "app.management.commands.backfill_english_titles.services.get_media_metadata"
    )
    def test_backfills_empty_english_title(self, mock_metadata):
        """Test that the command populates empty english_title."""
        mock_metadata.return_value = {"english_title": "Perfect Blue EN"}
        call_command("backfill_english_titles", stdout=StringIO())
        self.item.refresh_from_db()
        self.assertEqual(self.item.english_title, "Perfect Blue EN")

    @patch(
        "app.management.commands.backfill_english_titles.services.get_media_metadata"
    )
    def test_skips_non_mal_items(self, mock_metadata):
        """Test that non-MAL items are excluded."""
        tmdb_item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Godfather",
            image="http://example.com/image.jpg",
            english_title="",
        )
        mock_metadata.return_value = {"english_title": "Should not appear"}
        call_command("backfill_english_titles", stdout=StringIO())
        tmdb_item.refresh_from_db()
        self.assertEqual(tmdb_item.english_title, "")

    @patch(
        "app.management.commands.backfill_english_titles.services.get_media_metadata"
    )
    def test_dry_run_does_not_modify(self, mock_metadata):
        """Test that --dry-run shows results without saving."""
        mock_metadata.return_value = {"english_title": "Should not be saved"}
        call_command("backfill_english_titles", "--dry-run", stdout=StringIO())
        self.item.refresh_from_db()
        self.assertEqual(self.item.english_title, "")

    @patch(
        "app.management.commands.backfill_english_titles.services.get_media_metadata"
    )
    def test_skips_when_no_english_title(self, mock_metadata):
        """Test that items with no english_title in metadata are skipped."""
        mock_metadata.return_value = {"english_title": ""}
        call_command("backfill_english_titles", stdout=StringIO())
        self.item.refresh_from_db()
        self.assertEqual(self.item.english_title, "")

    @patch(
        "app.management.commands.backfill_english_titles.services.get_media_metadata"
    )
    def test_handles_provider_error(self, mock_metadata):
        """Test that ProviderAPIError is handled gracefully."""
        error_response = Mock()
        error_response.status_code = 500
        error_response.text = "Server error"
        mock_metadata.side_effect = ProviderAPIError(
            provider=Sources.MAL.value,
            error=error_response,
            details="API error",
        )
        stderr = StringIO()
        call_command("backfill_english_titles", stderr=stderr)
        self.assertIn("Error", stderr.getvalue())
