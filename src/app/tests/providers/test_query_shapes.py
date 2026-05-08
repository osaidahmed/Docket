from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from app.providers import anilist


class AnilistAiringScheduleQueryShapeTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("app.providers.anilist.services.api_request")
    def test_query_call_shape(self, mock_api_request):
        mock_api_request.return_value = {
            "data": {"Page": {"airingSchedules": []}},
        }
        anilist.airing_schedule(page=2, per_page=10)

        mock_api_request.assert_called_once()
        args, kwargs = mock_api_request.call_args
        self.assertEqual(args[0], "anilist")
        self.assertEqual(args[1], "POST")
        params = kwargs["params"]
        variables = params["variables"]
        self.assertEqual(variables["page"], 2)
        self.assertEqual(variables["perPage"], 10)
        self.assertIn("start", variables)
        self.assertIn("end", variables)
        self.assertIn("airingSchedules", params["query"])
        self.assertIn("Page(page: $page", params["query"])

    @patch("app.providers.anilist.services.api_request")
    def test_uses_cache_on_second_call(self, mock_api_request):
        mock_api_request.return_value = {
            "data": {"Page": {"airingSchedules": []}},
        }
        anilist.airing_schedule(page=1, per_page=20)
        anilist.airing_schedule(page=1, per_page=20)
        self.assertEqual(mock_api_request.call_count, 1)
