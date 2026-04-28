from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from app.models import MediaTypes, Sources
from app.providers import _mal_helpers, mal, services
from app.tests.providers._http_error_helpers import make_http_error


class MALBrowse(TestCase):
    """Test the MAL browse API calls."""

    required_keys = {"media_id", "media_type", "title", "image", "synopsis"}

    def test_anime_top_rated(self):
        """Test browsing top rated anime."""
        response = mal.browse(MediaTypes.ANIME.value, "all", 1)

        self.assertGreater(len(response["results"]), 0)
        for item in response["results"]:
            self.assertTrue(all(key in item for key in self.required_keys))
            self.assertEqual(item["media_type"], MediaTypes.ANIME.value)

    def test_anime_airing(self):
        """Test browsing currently airing anime."""
        response = mal.browse(MediaTypes.ANIME.value, "airing", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_anime_upcoming(self):
        """Test browsing upcoming anime."""
        response = mal.browse(MediaTypes.ANIME.value, "upcoming", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_anime_bypopularity(self):
        """Test browsing anime by popularity."""
        response = mal.browse(MediaTypes.ANIME.value, "bypopularity", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_manga_top_rated(self):
        """Test browsing top rated manga."""
        response = mal.browse(MediaTypes.MANGA.value, "all", 1)

        self.assertGreater(len(response["results"]), 0)
        for item in response["results"]:
            self.assertTrue(all(key in item for key in self.required_keys))
            self.assertEqual(item["media_type"], MediaTypes.MANGA.value)

    def test_manga_bypopularity(self):
        """Test browsing manga by popularity."""
        response = mal.browse(MediaTypes.MANGA.value, "bypopularity", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_manga_manga(self):
        """Test browsing top manga (manga-only ranking)."""
        response = mal.browse(MediaTypes.MANGA.value, "manga", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_manga_novels(self):
        """Test browsing top novels."""
        response = mal.browse(MediaTypes.MANGA.value, "novels", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_pagination(self):
        """Test that pagination returns different pages."""
        page1 = mal.browse(MediaTypes.ANIME.value, "all", 1)
        page2 = mal.browse(MediaTypes.ANIME.value, "all", 2)

        self.assertEqual(page1["page"], 1)
        self.assertEqual(page2["page"], 2)

    def test_response_format(self):
        """Test that the response has the expected keys."""
        response = mal.browse(MediaTypes.ANIME.value, "all", 1)

        self.assertIn("page", response)
        self.assertIn("total_results", response)
        self.assertIn("total_pages", response)
        self.assertIn("results", response)

    def test_seasonal_browse(self):
        """Test browsing seasonal anime."""
        response = mal.browse_seasonal(2024, "fall", 1)

        self.assertGreater(len(response["results"]), 0)
        for item in response["results"]:
            self.assertTrue(all(key in item for key in self.required_keys))
            self.assertEqual(item["media_type"], MediaTypes.ANIME.value)


class MALHandleErrorBranches(SimpleTestCase):
    def test_forbidden_raises(self):
        with self.assertRaises(services.ProviderAPIError) as ctx:
            mal.handle_error(make_http_error(403, {}))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("API key", str(ctx.exception))

    def test_json_decode_error(self):
        with self.assertRaises(services.ProviderAPIError):
            mal.handle_error(make_http_error(500, text="not json"))

    def test_bad_request_invalid_client_id(self):
        with self.assertRaises(services.ProviderAPIError) as ctx:
            mal.handle_error(make_http_error(400, {"message": "Invalid client id"}))
        self.assertIn("Invalid API key", str(ctx.exception))

    def test_bad_request_invalid_q_returns_empty(self):
        result = mal.handle_error(make_http_error(400, {"message": "invalid q"}))
        self.assertEqual(result, {"data": []})

    def test_bad_request_other_message_raises(self):
        with self.assertRaises(services.ProviderAPIError):
            mal.handle_error(make_http_error(400, {"message": "Some other err"}))

    def test_default_500_raises(self):
        with self.assertRaises(services.ProviderAPIError) as ctx:
            mal.handle_error(make_http_error(500, {"foo": "bar"}))
        self.assertEqual(ctx.exception.status_code, 500)


class MALPaginateResponse(SimpleTestCase):
    def test_total_exact_false_when_next_page_present(self):
        response = {
            "paging": {"next": "https://api.myanimelist.net/v2/anime?offset=20"}
        }
        results = [{"x": i} for i in range(settings.PER_PAGE)]
        data = mal._paginate_response(response, page=1, offset=0, results=results)
        self.assertGreater(data["total_results"], len(results))


class MALCachedBrowseOffset(TestCase):
    def setUp(self):
        cache.clear()

    @patch("app.providers.mal._mal_request")
    def test_offset_for_second_page(self, mock_req):
        mock_req.return_value = {"data": [], "paging": {}}
        mal.browse(MediaTypes.ANIME.value, "all", 2)
        call_kwargs = mock_req.call_args[0][1]
        self.assertEqual(call_kwargs["offset"], settings.PER_PAGE)


class MalHelpersJST(SimpleTestCase):
    def test_full_date(self):
        tz = ZoneInfo("Asia/Tokyo")
        d = _mal_helpers.parse_jst_start_date("2024-05-01", tz)
        self.assertEqual(d, datetime(2024, 5, 1, tzinfo=tz))

    def test_year_month_only(self):
        tz = ZoneInfo("Asia/Tokyo")
        d = _mal_helpers.parse_jst_start_date("2024-05", tz)
        self.assertEqual(d, datetime(2024, 5, 1, tzinfo=tz))


class MalRequestNSFW(TestCase):
    def setUp(self):
        cache.clear()

    @patch.object(settings, "MAL_NSFW", new=True)
    @patch("app.providers.services.api_request")
    def test_nsfw_param_added(self, mock_api):
        mock_api.return_value = {"data": [], "paging": {}}
        mal._mal_request("https://api.myanimelist.net/v2/anime", {"q": "x"})
        params = mock_api.call_args.kwargs["params"]
        self.assertEqual(params["nsfw"], "true")

    @patch("app.providers.services.api_request")
    def test_http_error_dispatches_handle_error(self, mock_api):
        mock_api.side_effect = make_http_error(500, {"foo": "bar"})
        with self.assertRaises(services.ProviderAPIError):
            mal._mal_request("https://api.myanimelist.net/v2/anime", {})

    @patch("app.providers.services.api_request")
    def test_anime_uses_mal_source(self, mock_api):
        mock_api.side_effect = make_http_error(403, {"message": "Forbidden"})
        with self.assertRaises(services.ProviderAPIError) as ctx:
            mal.anime("123")
        self.assertEqual(ctx.exception.provider, Sources.MAL.value)


class MalGettersAndStaleCache(SimpleTestCase):
    def test_get_format_ova(self):
        self.assertEqual(mal.get_format({"media_type": "ova"}), "OVA")

    def test_get_format_ona(self):
        self.assertEqual(mal.get_format({"media_type": "ona"}), "ONA")

    def test_get_format_other(self):
        self.assertEqual(mal.get_format({"media_type": "special"}), "Special")

    def test_get_readable_status_unmapped(self):
        self.assertEqual(
            mal.get_readable_status({"status": "weird_status"}), "Weird Status"
        )

    def test_get_source_missing_key(self):
        self.assertIsNone(mal.get_source({}))

    def test_get_source_present(self):
        self.assertEqual(mal.get_source({"source": "light_novel"}), "Light Novel")

    def test_needs_relationship_refetch_true(self):
        data = {"related": {"related_anime": [{"media_id": "1"}]}}
        self.assertTrue(mal._needs_relationship_refetch(data))

    def test_needs_relationship_refetch_false_when_present(self):
        data = {"related": {"related_anime": [{"relation_type": "sequel"}]}}
        self.assertFalse(mal._needs_relationship_refetch(data))

    def test_needs_relationship_refetch_false_when_empty(self):
        self.assertFalse(mal._needs_relationship_refetch({}))


class MalAnimeStaleCacheRefetch(TestCase):
    def setUp(self):
        cache.clear()

    @patch("app.providers.mal._mal_request")
    def test_stale_cache_triggers_refetch(self, mock_req):
        cache_key = f"{Sources.MAL.value}_{MediaTypes.ANIME.value}_777"
        cache.set(
            cache_key,
            {"related": {"related_anime": [{"media_id": "1"}]}},
        )
        mock_req.return_value = {
            "id": 777,
            "title": "T",
            "alternative_titles": {},
            "main_picture": {"large": "http://x"},
            "media_type": "tv",
            "start_date": "2020-01-01",
            "end_date": "2020-04-01",
            "synopsis": "x",
            "status": "finished_airing",
            "genres": [],
            "mean": 8.0,
            "num_scoring_users": 100,
            "recommendations": [],
            "num_episodes": 12,
            "average_episode_duration": 1440,
            "studios": [{"name": "S"}],
            "start_season": {"season": "winter", "year": 2020},
            "broadcast": None,
            "source": "manga",
            "related_anime": [],
        }
        result = mal.anime("777")
        self.assertEqual(result["title"], "T")
        mock_req.assert_called_once()
