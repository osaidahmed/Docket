from unittest.mock import MagicMock, patch

import requests
from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from app.models import MediaTypes
from app.providers import tmdb
from app.providers.services import ProviderAPIError
from app.tests.providers._http_error_helpers import make_http_error


class TMDBHelperTests(SimpleTestCase):
    """Test TMDB helper and utility functions."""

    def test_build_discover_params_movie_year(self):
        params = tmdb._build_discover_params(
            MediaTypes.MOVIE.value, {"year": "2024"}, 1
        )
        self.assertIn("primary_release_year", params)
        self.assertEqual(params["primary_release_year"], "2024")

    def test_build_discover_params_tv_year(self):
        params = tmdb._build_discover_params(MediaTypes.TV.value, {"year": "2024"}, 1)
        self.assertIn("first_air_date_year", params)
        self.assertEqual(params["first_air_date_year"], "2024")

    def test_build_discover_params_genres_and_score(self):
        params = tmdb._build_discover_params(
            MediaTypes.MOVIE.value,
            {"genres": "28,12", "min_score": "7"},
            1,
        )
        self.assertEqual(params["with_genres"], "28,12")
        self.assertEqual(params["vote_average.gte"], "7")
        self.assertEqual(params["vote_count.gte"], 50)

    @patch.object(settings, "TMDB_NSFW", new=True)
    def test_build_discover_params_nsfw(self):
        params = tmdb._build_discover_params(MediaTypes.MOVIE.value, {}, 1)
        self.assertEqual(params["include_adult"], "true")

    def test_build_discover_filter_hash_nofilter(self):
        result = tmdb._build_discover_filter_hash(MediaTypes.MOVIE.value, {})
        self.assertEqual(result, "nofilter")

    def test_build_discover_filter_hash_with_filters(self):
        result = tmdb._build_discover_filter_hash(
            MediaTypes.MOVIE.value, {"genres": "28", "year": "2024"}
        )
        self.assertIn("genres=28", result)
        self.assertIn("year=2024", result)

    def test_handle_error_json_decode(self):
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.json.side_effect = requests.exceptions.JSONDecodeError(
            "msg", "doc", 0
        )
        error = MagicMock()
        error.response = error_response
        with self.assertRaises(ProviderAPIError):
            tmdb.handle_error(error)

    def test_handle_error_unauthorized_with_message(self):
        error_response = MagicMock()
        error_response.status_code = requests.codes.unauthorized
        error_response.json.return_value = {"status_message": "Invalid API key."}
        error = MagicMock()
        error.response = error_response
        with self.assertRaises(ProviderAPIError) as ctx:
            tmdb.handle_error(error)
        self.assertIn("Invalid API key", str(ctx.exception))

    def test_get_collection_unknown_release_date(self):
        collection = {
            "parts": [
                {
                    "id": 1,
                    "title": "Movie A",
                    "poster_path": "/a.jpg",
                    "release_date": None,
                },
                {
                    "id": 2,
                    "title": "Movie B",
                    "poster_path": "/b.jpg",
                    "release_date": "2020-01-01",
                },
            ],
        }
        result = tmdb.get_collection(collection)
        self.assertEqual(result[0]["title"], "Movie B")
        self.assertEqual(result[1]["title"], "Movie A")

    def test_fetch_movie_collection_no_collection(self):
        self.assertEqual(tmdb._fetch_movie_collection({}), {})
        self.assertEqual(
            tmdb._fetch_movie_collection({"belongs_to_collection": {"id": None}}),
            {},
        )

    @patch("app.providers.services.api_request")
    def test_fetch_movie_collection_http_error(self, mock_api):
        error = requests.exceptions.HTTPError()
        error.response = MagicMock(status_code=500, text="err")
        mock_api.side_effect = error
        result = tmdb._fetch_movie_collection({"belongs_to_collection": {"id": 123}})
        self.assertEqual(result, {})


