from unittest.mock import MagicMock, patch

import requests
from django.conf import settings
from django.test import SimpleTestCase, TestCase

from app.models import MediaTypes
from app.providers import tmdb
from app.providers.services import ProviderAPIError


class TMDBHelperTests(SimpleTestCase):
    """Test TMDB helper and utility functions."""

    def test_build_discover_params_movie_year(self):
        params = tmdb._build_discover_params(
            MediaTypes.MOVIE.value, {"year": "2024"}, 1
        )
        self.assertIn("primary_release_year", params)
        self.assertEqual(params["primary_release_year"], "2024")

    def test_build_discover_params_tv_year(self):
        params = tmdb._build_discover_params(
            MediaTypes.TV.value, {"year": "2024"}, 1
        )
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
        params = tmdb._build_discover_params(
            MediaTypes.MOVIE.value, {}, 1
        )
        self.assertEqual(params["include_adult"], "true")

    def test_build_discover_filter_hash_nofilter(self):
        result = tmdb._build_discover_filter_hash(
            MediaTypes.MOVIE.value, {}
        )
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
        error_response.json.return_value = {
            "status_message": "Invalid API key."
        }
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
            tmdb._fetch_movie_collection(
                {"belongs_to_collection": {"id": None}}
            ),
            {},
        )

    @patch("app.providers.services.api_request")
    def test_fetch_movie_collection_http_error(self, mock_api):
        error = requests.exceptions.HTTPError()
        error.response = MagicMock(status_code=500, text="err")
        mock_api.side_effect = error
        result = tmdb._fetch_movie_collection(
            {"belongs_to_collection": {"id": 123}}
        )
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
