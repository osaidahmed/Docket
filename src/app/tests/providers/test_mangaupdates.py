from unittest.mock import MagicMock, PropertyMock

import requests
from django.test import SimpleTestCase

from app.providers import services
from app.providers.mangaupdates import handle_error


class HandleErrorTests(SimpleTestCase):
    """Test mangaupdates handle_error function."""

    def _make_http_error(self, status_code, json_data=None, json_raises=None):
        """Create a mock HTTPError with a mocked response."""
        mock_response = MagicMock()
        type(mock_response).status_code = PropertyMock(return_value=status_code)
        if json_raises:
            mock_response.json.side_effect = json_raises
        else:
            mock_response.json.return_value = json_data

        error = requests.exceptions.HTTPError(response=mock_response)
        error.response = mock_response
        return error

    def test_json_decode_error_raises_provider_api_error(self):
        """Test that JSONDecodeError raises ProviderAPIError."""
        error = self._make_http_error(
            status_code=500,
            json_raises=requests.exceptions.JSONDecodeError("msg", "doc", 0),
        )

        with self.assertRaises(services.ProviderAPIError):
            handle_error(error)

    def test_bad_request_with_empty_search_returns_empty_results(self):
        """Test 400 with search error about empty string returns empty results."""
        error = self._make_http_error(
            status_code=400,
            json_data={
                "context": {
                    "search": [
                        {
                            "errors": [
                                '"" must have a length between 1 and 400'
                            ]
                        }
                    ]
                }
            },
        )

        result = handle_error(error)
        self.assertEqual(result, {"results": [], "total_hits": 0})

    def test_bad_request_without_search_error_raises(self):
        """Test 400 without matching search error raises ProviderAPIError."""
        error = self._make_http_error(
            status_code=400,
            json_data={
                "context": {
                    "search": [
                        {"errors": ["some other error"]}
                    ]
                }
            },
        )

        with self.assertRaises(services.ProviderAPIError):
            handle_error(error)

    def test_other_status_code_raises_provider_api_error(self):
        """Test that non-400 errors raise ProviderAPIError."""
        error = self._make_http_error(
            status_code=500,
            json_data={"error": "Internal Server Error"},
        )

        with self.assertRaises(services.ProviderAPIError):
            handle_error(error)
