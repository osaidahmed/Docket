import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from app.providers import openlibrary
from app.providers.services import ProviderAPIError


def _mock_aiohttp(mock_cls, response_data, status=200):
    """Configure a mocked aiohttp.ClientSession for async tests."""
    mock_response = AsyncMock()
    mock_response.status = status
    mock_response.json = AsyncMock(return_value=response_data)
    mock_get_cm = AsyncMock()
    mock_get_cm.__aenter__.return_value = mock_response
    mock_session = MagicMock()
    mock_session.get.return_value = mock_get_cm
    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__.return_value = mock_session
    mock_cls.return_value = mock_session_cm


class OpenLibraryHelperTests(SimpleTestCase):
    """Test synchronous helper functions in openlibrary module."""

    def test_handle_error_raises(self):
        error = MagicMock()
        error.response.status_code = 500
        error.response.text = "Server error"
        with self.assertRaises(ProviderAPIError):
            openlibrary.handle_error(error)

    def test_get_image_url(self):
        url = openlibrary.get_image_url({"cover_i": 12345})
        self.assertEqual(url, "https://covers.openlibrary.org/b/id/12345-L.jpg")
        self.assertEqual(openlibrary.get_image_url({}), settings.IMG_NONE)

    def test_extract_openlibrary_id(self):
        self.assertIsNone(openlibrary.extract_openlibrary_id(""))
        self.assertIsNone(openlibrary.extract_openlibrary_id(None))
        self.assertEqual(openlibrary.extract_openlibrary_id("/books/OL123M"), "OL123M")

    def test_get_description(self):
        cases = [
            ({"description": "Plain text"}, {}, "Plain text"),
            ({}, {"description": "Work desc"}, "Work desc"),
            ({}, {}, "No synopsis available."),
            (
                {"description": {"type": "/type/text", "value": "Dict val"}},
                {},
                "Dict val",
            ),
            ({"description": "<p>HTML <b>bold</b></p>"}, {}, "HTML bold"),
        ]
        for book_resp, work_resp, expected in cases:
            with self.subTest(expected=expected):
                result = openlibrary.get_description(book_resp, work_resp)
                self.assertEqual(result, expected)

    def test_get_publish_date(self):
        cases = [
            ({"publish_date": "January 19, 2001"}, "2001-01-19"),
            ({"publish_date": "18 March 2025"}, "2025-03-18"),
            ({"publish_date": "2001"}, "2001"),
            ({}, None),
            ({"publish_date": "cop. January 19, 2001"}, "2001-01-19"),
        ]
        for response, expected in cases:
            with self.subTest(response=response):
                self.assertEqual(openlibrary.get_publish_date(response), expected)

    def test_get_cover_image_url(self):
        self.assertEqual(
            openlibrary.get_cover_image_url({"covers": [42]}),
            "https://covers.openlibrary.org/b/id/42-L.jpg",
        )
        self.assertEqual(openlibrary.get_cover_image_url({}), settings.IMG_NONE)

    def test_get_physical_format(self):
        self.assertEqual(
            openlibrary.get_physical_format({"physical_format": "paperback"}),
            "Paperback",
        )
        self.assertIsNone(openlibrary.get_physical_format({}))

    def test_get_subjects_publishers_isbns_none(self):
        self.assertIsNone(openlibrary.get_subjects({}))
        self.assertIsNone(openlibrary.get_publishers({}))
        self.assertIsNone(openlibrary.get_isbns({}))

    def test_get_isbns_combined(self):
        result = openlibrary.get_isbns(
            {"isbn_13": ["978-0-123"], "isbn_10": ["0-123456"]}
        )
        self.assertEqual(result, ["978-0-123", "0-123456"])


