from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase

from app.link_providers import http as link_http
from app.link_providers.base import LinkProviderError


def _mock_response(payload=None, *, ok=True):
    response = MagicMock()
    if ok:
        response.json.return_value = payload
    else:
        response.json.side_effect = ValueError("bad json")
    return response


class FlareSolverrParsingTests(SimpleTestCase):
    """Tests for flaresolverr_get response parsing."""

    @patch("app.link_providers.http.requests.post")
    def test_returns_scraped_response_on_ok(self, mock_post):
        mock_post.return_value = _mock_response(
            {
                "status": "ok",
                "solution": {
                    "response": "<html>hello</html>",
                    "status": 200,
                    "url": "https://target.test/page",
                },
            },
        )

        result = link_http.flaresolverr_get("https://target.test/page")

        self.assertEqual(result.html, "<html>hello</html>")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.final_url, "https://target.test/page")

    @patch("app.link_providers.http.requests.post")
    def test_raises_on_error_status(self, mock_post):
        mock_post.return_value = _mock_response(
            {"status": "error", "message": "challenge failed"},
        )

        with self.assertRaises(LinkProviderError):
            link_http.flaresolverr_get("https://target.test/")

    @patch("app.link_providers.http.requests.post")
    def test_raises_on_malformed_json(self, mock_post):
        mock_post.return_value = _mock_response(ok=False)

        with self.assertRaises(LinkProviderError):
            link_http.flaresolverr_get("https://target.test/")

    @patch("app.link_providers.http.requests.post")
    def test_raises_on_transport_error(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("boom")

        with self.assertRaises(LinkProviderError):
            link_http.flaresolverr_get("https://target.test/")

    @patch("app.link_providers.http.requests.post")
    def test_handles_missing_solution_keys(self, mock_post):
        mock_post.return_value = _mock_response({"status": "ok"})

        result = link_http.flaresolverr_get("https://target.test/")

        self.assertEqual(result.html, "")
        self.assertEqual(result.status_code, 0)
        self.assertEqual(result.final_url, "")


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
