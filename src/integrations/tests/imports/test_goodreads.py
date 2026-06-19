from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import (
    Book,
    MediaTypes,
    Sources,
    Status,
)
from integrations.imports import (
    goodreads,
)
from integrations.imports.helpers import MediaImportError

mock_path = Path(__file__).resolve().parent.parent / "mock_data"
app_mock_path = (
    Path(__file__).resolve().parent.parent.parent.parent / "app" / "tests" / "mock_data"
)


class ImportGoodreads(TestCase):
    """Test importing media from GoodReads CSV."""

    @classmethod
    def setUpTestData(cls):
        """Create user for the tests."""
        cls.user = get_user_model().objects.create_user(
            username="test",
            password="12345",
        )

        def fake_search(media_type, query, page, source=None):
            """Mock book search; empty Goodreads ISBN columns ('=""') yield no hits."""
            del media_type, page, source
            if not query or query.strip('="') == "":
                return {"results": []}
            return {
                "results": [
                    {
                        "title": query,
                        "source": Sources.HARDCOVER.value,
                        "media_id": f"book-{query}",
                        "image": "https://img/book.jpg",
                    },
                ],
            }

        with (
            patch("app.providers.services.search", side_effect=fake_search),
            Path(mock_path / "import_goodreads.csv").open("rb") as file,
        ):
            cls.import_results = goodreads.importer(file, cls.user, "new")

    def test_import_counts(self):
        """Test basic counts of imported books."""
        self.assertEqual(Book.objects.filter(user=self.user).count(), 3)

    def test_historical_records(self):
        """Test historical records creation during import."""
        book = Book.objects.filter(user=self.user).first()
        self.assertEqual(book.history.count(), 1)

    def test_stored_progress(self):
        """Test progress of imported books."""
        read_book = Book.objects.get(status=Status.COMPLETED.value)
        self.assertEqual(read_book.status, Status.COMPLETED.value)
        self.assertEqual(read_book.progress, 994)

        read_book = Book.objects.get(status=Status.IN_PROGRESS.value)
        self.assertEqual(read_book.status, Status.IN_PROGRESS.value)
        self.assertEqual(read_book.progress, 0)


class GoodReadsEdgeCaseTests(TestCase):
    """Test edge cases and error paths in GoodReads importer."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="gr_edge", password="12345"
        )

    def test_unicode_decode_error(self):
        file = BytesIO(b"\x80\x81\x82\x83")
        with self.assertRaises(MediaImportError):
            goodreads.importer(file, self.user, "new")

    @patch("integrations.imports.goodreads.services.search")
    def test_search_returns_single_result(self, mock_search):
        mock_search.return_value = {
            "results": [
                {
                    "media_id": "42",
                    "title": "Found Book",
                    "image": "http://example.com/img.jpg",
                    "source": Sources.HARDCOVER.value,
                },
            ],
        }
        csv_content = (
            b"Title,ISBN13,Exclusive Shelf,My Rating,Number of Pages,"
            b"Private Notes,Date Added,Date Read\n"
            b"Found Book,1234567890123,read,4,200,,2024/01/01,2024/06/01\n"
        )
        file = BytesIO(csv_content)
        counts, _ = goodreads.importer(file, self.user, "new")
        self.assertEqual(counts.get(MediaTypes.BOOK.value, 0), 1)

    @patch("integrations.imports.goodreads.services.search")
    def test_book_not_found(self, mock_search):
        mock_search.return_value = {"results": []}

        csv_content = (
            b"Title,ISBN13,Exclusive Shelf,My Rating,Number of Pages,"
            b"Private Notes,Date Added,Date Read\n"
            b"Nonexistent Book,0000000000000,read,3,100,,"
            b"2024/01/01,2024/06/01\n"
        )
        file = BytesIO(csv_content)
        _, warnings = goodreads.importer(file, self.user, "new")
        self.assertIn("Nonexistent Book", warnings)

    @patch("integrations.imports.goodreads.services.search")
    def test_provider_api_error_warns_and_continues(self, mock_search):
        from app.providers import services as svc

        mock_search.side_effect = svc.ProviderAPIError(
            Sources.HARDCOVER.value,
            type(
                "Err",
                (),
                {
                    "response": type(
                        "R",
                        (),
                        {"status_code": 500, "text": "boom"},
                    )(),
                },
            )(),
        )
        csv_content = (
            b"Title,ISBN13,media_id,Exclusive Shelf,My Rating,Number of Pages,"
            b"Private Notes,Date Added,Date Read\n"
            b"Bad Book,1234,42,read,3,100,,2024/01/01,2024/06/01\n"
        )
        file = BytesIO(csv_content)
        _, warnings = goodreads.importer(file, self.user, "new")
        self.assertIn("Error processing entry", warnings)

    @patch("integrations.imports.goodreads.services.search")
    def test_unexpected_error_raised(self, mock_search):
        from integrations.imports.helpers import MediaImportUnexpectedError

        mock_search.side_effect = ValueError("explode")
        csv_content = (
            b"Title,ISBN13,Exclusive Shelf,My Rating,Number of Pages,"
            b"Private Notes,Date Added,Date Read\n"
            b"X,123,read,3,100,,2024/01/01,2024/06/01\n"
        )
        file = BytesIO(csv_content)
        with self.assertRaises(MediaImportUnexpectedError):
            goodreads.importer(file, self.user, "new")

    @patch("integrations.imports.helpers.should_process_media")
    @patch("integrations.imports.goodreads.services.search")
    def test_should_process_returns_false_skips(self, mock_search, mock_should):
        mock_search.return_value = {
            "results": [
                {
                    "media_id": "9",
                    "title": "Skipped",
                    "image": "http://example.com/i.jpg",
                    "source": Sources.HARDCOVER.value,
                },
            ],
        }
        mock_should.return_value = False
        csv_content = (
            b"Title,ISBN13,Exclusive Shelf,My Rating,Number of Pages,"
            b"Private Notes,Date Added,Date Read\n"
            b"Skipped,1,read,3,100,,2024/01/01,2024/06/01\n"
        )
        file = BytesIO(csv_content)
        counts, _ = goodreads.importer(file, self.user, "new")
        self.assertEqual(counts.get(MediaTypes.BOOK.value, 0), 0)