class TMDBDiscoverTests(TestCase):
    """Test TMDB discover and genre list functions."""

    @patch("app.providers.tmdb.cache")
    @patch("app.providers.services.api_request")
    def test_discover_returns_results(self, mock_api, mock_cache):
        mock_cache.get.return_value = None
        mock_api.return_value = {
            "results": [
                {
                    "id": 1,
                    "title": "Test Movie",
                    "poster_path": "/test.jpg",
                    "overview": "A movie.",
                },
            ],
            "total_results": 1,
        }
        result = tmdb.discover(MediaTypes.MOVIE.value, {}, 1)
        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["title"], "Test Movie")

    @patch("app.providers.tmdb.cache")
    @patch("app.providers.services.api_request")
    def test_get_genre_list(self, mock_api, mock_cache):
        mock_cache.get.return_value = None
        mock_api.return_value = {
            "genres": [
                {"id": 28, "name": "Action"},
                {"id": 35, "name": "Comedy"},
            ],
        }
        result = tmdb.get_genre_list(MediaTypes.MOVIE.value)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "Action")


class TMDBHandleErrorBranchTests(SimpleTestCase):
    def test_unauthorized_without_status_message(self):
        error = make_http_error(401, {})
        with self.assertRaises(ProviderAPIError) as ctx:
            tmdb.handle_error(error)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_non_auth_status(self):
        error = make_http_error(503, {"status_message": "Service Unavailable"})
        with self.assertRaises(ProviderAPIError) as ctx:
            tmdb.handle_error(error)
        self.assertEqual(ctx.exception.status_code, 503)


class TMDBExternalLinksTests(SimpleTestCase):
    def test_all_links_present(self):
        links = tmdb.get_external_links(
            {"imdb_id": "tt0903747", "tvdb_id": 81189, "wikidata_id": "Q1079"}
        )
        self.assertIn("IMDb", links)
        self.assertIn("TVDB", links)
        self.assertIn("Wikidata", links)

    def test_no_links_when_missing(self):
        self.assertEqual(tmdb.get_external_links({}), {})

    def test_backdrop_url_with_path(self):
        url = tmdb.get_backdrop_url("/path.jpg")
        self.assertEqual(url, "https://image.tmdb.org/t/p/w1280/path.jpg")

    def test_backdrop_url_without_path(self):
        self.assertIsNone(tmdb.get_backdrop_url(None))

    def test_format_browse_result_with_backdrop(self):
        media = {
            "id": 1,
            "title": "T",
            "poster_path": "/p.jpg",
            "backdrop_path": "/b.jpg",
            "overview": "x",
        }
        result = tmdb._format_browse_result(
            media, MediaTypes.MOVIE.value, include_backdrop=True
        )
        self.assertIn("backdrop", result)
        self.assertIn("/b.jpg", result["backdrop"])


class TMDBSearchAndFindHTTPErrorTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("app.providers.services.api_request")
    def test_search_http_error_raises(self, mock_api):
        mock_api.side_effect = make_http_error(500, {"status_message": "boom"})
        with self.assertRaises(ProviderAPIError):
            tmdb.search(MediaTypes.MOVIE.value, "x", 1)

    @patch.object(settings, "TMDB_NSFW", new=True)
    @patch("app.providers.services.api_request")
    def test_search_nsfw_passes_include_adult(self, mock_api):
        mock_api.return_value = {"results": [], "total_results": 0}
        tmdb.search(MediaTypes.MOVIE.value, "x", 1)
        params = mock_api.call_args.kwargs["params"]
        self.assertEqual(params["include_adult"], "true")

    @patch.object(settings, "TMDB_NSFW", new=True)
    @patch("app.providers.services.api_request")
    def test_search_multi_nsfw_passes_include_adult(self, mock_api):
        mock_api.return_value = {"results": []}
        tmdb.search_multi("x")
        params = mock_api.call_args.kwargs["params"]
        self.assertEqual(params["include_adult"], "true")

    @patch("app.providers.services.api_request")
    def test_search_multi_http_error(self, mock_api):
        mock_api.side_effect = make_http_error(500, {"status_message": "x"})
        with self.assertRaises(ProviderAPIError):
            tmdb.search_multi("x")

    @patch("app.providers.services.api_request")
    def test_find_http_error(self, mock_api):
        mock_api.side_effect = make_http_error(500, {"status_message": "x"})
        with self.assertRaises(ProviderAPIError):
            tmdb.find("tt12345", "imdb_id")

    @patch("app.providers.services.api_request")
    def test_movie_http_error(self, mock_api):
        mock_api.side_effect = make_http_error(404, {"status_message": "Not found"})
        with self.assertRaises(ProviderAPIError):
            tmdb.movie("999999")

    @patch("app.providers.services.api_request")
    def test_tv_http_error(self, mock_api):
        mock_api.side_effect = make_http_error(500, {"status_message": "x"})
        with self.assertRaises(ProviderAPIError):
            tmdb.tv("999999")

    @patch("app.providers.services.api_request")
    def test_fetch_and_cache_seasons_http_error(self, mock_api):
        mock_api.side_effect = make_http_error(500, {"status_message": "x"})
        with self.assertRaises(ProviderAPIError):
            tmdb.fetch_and_cache_seasons("99", [1], None)

    @patch("app.providers.services.api_request")
    def test_fetch_and_cache_seasons_missing_season_key(self, mock_api):
        mock_api.return_value = {
            "id": 99,
            "name": "Show",
            "number_of_episodes": 10,
            "number_of_seasons": 1,
            "first_air_date": "2020-01-01",
            "last_air_date": "2020-12-31",
            "status": "Ended",
            "poster_path": "/x.jpg",
            "overview": "x",
            "genres": [],
            "vote_average": 7.5,
            "vote_count": 100,
            "episode_run_time": [],
            "production_companies": [],
            "production_countries": [],
            "spoken_languages": [],
            "seasons": [],
            "external_ids": {},
            "next_episode_to_air": None,
            "last_episode_to_air": None,
            "season/2": {},
        }
        with self.assertRaises(ProviderAPIError):
            tmdb.fetch_and_cache_seasons("99", [1], None)


class TMDBBrowseHTTPErrorTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("app.providers.services.api_request")
    def test_browse_http_error(self, mock_api):
        mock_api.side_effect = make_http_error(500, {"status_message": "x"})
        with self.assertRaises(ProviderAPIError):
            tmdb.browse(MediaTypes.MOVIE.value, "popular", 1)

    @patch("app.providers.services.api_request")
    def test_discover_http_error(self, mock_api):
        mock_api.side_effect = make_http_error(500, {"status_message": "x"})
        with self.assertRaises(ProviderAPIError):
            tmdb.discover(MediaTypes.MOVIE.value, {}, 1)

    @patch("app.providers.services.api_request")
    def test_get_genre_list_http_error(self, mock_api):
        mock_api.side_effect = make_http_error(500, {"status_message": "x"})
        with self.assertRaises(ProviderAPIError):
            tmdb.get_genre_list(MediaTypes.MOVIE.value)

    def test_build_discover_params_no_genres(self):
        params = tmdb._build_discover_params(MediaTypes.MOVIE.value, {}, 1)
        self.assertNotIn("with_genres", params)

    @patch("app.providers.services.api_request")
    def test_browse_for_discover_invokes_browse(self, mock_api):
        mock_api.return_value = {
            "results": [
                {
                    "id": 7,
                    "title": "T",
                    "poster_path": "/p.jpg",
                    "backdrop_path": "/b.jpg",
                    "overview": "x",
                },
            ],
            "total_results": 1,
        }
        data = tmdb.browse_for_discover(MediaTypes.MOVIE.value, "popular", 1)
        self.assertEqual(len(data["results"]), 1)
        self.assertIn("backdrop", data["results"][0])