class OpenLibraryAsyncTests(TestCase):
    """Test async functions and integration paths."""

    def test_get_ratings_no_work_id(self):
        result = asyncio.run(openlibrary.get_ratings({}))
        self.assertEqual(result, (None, None))

    def test_get_authors_empty(self):
        result = asyncio.run(openlibrary.get_authors({}))
        self.assertIsNone(result)

    @patch("app.providers.openlibrary.fetch_author_data", new_callable=AsyncMock)
    def test_get_authors_with_entries(self, mock_fetch):
        mock_fetch.return_value = {"name": "George Orwell"}
        response = {"authors": [{"author": {"key": "/authors/OL1A"}}]}
        result = asyncio.run(openlibrary.get_authors(response))
        self.assertEqual(result, ["George Orwell"])

    @patch("app.providers.openlibrary.fetch_author_data", new_callable=AsyncMock)
    def test_get_authors_all_fail(self, mock_fetch):
        mock_fetch.return_value = None
        response = {"authors": [{"author": {"key": "/authors/OL1A"}}]}
        result = asyncio.run(openlibrary.get_authors(response))
        self.assertIsNone(result)

    def test_fetch_author_data_non_200(self):
        mock_response = MagicMock()
        mock_response.status = 404
        mock_cm = AsyncMock()
        mock_cm.__aenter__.return_value = mock_response
        mock_session = MagicMock()
        mock_session.get.return_value = mock_cm
        result = asyncio.run(
            openlibrary.fetch_author_data(mock_session, "http://example.com")
        )
        self.assertIsNone(result)

    @patch("app.providers.openlibrary.aiohttp.ClientSession")
    def test_get_editions_success(self, mock_cls):
        _mock_aiohttp(
            mock_cls,
            {
                "entries": [
                    {"key": "/books/OL100M", "title": "Same Book"},
                    {"key": "/books/OL200M", "title": "Other Edition"},
                ],
            },
        )
        result = asyncio.run(
            openlibrary.get_editions(
                {"key": "/books/OL100M"},
                {"key": "/works/OL1W"},
            )
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["media_id"], "OL200M")

    @patch("app.providers.openlibrary.aiohttp.ClientSession")
    def test_get_editions_no_work_id(self, mock_cls):
        _mock_aiohttp(
            mock_cls,
            {"entries": [{"key": "/books/OL200M", "title": "Edition"}]},
        )
        result = asyncio.run(openlibrary.get_editions({"key": "/books/OL100M"}, {}))
        self.assertEqual(len(result), 1)

    @patch("app.providers.openlibrary.aiohttp.ClientSession")
    def test_get_editions_non_200(self, mock_cls):
        _mock_aiohttp(mock_cls, {}, status=500)
        result = asyncio.run(
            openlibrary.get_editions(
                {"key": "/books/OL100M"},
                {"key": "/works/OL1W"},
            )
        )
        self.assertEqual(result, [])

    @patch("app.providers.openlibrary.aiohttp.ClientSession")
    def test_get_ratings_success(self, mock_cls):
        _mock_aiohttp(mock_cls, {"summary": {"average": 4.2, "count": 100}})
        result = asyncio.run(openlibrary.get_ratings({"key": "/works/OL1W"}))
        self.assertEqual(result, (8.4, 100))

    @patch("app.providers.openlibrary.aiohttp.ClientSession")
    def test_get_ratings_no_average(self, mock_cls):
        _mock_aiohttp(mock_cls, {"summary": {"average": None, "count": 0}})
        result = asyncio.run(openlibrary.get_ratings({"key": "/works/OL1W"}))
        self.assertEqual(result, (None, 0))

    @patch("app.providers.openlibrary.get_ratings", new_callable=AsyncMock)
    @patch("app.providers.openlibrary.get_editions", new_callable=AsyncMock)
    @patch("app.providers.openlibrary.get_authors", new_callable=AsyncMock)
    @patch("app.providers.openlibrary.cache")
    @patch("app.providers.services.api_request")
    def test_book_no_works(
        self, mock_api, mock_cache, mock_authors, mock_editions, mock_ratings
    ):
        mock_cache.get.return_value = None
        mock_api.return_value = {"title": "Test Book", "works": []}
        mock_authors.return_value = None
        mock_editions.return_value = []
        mock_ratings.return_value = (None, None)
        result = openlibrary.book("OL123M")
        self.assertEqual(result["title"], "Test Book")
        mock_api.assert_called_once()


