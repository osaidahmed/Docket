from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase

from app.link_providers import http as link_http
from app.link_providers.base import LinkProviderError


class GetSessionTests(SimpleTestCase):
    def test_returns_shared_session(self):
        from app.providers import services

        self.assertIs(link_http.get_session(), services.session)


class HttpVerbWrappersTests(SimpleTestCase):
    @patch("app.link_providers.http.get_session")
    def test_http_get_success_returns_response(self, mock_get_session):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_session.request.return_value = mock_response
        mock_get_session.return_value = mock_session

        result = link_http.http_get("https://x.test/", headers={"X-A": "1"})

        self.assertIs(result, mock_response)
        mock_session.request.assert_called_once_with(
            "GET",
            "https://x.test/",
            headers={"X-A": "1"},
            timeout=link_http.DEFAULT_TIMEOUT,
        )

    @patch("app.link_providers.http.get_session")
    def test_http_post_success(self, mock_get_session):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_session.request.return_value = mock_response
        mock_get_session.return_value = mock_session

        result = link_http.http_post("https://x.test/", json_body={"k": "v"})

        self.assertIs(result, mock_response)
        kwargs = mock_session.request.call_args.kwargs
        self.assertEqual(kwargs["json"], {"k": "v"})

    @patch("app.link_providers.http.get_session")
    def test_http_get_wraps_request_exception(self, mock_get_session):
        mock_session = MagicMock()
        mock_session.request.side_effect = requests.exceptions.ConnectionError("boom")
        mock_get_session.return_value = mock_session

        with self.assertRaises(LinkProviderError):
            link_http.http_get("https://x.test/")

    @patch("app.link_providers.http.get_session")
    def test_http_post_wraps_http_error(self, mock_get_session):
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "500"
        )
        mock_session.request.return_value = mock_response
        mock_get_session.return_value = mock_session

        with self.assertRaises(LinkProviderError):
            link_http.http_post("https://x.test/", json_body={})
