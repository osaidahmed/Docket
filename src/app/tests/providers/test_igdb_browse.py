from unittest.mock import MagicMock, patch

import requests
from django.conf import settings
from django.core.cache import cache
from django.test import TestCase

from app.models import MediaTypes, Sources
from app.providers import igdb, services


class IGDBBrowse(TestCase):
    """Test the IGDB browse API calls."""

    required_keys = {"media_id", "media_type", "title", "image", "synopsis"}

    def test_popular(self):
        """Test browsing popular games."""
        response = igdb.browse("popular", 1)

        self.assertGreater(len(response["results"]), 0)
        for item in response["results"]:
            self.assertTrue(all(key in item for key in self.required_keys))
            self.assertEqual(item["media_type"], MediaTypes.GAME.value)

    def test_top_rated(self):
        """Test browsing top rated games."""
        response = igdb.browse("top_rated", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_recent(self):
        """Test browsing recently released games."""
        response = igdb.browse("recent", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_anticipated(self):
        """Test browsing most anticipated games."""
        response = igdb.browse("anticipated", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_pagination(self):
        """Test that pagination returns different pages."""
        page1 = igdb.browse("popular", 1)
        page2 = igdb.browse("popular", 2)

        self.assertEqual(page1["page"], 1)
        self.assertEqual(page2["page"], 2)

    def test_response_format(self):
        """Test that the response has the expected keys."""
        response = igdb.browse("popular", 1)

        self.assertIn("page", response)
        self.assertIn("total_results", response)
        self.assertIn("total_pages", response)
        self.assertIn("results", response)


class IGDBHandleErrorEdgeCases(TestCase):
    """Test IGDB handle_error edge cases."""

    def test_json_decode_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = requests.exceptions.JSONDecodeError(
            "err", "", 0
        )

        error = requests.exceptions.HTTPError("500")
        error.response = mock_response

        with self.assertRaises(services.ProviderAPIError):
            igdb.handle_error(error)

    def test_bad_request_attribute_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {"not_message": "something"}

        error = requests.exceptions.HTTPError("400")
        error.response = mock_response

        with self.assertRaises(services.ProviderAPIError):
            igdb.handle_error(error)

    def test_forbidden_with_message(self):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"message": "forbidden access"}

        error = requests.exceptions.HTTPError("403")
        error.response = mock_response

        with self.assertRaises(services.ProviderAPIError):
            igdb.handle_error(error)

    def test_other_status_code(self):
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.json.return_value = {}

        error = requests.exceptions.HTTPError("503")
        error.response = mock_response

        with self.assertRaises(services.ProviderAPIError):
            igdb.handle_error(error)


class IGDBBrowseFiltered(TestCase):
    """Test IGDB browse_filtered functionality."""

    @patch("app.providers.igdb.get_access_token")
    @patch("app.providers.services.api_request")
    def test_browse_filtered_basic(self, mock_api, mock_token):
        mock_token.return_value = "test_token"
        mock_api.return_value = [
            {
                "name": "BrowseResults",
                "result": [
                    {"id": 1, "name": "Game 1", "cover": {"image_id": "abc"}},
                ],
            },
            {"name": "TotalCount", "count": 1},
        ]

        response = igdb.browse_filtered({}, 1)

        self.assertEqual(len(response["results"]), 1)
        self.assertEqual(response["results"][0]["title"], "Game 1")

    @patch("app.providers.igdb.get_access_token")
    @patch("app.providers.services.api_request")
    def test_browse_filtered_with_all_filters(self, mock_api, mock_token):
        mock_token.return_value = "test_token"
        mock_api.return_value = [
            {"name": "BrowseResults", "result": []},
            {"name": "TotalCount", "count": 0},
        ]

        filters = {
            "genres": "12,14",
            "themes": "1",
            "platforms": "48,49",
            "min_score": "70",
            "sort_by": "rating",
        }

        response = igdb.browse_filtered(filters, 1)

        self.assertEqual(response["results"], [])
        call_data = mock_api.call_args[1]["data"]
        self.assertIn("genres = (12,14)", call_data)
        self.assertIn("themes = (1)", call_data)
        self.assertIn("platforms = (48,49)", call_data)
        self.assertIn("total_rating >= 70.0", call_data)
        self.assertIn("total_rating desc", call_data)

    @patch("app.providers.igdb.get_access_token")
    @patch("app.providers.services.api_request")
    def test_browse_filtered_sort_options(self, mock_api, mock_token):
        mock_token.return_value = "test_token"
        mock_api.return_value = [
            {"name": "BrowseResults", "result": []},
            {"name": "TotalCount", "count": 0},
        ]

        for sort_by, expected_sort in [
            ("date", "first_release_date desc"),
            ("hype", "hypes desc"),
            ("popularity", "total_rating_count desc"),
            ("unknown", "total_rating_count desc"),
        ]:
            with self.subTest(sort_by=sort_by):
                igdb.browse_filtered({"sort_by": sort_by}, 1)
                call_data = mock_api.call_args[1]["data"]
                self.assertIn(expected_sort, call_data)


class IGDBEnumLists(TestCase):
    """Test IGDB enum list functions."""

    def setUp(self):
        cache.delete("igdb_genres")
        cache.delete("igdb_themes")
        cache.delete("igdb_platforms")

    @patch("app.providers.igdb.get_access_token")
    @patch("app.providers.services.api_request")
    def test_get_genres(self, mock_api, mock_token):
        mock_token.return_value = "test_token"
        mock_api.return_value = [
            {"id": 1, "name": "Action"},
            {"id": 2, "name": "RPG"},
        ]

        result = igdb.get_genres()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "Action")

    @patch("app.providers.igdb.get_access_token")
    @patch("app.providers.services.api_request")
    def test_get_themes(self, mock_api, mock_token):
        mock_token.return_value = "test_token"
        mock_api.return_value = [{"id": 1, "name": "Fantasy"}]

        result = igdb.get_themes()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Fantasy")

    @patch("app.providers.igdb.get_access_token")
    @patch("app.providers.services.api_request")
    def test_get_platforms(self, mock_api, mock_token):
        mock_token.return_value = "test_token"
        mock_api.return_value = [{"id": 48, "name": "PlayStation 4"}]

        result = igdb.get_platforms()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "PlayStation 4")