class OpenLibraryHTTPErrorAndEdges(TestCase):
    def setUp(self):
        from django.core.cache import cache as _cache

        _cache.clear()

    def test_search_card_no_editions_returns_none(self):
        doc = {"title": "X", "editions": {"docs": []}}
        self.assertIsNone(openlibrary._search_card(doc))

    def test_browse_card_falls_back_to_cover_edition_key(self):
        work = {
            "title": "Y",
            "cover_edition_key": "OL999M",
            "editions": {"docs": []},
        }
        card = openlibrary._browse_card(work)
        assert card is not None
        self.assertEqual(card["media_id"], "OL999M")

    def test_browse_card_returns_none_when_no_id(self):
        work = {"title": "Z", "editions": {"docs": []}}
        self.assertIsNone(openlibrary._browse_card(work))

    def test_estimate_browse_total_partial_page_exact(self):
        results = [{"x": 1}]
        total, exact = openlibrary._estimate_browse_total(results, offset=10)
        self.assertEqual(total, 11)
        self.assertTrue(exact)

    def test_estimate_browse_total_full_page_inexact(self):
        from django.conf import settings

        results = [{"x": i} for i in range(settings.PER_PAGE)]
        total, exact = openlibrary._estimate_browse_total(results, offset=0)
        self.assertGreaterEqual(total, settings.PER_PAGE)
        self.assertFalse(exact)

    def test_get_publishers_present(self):
        result = openlibrary.get_publishers({"publishers": ["A", "B", "C"]})
        self.assertEqual(result, ["A", "B", "C"])

    def test_get_subjects_present(self):
        result = openlibrary.get_subjects({"subjects": ["Sci-Fi", "Drama"]})
        self.assertEqual(result, ["Sci-Fi", "Drama"])

    def test_fetch_author_data_success(self):
        from unittest.mock import AsyncMock

        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"name": "Author One"})

        class _AsyncCM:
            async def __aenter__(self):
                return mock_response

            async def __aexit__(self, *_):
                return False

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=_AsyncCM())

        result = asyncio.run(
            openlibrary.fetch_author_data(mock_session, "http://example.com")
        )
        assert result is not None
        self.assertEqual(result["name"], "Author One")

    @patch("app.providers.services.api_request")
    def test_search_request_exception(self, mock_api):
        from app.tests.providers._http_error_helpers import make_http_error

        mock_api.side_effect = make_http_error(500, {"error": "boom"})
        with self.assertRaises(ProviderAPIError):
            openlibrary.search("anything", 1)

    @patch("app.providers.services.api_request")
    def test_browse_request_exception(self, mock_api):
        from app.tests.providers._http_error_helpers import make_http_error

        mock_api.side_effect = make_http_error(500, {"error": "boom"})
        with self.assertRaises(ProviderAPIError):
            openlibrary.browse("trending", 1)

    @patch("app.providers.openlibrary._fetch_book_and_work")
    def test_book_propagates_fetch_error(self, mock_fetch):
        mock_fetch.side_effect = ProviderAPIError(
            "openlibrary", MagicMock(response=MagicMock(status_code=500, text="x"))
        )
        with self.assertRaises(ProviderAPIError):
            openlibrary.book("OL999M")

    @patch("app.providers.services.api_request")
    def test_fetch_book_and_work_book_request_error(self, mock_api):
        from app.tests.providers._http_error_helpers import make_http_error

        mock_api.side_effect = make_http_error(500, {"error": "boom"})
        with self.assertRaises(ProviderAPIError):
            openlibrary._fetch_book_and_work("OL1M")

    @patch("app.providers.services.api_request")
    def test_fetch_book_and_work_work_request_error(self, mock_api):
        from app.tests.providers._http_error_helpers import make_http_error

        mock_api.side_effect = [
            {"title": "X", "works": [{"key": "/works/OL1W"}]},
            make_http_error(500, {"error": "boom"}),
        ]
        with self.assertRaises(ProviderAPIError):
            openlibrary._fetch_book_and_work("OL1M")
