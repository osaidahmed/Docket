from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from app.models import (
    TV,
    MediaTypes,
    Movie,
    Status,
)
from app.providers.services import ProviderAPIError
from integrations.imports import (
    imdb,
)
from integrations.imports.helpers import MediaImportError

mock_path = Path(__file__).resolve().parent.parent / "mock_data"
app_mock_path = (
    Path(__file__).resolve().parent.parent.parent.parent / "app" / "tests" / "mock_data"
)


class ImportIMDB(TestCase):
    """Test importing media from IMDB CSV."""

    def setUp(self):
        """Create user for the tests."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        with Path(mock_path / "import_imdb.csv").open("rb") as file:
            self.import_results = imdb.importer(file, self.user, "new")

    def test_import_imdb_csv(self):
        """Test importing movies and TV shows from IMDB CSV."""
        imported_counts, warnings = self.import_results

        self.assertEqual(imported_counts[MediaTypes.MOVIE.value], 5)
        self.assertEqual(imported_counts[MediaTypes.TV.value], 2)

        self.assertIn(
            "The Last of Us: Unsupported title type 'Video Game' - skipped",
            warnings,
        )

        movie_1 = Movie.objects.get(item__title="The Shawshank Redemption")
        self.assertEqual(movie_1.score, 9)
        self.assertEqual(movie_1.status, Status.COMPLETED.value)
        self.assertEqual(movie_1.progress, 1)
        self.assertEqual(
            movie_1.end_date,
            datetime(2025, 2, 3, tzinfo=timezone.get_current_timezone()),
        )

        game_of_thrones = TV.objects.get(item__title="Game of Thrones")
        self.assertEqual(game_of_thrones.status, Status.PLANNING.value)

    def test_extract_imdb_id(self):
        """Test IMDB ID extraction and formatting."""
        importer_instance = imdb.IMDBImporter(None, self.user, "new")

        self.assertEqual(
            importer_instance._extract_imdb_id({"Const": "tt0111161"}),
            "tt0111161",
        )
        self.assertEqual(
            importer_instance._extract_imdb_id({"Const": "0111161"}),
            "tt0111161",
        )
        self.assertIsNone(importer_instance._extract_imdb_id({"Const": ""}))
        self.assertIsNone(importer_instance._extract_imdb_id({"Const": "invalid"}))

    def test_parse_rating(self):
        """Test rating parsing."""
        importer_instance = imdb.IMDBImporter(None, self.user, "new")

        # Valid ratings
        self.assertEqual(importer_instance._parse_rating("8.5"), 8.5)
        self.assertEqual(importer_instance._parse_rating("10"), 10.0)
        self.assertEqual(importer_instance._parse_rating("1"), 1.0)

        self.assertIsNone(importer_instance._parse_rating(""))
        self.assertIsNone(importer_instance._parse_rating("invalid"))
        self.assertIsNone(importer_instance._parse_rating("11"))
        self.assertIsNone(importer_instance._parse_rating("0"))

    def test_parse_date_rated(self):
        """Test date parsing."""
        importer_instance = imdb.IMDBImporter(None, self.user, "new")

        # Valid date
        parsed_date = importer_instance._parse_date("2023-01-15")
        self.assertEqual(parsed_date.date(), datetime(2023, 1, 15, tzinfo=UTC).date())

        self.assertIsNone(importer_instance._parse_date(""))
        self.assertIsNone(importer_instance._parse_date("invalid-date"))

    def test_is_supported_type(self):
        """Test title type support checking."""
        importer_instance = imdb.IMDBImporter(None, self.user, "new")
        type_tests = {
            ("Movie", True),
            ("TV Series", True),
            ("Short", True),
            ("TV Mini Series", True),
            ("TV Movie", True),
            ("TV Special", True),
            ("Video", True),
            ("TV Episode", False),
            ("TV Short", False),
            ("Video Game", False),
            ("Music Video", False),
            ("Podcast Series", False),
            ("Podcast Episode", False),
        }

        for media_type, result in type_tests:
            self.assertEqual(importer_instance._is_supported_type(media_type), result)

    @patch("app.providers.tmdb.find")
    def test_lookup_in_tmdb_not_found(self, mock_tmdb_find):
        """Test TMDB lookup when no results are found."""
        mock_tmdb_find.return_value = {}

        importer_instance = imdb.IMDBImporter(None, self.user, "new")
        result = importer_instance._lookup_in_tmdb("tt9999999", "movie")

        self.assertIsNone(result)

    def test_duplicate_handling(self):
        """Test handling of duplicate IMDB entries that map to same TMDB ID."""
        imported_counts, warnings = self.import_results

        # There are six movies in the test CSV, one of them is a duplicate
        # The test CSV file contains a duplicate of The Dark Knight
        self.assertEqual(imported_counts.get(MediaTypes.MOVIE.value, 0), 5)

        self.assertIn("They were matched to the same TMDB ID 155", warnings)

    def test_invalid_file_format(self):
        file = BytesIO(b"\x80\x81\x82")
        with self.assertRaises(MediaImportError):
            imdb.importer(file, self.user, "new")

    @patch("app.providers.tmdb.find")
    def test_first_pass_no_imdb_id(self, mock_find):
        csv_content = (
            "Position,Const,Created,Modified,Description,Title,Original Title,"
            "URL,Title Type,IMDb Rating,Runtime (mins),Year,Genres,Num Votes,"
            "Release Date,Directors,Your Rating,Date Rated\n"
            "1,,2023-07-09,2024-02-01,,No ID Movie,No ID Movie,"
            "https://www.imdb.com/title/tt0000000/,Movie,9,120,2023,"
            '"Action",1000,2023-01-01,Director,,\n'
        )
        file = BytesIO(csv_content.encode("utf-8"))
        _, warnings = imdb.importer(file, self.user, "new")
        self.assertIn("Invalid or missing IMDB ID", warnings)

    @patch("app.providers.tmdb.find")
    def test_first_pass_unknown_title_type(self, mock_find):
        csv_content = (
            "Position,Const,Created,Modified,Description,Title,Original Title,"
            "URL,Title Type,IMDb Rating,Runtime (mins),Year,Genres,Num Votes,"
            "Release Date,Directors,Your Rating,Date Rated\n"
            "1,tt1234567,2023-07-09,2024-02-01,,Unknown Type,Unknown Type,"
            "https://www.imdb.com/title/tt1234567/,FutureType,9,120,2023,"
            '"Action",1000,2023-01-01,Director,,\n'
        )
        file = BytesIO(csv_content.encode("utf-8"))
        _, warnings = imdb.importer(file, self.user, "new")
        self.assertIn("Unknown title type", warnings)

    @patch("app.providers.tmdb.find")
    def test_first_pass_tmdb_not_found(self, mock_find):
        mock_find.return_value = {}
        csv_content = (
            "Position,Const,Created,Modified,Description,Title,Original Title,"
            "URL,Title Type,IMDb Rating,Runtime (mins),Year,Genres,Num Votes,"
            "Release Date,Directors,Your Rating,Date Rated\n"
            "1,tt9999999,2023-07-09,2024-02-01,,Missing Movie,Missing Movie,"
            "https://www.imdb.com/title/tt9999999/,Movie,9,120,2023,"
            '"Action",1000,2023-01-01,Director,,\n'
        )
        file = BytesIO(csv_content.encode("utf-8"))
        _, warnings = imdb.importer(file, self.user, "new")
        self.assertIn("Couldn't find a match", warnings)

    @patch("app.providers.tmdb.find")
    def test_lookup_in_tmdb_provider_error(self, mock_find):
        error = Mock()
        error.response.status_code = 500
        error.response.text = "Server error"
        mock_find.side_effect = ProviderAPIError("TMDB", error)

        importer_instance = imdb.IMDBImporter(None, self.user, "new")
        result = importer_instance._lookup_in_tmdb("tt1234567", "Movie")
        self.assertIsNone(result)

    @patch("app.providers.tmdb.find")
    def test_lookup_tv_in_tmdb(self, mock_find):
        mock_find.return_value = {
            "tv_results": [
                {
                    "id": 456,
                    "name": "Test Show",
                    "poster_path": "/poster.jpg",
                },
            ],
        }

        importer_instance = imdb.IMDBImporter(None, self.user, "new")
        result = importer_instance._lookup_in_tmdb("tt1234567", "TV Series")
        self.assertIsNotNone(result)
        self.assertEqual(result["media_id"], 456)
        self.assertEqual(result["media_type"], MediaTypes.TV.value)