class IGDBBrowseFilterHash(TestCase):
    """Test IGDB _build_browse_filter_hash function."""

    def test_with_filters(self):
        result = igdb._build_browse_filter_hash({"genres": "12", "sort_by": "rating"})
        self.assertIn("genres=12", result)
        self.assertIn("sort_by=rating", result)

    def test_no_filters(self):
        result = igdb._build_browse_filter_hash({})
        self.assertEqual(result, "nofilter")

    def test_empty_values_ignored(self):
        result = igdb._build_browse_filter_hash({"genres": "", "themes": None})
        self.assertEqual(result, "nofilter")


class IGDBHelperEdgeCases(TestCase):
    """Test IGDB helper function edge cases."""

    def test_get_image_url_no_cover(self):
        self.assertEqual(igdb.get_image_url({}), settings.IMG_NONE)

    def test_get_start_date_missing(self):
        self.assertIsNone(igdb.get_start_date({}))

    def test_get_list_missing_field(self):
        self.assertIsNone(igdb.get_list({}, "genres"))

    def test_get_companies_missing(self):
        self.assertIsNone(igdb.get_companies({}))

    def test_get_score_missing(self):
        self.assertIsNone(igdb.get_score({}))

    def test_get_parent_none(self):
        self.assertEqual(igdb.get_parent(None), [])

    def test_get_related_none(self):
        self.assertEqual(igdb.get_related(None), [])

    def test_get_related_with_data(self):
        related = [
            {"id": 1, "name": "DLC 1", "cover": {"image_id": "abc"}},
            {"id": 2, "name": "DLC 2"},
        ]
        result = igdb.get_related(related)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["title"], "DLC 1")
        self.assertEqual(result[1]["image"], settings.IMG_NONE)

    def test_get_parent_with_data(self):
        parent = {"id": 10, "name": "Parent Game", "cover": {"image_id": "xyz"}}
        result = igdb.get_parent(parent)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Parent Game")


class IGDBGameNotFound(TestCase):
    """Test IGDB game not found error."""

    @patch("app.providers.igdb.get_access_token")
    @patch("app.providers.services.api_request")
    def test_game_not_found(self, mock_api, mock_token):
        mock_token.return_value = "test_token"
        mock_api.return_value = []

        with self.assertRaises(services.ProviderAPIError):
            igdb.game("999999999")


def _make_401_error():
    mock_response = MagicMock()
    mock_response.status_code = 401
    error = requests.exceptions.HTTPError("401")
    error.response = mock_response
    return error


