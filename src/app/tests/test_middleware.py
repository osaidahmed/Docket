from unittest.mock import MagicMock, patch

from django.test import RequestFactory, TestCase

from app.middleware import ProviderAPIErrorMiddleware
from app.models import Sources
from app.providers.services import ProviderAPIError


class ProviderAPIErrorMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = MagicMock(return_value="ok")
        self.middleware = ProviderAPIErrorMiddleware(self.get_response)

    def test_call_passes_through(self):
        request = self.factory.get("/")
        result = self.middleware(request)
        self.assertEqual(result, "ok")
        self.get_response.assert_called_once_with(request)

    def test_process_exception_handles_provider_error(self):
        request = self.factory.get("/")
        error_response = MagicMock(status_code=500, text="boom")
        exc = ProviderAPIError(Sources.TMDB.value, error_response, "details")
        response = self.middleware.process_exception(request, exc)
        assert response is not None
        self.assertEqual(response.status_code, 500)

    def test_process_exception_returns_none_for_other(self):
        request = self.factory.get("/")
        result = self.middleware.process_exception(request, ValueError("x"))
        self.assertIsNone(result)

    def test_process_exception_renders_500_template_with_context(self):
        request = self.factory.get("/")
        error_response = MagicMock(status_code=500, text="boom")
        exc = ProviderAPIError(Sources.TMDB.value, error_response, "details")
        with patch("app.middleware.render") as mock_render:
            mock_render.return_value = MagicMock(status_code=500)
            self.middleware.process_exception(request, exc)
        mock_render.assert_called_once()
        args, kwargs = mock_render.call_args
        self.assertEqual(args[0], request)
        self.assertEqual(args[1], "500.html")
        context = args[2]
        self.assertEqual(context["provider"], Sources.TMDB.value)
        self.assertIn("details", context["error_message"])
        self.assertEqual(kwargs["status"], 500)

    def test_process_exception_passes_distinct_provider(self):
        request = self.factory.get("/")
        error_response = MagicMock(status_code=502, text="boom")
        exc = ProviderAPIError(Sources.MAL.value, error_response, "rate-limited")
        with patch("app.middleware.render") as mock_render:
            mock_render.return_value = MagicMock(status_code=500)
            self.middleware.process_exception(request, exc)
        context = mock_render.call_args.args[2]
        self.assertEqual(context["provider"], Sources.MAL.value)
        self.assertIn("rate-limited", context["error_message"])

    def test_call_passes_request_object_through(self):
        request = self.factory.get("/some/path")
        self.middleware(request)
        self.get_response.assert_called_once_with(request)
