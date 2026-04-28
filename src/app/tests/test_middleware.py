from unittest.mock import MagicMock

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