class IGDBRetryOnAuthError(TestCase):
    """Test IGDB retry on authentication error."""

    @patch("app.providers.igdb.get_access_token")
    @patch("app.providers.services.api_request")
    def test_search_retries_on_401(self, mock_api, mock_token):
        mock_token.return_value = "new_token"
        mock_api.side_effect = [
            requests.exceptions.HTTPError(response=MagicMock(status_code=401)),
            [
                {
                    "name": "SearchResults",
                    "result": [{"id": 1, "name": "Game", "cover": {"image_id": "x"}}],
                },
                {"name": "TotalCount", "count": 1},
            ],
        ]

        cache.delete(f"search_{Sources.IGDB.value}_{MediaTypes.GAME.value}_RetryTest_1")
        cache.delete(f"{Sources.IGDB.value}_access_token")

        response = igdb.search("RetryTest", 1)

        self.assertEqual(len(response["results"]), 1)

    @patch("app.providers.igdb.get_access_token")
    @patch("app.providers.services.api_request")
    def test_browse_retries_on_401(self, mock_api, mock_token):
        mock_token.return_value = "new_token"
        mock_api.side_effect = [
            requests.exceptions.HTTPError(response=MagicMock(status_code=401)),
            [
                {
                    "name": "BrowseResults",
                    "result": [{"id": 1, "name": "Game", "cover": {"image_id": "x"}}],
                },
                {"name": "TotalCount", "count": 1},
            ],
        ]

        cache.delete(f"browse_{Sources.IGDB.value}_{MediaTypes.GAME.value}_popular_99")
        cache.delete(f"{Sources.IGDB.value}_access_token")

        response = igdb.browse("popular", 99)

        self.assertEqual(len(response["results"]), 1)

    @patch("app.providers.igdb.get_access_token")
    @patch("app.providers.services.api_request")
    def test_browse_filtered_retries_on_401(self, mock_api, mock_token):
        mock_token.return_value = "new_token"
        mock_api.side_effect = [
            requests.exceptions.HTTPError(response=MagicMock(status_code=401)),
            [
                {"name": "BrowseResults", "result": []},
                {"name": "TotalCount", "count": 0},
            ],
        ]

        cache.delete(f"{Sources.IGDB.value}_access_token")

        response = igdb.browse_filtered({"genres": "999"}, 99)

        self.assertEqual(response["results"], [])

    @patch("app.providers.igdb.get_access_token")
    @patch("app.providers.services.api_request")
    def test_get_enum_list_retries_on_401(self, mock_api, mock_token):
        mock_token.return_value = "new_token"
        mock_api.side_effect = [
            requests.exceptions.HTTPError(response=MagicMock(status_code=401)),
            [{"id": 1, "name": "Action"}],
        ]

        cache.delete("igdb_genres_retry_test")
        cache.delete(f"{Sources.IGDB.value}_access_token")

        result = igdb._get_enum_list("genres", "igdb_genres_retry_test")

        self.assertEqual(len(result), 1)

    @patch("app.providers.igdb.get_access_token")
    @patch("app.providers.services.api_request")
    def test_game_retries_on_401(self, mock_api, mock_token):
        mock_token.return_value = "new_token"
        mock_api.side_effect = [
            requests.exceptions.HTTPError(response=MagicMock(status_code=401)),
            [
                {
                    "id": 1942,
                    "name": "Test Game",
                    "url": "https://www.igdb.com/games/test",
                    "game_type": 0,
                    "cover": {"image_id": "abc"},
                    "summary": "A test game",
                    "total_rating": 92.5,
                    "total_rating_count": 1000,
                    "genres": [{"name": "RPG"}],
                    "first_release_date": 1431993600,
                },
            ],
        ]

        cache.delete(f"{Sources.IGDB.value}_{MediaTypes.GAME.value}_9991942")
        cache.delete(f"{Sources.IGDB.value}_access_token")

        response = igdb.game("9991942")

        self.assertEqual(response["title"], "Test Game")

    @patch("app.providers.igdb.get_access_token")
    @patch("app.providers.services.api_request")
    def test_external_game_retries_on_401(self, mock_api, mock_token):
        mock_token.return_value = "new_token"
        mock_api.side_effect = [
            requests.exceptions.HTTPError(response=MagicMock(status_code=401)),
            [{"game": 1942}],
        ]

        cache.delete(f"external_game_{Sources.IGDB.value}_1_999888")
        cache.delete(f"{Sources.IGDB.value}_access_token")

        result = igdb.external_game("999888", igdb.ExternalGameSource.STEAM)

        self.assertEqual(result, 1942)

    @patch("app.providers.igdb.get_access_token")
    @patch("app.providers.services.api_request")
    def test_get_access_token_error(self, _mock_api, mock_token):
        mock_token.side_effect = services.ProviderAPIError(
            Sources.IGDB.value,
            requests.exceptions.HTTPError(
                response=MagicMock(status_code=500, text="error")
            ),
        )

        cache.delete(f"{Sources.IGDB.value}_access_token")

        with self.assertRaises(services.ProviderAPIError):
            igdb.search("ErrorTest", 99)
