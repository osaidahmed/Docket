from unittest.mock import MagicMock, patch

import requests
from django.test import TestCase

from app.models import MediaTypes, Sources
from app.providers import (
    igdb,
    mal,
    services,
    tmdb,
)


class ServicesTests(TestCase):
    """Test the services module functions."""

    @patch("app.providers.services.session.get")
    def test_api_request_get(self, mock_get):
        """Test the api_request function with GET method."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": "test"}
        mock_get.return_value = mock_response

        result = services.api_request(
            "TEST",
            "GET",
            "https://example.com/api",
            params={"param": "value"},
        )

        self.assertEqual(result, {"data": "test"})

        mock_get.assert_called_once()
        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs["url"], "https://example.com/api")
        self.assertEqual(kwargs["params"], {"param": "value"})
        self.assertIn("timeout", kwargs)

    @patch("app.providers.services.session.post")
    def test_api_request_post(self, mock_post):
        """Test the api_request function with POST method."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": "test"}
        mock_post.return_value = mock_response

        result = services.api_request(
            "TEST",
            "POST",
            "https://example.com/api",
            params={"json_param": "value"},
            data={"form_data": "value"},
        )

        self.assertEqual(result, {"data": "test"})

        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["url"], "https://example.com/api")
        self.assertEqual(kwargs["json"], {"json_param": "value"})
        self.assertEqual(kwargs["data"], {"form_data": "value"})
        self.assertIn("timeout", kwargs)

    @patch("app.providers.services.time.sleep")
    @patch("app.providers.services._execute_request")
    def test_rate_limit_retry_succeeds(self, mock_execute, mock_sleep):
        """Test that 429 is retried and succeeds on second attempt."""
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {"Retry-After": "5"}
        error_429 = requests.exceptions.HTTPError(response=mock_429)

        mock_success = MagicMock()
        mock_success.json.return_value = {"data": "retry_success"}

        mock_execute.side_effect = [error_429, mock_success]

        result = services.api_request("TEST", "GET", "https://example.com/api")

        self.assertEqual(result, {"data": "retry_success"})
        self.assertEqual(mock_execute.call_count, 2)
        mock_sleep.assert_called_once_with(8)

    @patch("app.providers.services.time.sleep")
    @patch("app.providers.services._execute_request")
    def test_rate_limit_retry_exhausted(self, mock_execute, mock_sleep):
        """Test that 429 raises after MAX_RETRIES attempts."""
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {"Retry-After": "2"}
        error_429 = requests.exceptions.HTTPError(response=mock_429)

        mock_execute.side_effect = error_429

        with self.assertRaises(requests.exceptions.HTTPError):
            services.api_request("TEST", "GET", "https://example.com/api")

        self.assertEqual(mock_execute.call_count, services.MAX_RETRIES)
        self.assertEqual(mock_sleep.call_count, services.MAX_RETRIES - 1)

    @patch("app.providers.services.time.sleep")
    @patch("app.providers.services._execute_request")
    def test_rate_limit_uses_retry_after_header(self, mock_execute, mock_sleep):
        """Test that retry wait uses Retry-After when larger than backoff."""
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.headers = {"Retry-After": "30"}
        error_429 = requests.exceptions.HTTPError(response=mock_429)

        mock_success = MagicMock()
        mock_success.json.return_value = {"data": "ok"}
        mock_execute.side_effect = [error_429, mock_success]

        services.api_request("TEST", "GET", "https://example.com/api")

        mock_sleep.assert_called_once_with(33)

    @patch("app.providers.services._execute_request")
    def test_non_429_http_error_raises_immediately(self, mock_execute):
        """Test that non-429 HTTP errors raise without retrying."""
        mock_500 = MagicMock()
        mock_500.status_code = 500
        error_500 = requests.exceptions.HTTPError(response=mock_500)

        mock_execute.side_effect = error_500

        with self.assertRaises(requests.exceptions.HTTPError):
            services.api_request("TEST", "GET", "https://example.com/api")

        self.assertEqual(mock_execute.call_count, 1)

    @patch("app.providers.services._execute_request")
    def test_connection_error_raises_provider_api_error(self, mock_execute):
        """Test that connection errors are wrapped in ProviderAPIError."""
        mock_execute.side_effect = requests.exceptions.ConnectionError("refused")

        with self.assertRaises(services.ProviderAPIError):
            services.api_request("TEST", "GET", "https://example.com/api")

        self.assertEqual(mock_execute.call_count, 1)

    @patch("app.providers.services._execute_request")
    def test_timeout_error_raises_provider_api_error(self, mock_execute):
        """Test that timeout errors are wrapped in ProviderAPIError."""
        mock_execute.side_effect = requests.exceptions.Timeout("timed out")

        with self.assertRaises(services.ProviderAPIError):
            services.api_request("TEST", "GET", "https://example.com/api")

        self.assertEqual(mock_execute.call_count, 1)

    @patch("app.providers.services._execute_request")
    def test_xml_response_format(self, mock_execute):
        """Test that XML response format parses correctly."""
        mock_response = MagicMock()
        mock_response.text = "<root><item>test</item></root>"
        mock_execute.return_value = mock_response

        result = services.api_request(
            "TEST", "GET", "https://example.com/api", response_format="xml"
        )

        self.assertEqual(result.tag, "root")
        self.assertEqual(result.find("item").text, "test")

    @patch("app.providers.igdb.cache.delete")
    def test_handle_error_igdb_unauthorized(
        self,
        mock_cache_delete,
    ):
        """Test the handle_error function with IGDB unauthorized error."""
        mock_response = MagicMock()
        mock_response.status_code = 401  # Unauthorized

        error = requests.exceptions.HTTPError("401 Unauthorized")
        error.response = mock_response

        result = igdb.handle_error(error)

        mock_cache_delete.assert_called_once_with("igdb_access_token")

        self.assertEqual(result, {"retry": True})

    def test_handle_error_igdb_bad_request(self):
        """Test the handle_error function with IGDB bad request error."""
        mock_response = MagicMock()
        mock_response.status_code = 400  # Bad Request
        mock_response.json.return_value = {"message": "Invalid query"}

        error = requests.exceptions.HTTPError("400 Bad Request")
        error.response = mock_response

        with self.assertRaises(services.ProviderAPIError) as cm:
            igdb.handle_error(error)

        self.assertEqual(cm.exception.provider, Sources.IGDB.value)

    def test_handle_error_tmdb_unauthorized(self):
        """Test the handle_error function with TMDB unauthorized error."""
        mock_response = MagicMock()
        mock_response.status_code = 401  # Unauthorized
        mock_response.json.return_value = {"status_message": "Invalid API key"}

        error = requests.exceptions.HTTPError("401 Unauthorized")
        error.response = mock_response

        with self.assertRaises(services.ProviderAPIError) as cm:
            tmdb.handle_error(error)

        self.assertEqual(cm.exception.provider, Sources.TMDB.value)

    def test_handle_error_mal_forbidden(self):
        """Test the handle_error function with MAL forbidden error."""
        mock_response = MagicMock()
        mock_response.status_code = 403  # Forbidden
        mock_response.json.return_value = {"message": "Forbidden"}

        error = requests.exceptions.HTTPError("403 Forbidden")
        error.response = mock_response

        with self.assertRaises(services.ProviderAPIError) as cm:
            mal.handle_error(error)

        self.assertEqual(cm.exception.provider, Sources.MAL.value)

    _DEFAULT_RETURN = {"title": "test"}

    METADATA_CASES = [
        (
            MediaTypes.ANIME.value,
            Sources.MAL.value,
            "app.providers.mal.anime",
            "1",
            ("1",),
            None,
            None,
            _DEFAULT_RETURN,
            _DEFAULT_RETURN,
        ),
        (
            MediaTypes.MANGA.value,
            Sources.MANGAUPDATES.value,
            "app.providers.mangaupdates.manga",
            "1",
            ("1",),
            None,
            None,
            _DEFAULT_RETURN,
            _DEFAULT_RETURN,
        ),
        (
            MediaTypes.MANGA.value,
            Sources.MAL.value,
            "app.providers.mal.manga",
            "1",
            ("1",),
            None,
            None,
            _DEFAULT_RETURN,
            _DEFAULT_RETURN,
        ),
        (
            MediaTypes.TV.value,
            Sources.TMDB.value,
            "app.providers.tmdb.tv",
            "1",
            ("1",),
            None,
            None,
            _DEFAULT_RETURN,
            _DEFAULT_RETURN,
        ),
        (
            "tv_with_seasons",
            Sources.TMDB.value,
            "app.providers.tmdb.tv_with_seasons",
            "1",
            ("1", [1, 2]),
            [1, 2],
            None,
            _DEFAULT_RETURN,
            _DEFAULT_RETURN,
        ),
        (
            MediaTypes.SEASON.value,
            Sources.TMDB.value,
            "app.providers.tmdb.tv_with_seasons",
            "1",
            ("1", [1]),
            [1],
            None,
            {"season/1": {"title": "test"}},
            {"title": "test"},
        ),
        (
            MediaTypes.EPISODE.value,
            Sources.TMDB.value,
            "app.providers.tmdb.episode",
            "1",
            ("1", 1, "2"),
            [1],
            "2",
            _DEFAULT_RETURN,
            _DEFAULT_RETURN,
        ),
        (
            MediaTypes.MOVIE.value,
            Sources.TMDB.value,
            "app.providers.tmdb.movie",
            "1",
            ("1",),
            None,
            None,
            _DEFAULT_RETURN,
            _DEFAULT_RETURN,
        ),
        (
            MediaTypes.GAME.value,
            Sources.IGDB.value,
            "app.providers.igdb.game",
            "1",
            ("1",),
            None,
            None,
            _DEFAULT_RETURN,
            _DEFAULT_RETURN,
        ),
        (
            MediaTypes.COMIC.value,
            Sources.COMICVINE.value,
            "app.providers.comicvine.comic",
            "1",
            ("1",),
            None,
            None,
            _DEFAULT_RETURN,
            _DEFAULT_RETURN,
        ),
        (
            MediaTypes.BOOK.value,
            Sources.OPENLIBRARY.value,
            "app.providers.openlibrary.book",
            "1",
            ("1",),
            None,
            None,
            _DEFAULT_RETURN,
            _DEFAULT_RETURN,
        ),
        (
            MediaTypes.BOOK.value,
            Sources.HARDCOVER.value,
            "app.providers.hardcover.book",
            "1",
            ("1",),
            None,
            None,
            _DEFAULT_RETURN,
            _DEFAULT_RETURN,
        ),
        (
            MediaTypes.MOVIE.value,
            Sources.MANUAL.value,
            "app.providers.manual.metadata",
            "1",
            ("1", MediaTypes.MOVIE.value),
            None,
            None,
            _DEFAULT_RETURN,
            _DEFAULT_RETURN,
        ),
        (
            MediaTypes.SEASON.value,
            Sources.MANUAL.value,
            "app.providers.manual.season",
            "1",
            ("1", 1),
            [1],
            None,
            _DEFAULT_RETURN,
            _DEFAULT_RETURN,
        ),
        (
            MediaTypes.EPISODE.value,
            Sources.MANUAL.value,
            "app.providers.manual.episode",
            "1",
            ("1", 1, "2"),
            [1],
            "2",
            _DEFAULT_RETURN,
            _DEFAULT_RETURN,
        ),
    ]

    def test_get_media_metadata(self):
        """Test get_media_metadata dispatches to the correct provider."""
        for (
            media_type,
            source,
            patch_target,
            media_id,
            expected_call_args,
            season_numbers,
            episode_number,
            mock_return,
            expected_result,
        ) in self.METADATA_CASES:
            with (
                self.subTest(
                    media_type=media_type, source=source, patch_target=patch_target
                ),
                patch(patch_target) as mock_fn,
            ):
                mock_fn.return_value = mock_return

                kwargs = {}
                if season_numbers is not None:
                    kwargs["season_numbers"] = season_numbers
                if episode_number is not None:
                    kwargs["episode_number"] = episode_number

                result = services.get_media_metadata(
                    media_type,
                    media_id,
                    source,
                    **kwargs,
                )

                self.assertEqual(result, expected_result)
                mock_fn.assert_called_once_with(*expected_call_args)

    @patch("app.providers.tmdb.episode")
    def test_get_media_metadata_tmdb_episode_not_found(self, mock_episode):
        """Test the get_media_metadata function for TMDB episodes that don't exist."""
        mock_response = type(
            "Response",
            (),
            {"status_code": 404, "text": "Episode not found"},
        )()
        mock_error = type("Error", (), {"response": mock_response})()
        mock_episode.side_effect = services.ProviderAPIError(
            Sources.TMDB.value,
            mock_error,
        )

        with self.assertRaises(services.ProviderAPIError) as cm:
            services.get_media_metadata(
                MediaTypes.EPISODE.value,
                "1396",
                Sources.TMDB.value,
                season_numbers=[1],
                episode_number="3",
            )

        self.assertEqual(cm.exception.provider, Sources.TMDB.value)

        mock_episode.assert_called_once_with("1396", 1, "3")

    SEARCH_CASES = [
        (
            MediaTypes.ANIME.value,
            None,
            "app.providers.mal.search",
            (MediaTypes.ANIME.value, "test", 1),
        ),
        (
            MediaTypes.MANGA.value,
            Sources.MANGAUPDATES.value,
            "app.providers.mangaupdates.search",
            ("test", 1),
        ),
        (
            MediaTypes.MANGA.value,
            None,
            "app.providers.mal.search",
            (MediaTypes.MANGA.value, "test", 1),
        ),
        (
            MediaTypes.TV.value,
            None,
            "app.providers.tmdb.search",
            (MediaTypes.TV.value, "test", 1),
        ),
        (
            MediaTypes.MOVIE.value,
            None,
            "app.providers.tmdb.search",
            (MediaTypes.MOVIE.value, "test", 1),
        ),
        (MediaTypes.GAME.value, None, "app.providers.igdb.search", ("test", 1)),
        (
            MediaTypes.BOOK.value,
            Sources.HARDCOVER.value,
            "app.providers.hardcover.search",
            ("test", 1),
        ),
        (
            MediaTypes.BOOK.value,
            Sources.OPENLIBRARY.value,
            "app.providers.openlibrary.search",
            ("test", 1),
        ),
        (MediaTypes.COMIC.value, None, "app.providers.comicvine.search", ("test", 1)),
    ]

    def test_search(self):
        """Test search dispatches to the correct provider."""
        for media_type, source, patch_target, expected_call_args in self.SEARCH_CASES:
            with (
                self.subTest(
                    media_type=media_type, source=source, patch_target=patch_target
                ),
                patch(patch_target) as mock_fn,
            ):
                mock_fn.return_value = [{"title": "test"}]

                kwargs = {}
                if source is not None:
                    kwargs["source"] = source
                result = services.search(
                    media_type,
                    "test",
                    1,
                    **kwargs,
                )

                self.assertEqual(result, [{"title": "test"}])
                mock_fn.assert_called_once_with(*expected_call_args)

    @patch("app.providers.services.search")
    def test_search_all_returns_grouped_results(self, mock_search):
        """Test search_all returns results grouped by type in correct order."""
        mock_search.side_effect = lambda mt, _q, _page, source=None: {
            "results": [
                {
                    "media_id": "1",
                    "title": f"Test {mt}",
                    "media_type": mt,
                    "source": source or "test",
                    "image": "http://example.com/img.jpg",
                    "synopsis": "A synopsis.",
                },
            ],
        }

        all_types = [
            MediaTypes.ANIME.value,
            MediaTypes.MANGA.value,
            MediaTypes.TV.value,
            MediaTypes.MOVIE.value,
            MediaTypes.GAME.value,
            MediaTypes.BOOK.value,
            MediaTypes.COMIC.value,
            MediaTypes.BOARDGAME.value,
        ]

        result = services.search_all("test", all_types)

        result_types = [g["media_type"] for g in result]
        self.assertEqual(result_types, all_types)

        for group in result:
            self.assertTrue(len(group["results"]) > 0)

    @patch("app.providers.services.search")
    def test_search_all_caps_at_three(self, mock_search):
        """Test search_all returns at most 3 results per type."""
        mock_search.return_value = {
            "results": [
                {
                    "media_id": str(i),
                    "title": f"Result {i}",
                    "media_type": MediaTypes.ANIME.value,
                    "source": Sources.MAL.value,
                    "image": "http://example.com/img.jpg",
                    "synopsis": "",
                }
                for i in range(10)
            ],
        }

        result = services.search_all("test", [MediaTypes.ANIME.value])

        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["results"]), 3)

    @patch("app.providers.services.search")
    def test_search_all_handles_provider_failure(self, mock_search):
        """Test search_all gracefully handles a failing provider."""

        def side_effect(mt, _q, _page, source=None):
            if mt == MediaTypes.ANIME.value:
                msg = "MAL is down"
                raise RuntimeError(msg)
            return {
                "results": [
                    {
                        "media_id": "1",
                        "title": f"Test {mt}",
                        "media_type": mt,
                        "source": source or "test",
                        "image": "http://example.com/img.jpg",
                        "synopsis": "",
                    },
                ],
            }

        mock_search.side_effect = side_effect

        result = services.search_all(
            "test",
            [MediaTypes.ANIME.value, MediaTypes.TV.value],
        )

        result_types = [g["media_type"] for g in result]
        self.assertNotIn(MediaTypes.ANIME.value, result_types)
        self.assertIn(MediaTypes.TV.value, result_types)

    def test_search_all_empty_enabled_types(self):
        """Test search_all with no enabled types returns empty list."""
        result = services.search_all("test", [])
        self.assertEqual(result, [])

    @patch("app.providers.services.search")
    def test_search_all_respects_custom_order(self, mock_search):
        """Test search_all returns results in the order of enabled_types input."""
        mock_search.side_effect = lambda mt, _q, _page, source=None: {
            "results": [
                {
                    "media_id": "1",
                    "title": f"Test {mt}",
                    "media_type": mt,
                    "source": source or "test",
                    "image": "http://example.com/img.jpg",
                    "synopsis": "",
                },
            ],
        }

        custom_order = [
            MediaTypes.GAME.value,
            MediaTypes.ANIME.value,
            MediaTypes.BOOK.value,
        ]

        result = services.search_all("test", custom_order)

        result_types = [g["media_type"] for g in result]
        self.assertEqual(result_types, custom_order)


class ProviderAPIErrorTests(TestCase):
    """Test ProviderAPIError exception class."""

    def test_invalid_source_uses_title(self):
        mock_response = type("Response", (), {"status_code": 500, "text": "error"})()
        mock_error = requests.exceptions.HTTPError(response=mock_response)

        error = services.ProviderAPIError("unknown_provider", mock_error)

        self.assertEqual(error.provider, "unknown_provider")
        self.assertIn("Unknown_Provider", str(error))

    def test_with_details(self):
        mock_response = type("Response", (), {"status_code": 400, "text": "bad"})()
        mock_error = requests.exceptions.HTTPError(response=mock_response)

        error = services.ProviderAPIError(
            Sources.TMDB.value, mock_error, "Custom detail"
        )

        self.assertIn("Custom detail", str(error))


class RaiseNotFoundErrorTests(TestCase):
    """Test raise_not_found_error function."""

    def test_raises_provider_api_error(self):
        with self.assertRaises(services.ProviderAPIError) as cm:
            services.raise_not_found_error(Sources.COMICVINE.value, "12345", "comic")

        self.assertEqual(cm.exception.status_code, 404)
        self.assertIn("Comic with ID 12345 not found", str(cm.exception))

    def test_default_media_type(self):
        with self.assertRaises(services.ProviderAPIError) as cm:
            services.raise_not_found_error(Sources.IGDB.value, "99")

        self.assertIn("Item with ID 99 not found", str(cm.exception))


class APIRequestConnectionErrorTests(TestCase):
    """Test api_request connection error handling."""

    @patch("app.providers.services.session.get")
    def test_connection_error(self, mock_get):
        mock_get.side_effect = requests.exceptions.ConnectionError("DNS failure")

        with self.assertRaises(services.ProviderAPIError) as cm:
            services.api_request("TEST", "GET", "https://example.com/api")

        self.assertEqual(cm.exception.status_code, 503)
        self.assertIn("Connection failed", str(cm.exception))

    @patch("app.providers.services.session.get")
    def test_timeout_error(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")

        with self.assertRaises(services.ProviderAPIError) as cm:
            services.api_request("TEST", "GET", "https://example.com/api")

        self.assertEqual(cm.exception.status_code, 503)


class APIRequestXMLTests(TestCase):
    """Test api_request XML response handling."""

    @patch("app.providers.services.session.get")
    def test_xml_response(self, mock_get):
        mock_response = MagicMock()
        mock_response.text = "<root><item id='1'/></root>"
        mock_get.return_value = mock_response

        result = services.api_request(
            "TEST", "GET", "https://example.com/api", response_format="xml"
        )

        self.assertEqual(result.tag, "root")


class BrowseDispatchTests(TestCase):
    """Test services.browse dispatch to providers."""

    @patch("app.providers.bgg.browse")
    def test_browse_boardgame(self, mock_bgg):
        mock_bgg.return_value = {"results": [], "page": 1, "total_results": 0}

        result = services.browse(MediaTypes.BOARDGAME.value, "hot", 1)

        mock_bgg.assert_called_once_with("hot", 1)
        self.assertEqual(result["results"], [])

    @patch("app.providers.comicvine.browse")
    def test_browse_comic(self, mock_cv):
        mock_cv.return_value = {"results": [], "page": 1, "total_results": 0}

        services.browse(MediaTypes.COMIC.value, "recent", 1)

        mock_cv.assert_called_once_with("recent", 1)

    @patch("app.providers.igdb.browse")
    def test_browse_game(self, mock_igdb):
        mock_igdb.return_value = {"results": [], "page": 1, "total_results": 0}

        services.browse(MediaTypes.GAME.value, "popular", 1)

        mock_igdb.assert_called_once_with("popular", 1)

    @patch("app.providers.mal.browse_seasonal")
    def test_browse_anime_seasonal(self, mock_seasonal):
        mock_seasonal.return_value = {"results": []}

        services.browse(
            MediaTypes.ANIME.value, "seasonal", 1, year=2024, season="winter"
        )

        mock_seasonal.assert_called_once_with(2024, "winter", 1)

    def test_browse_unknown_type(self):
        result = services.browse("nonexistent", "popular", 1)

        self.assertEqual(result["results"], [])
        self.assertEqual(result["total_results"], 0)

    BROWSE_CASES = [
        (MediaTypes.ANIME.value, "app.providers.mal.browse"),
        (MediaTypes.MANGA.value, "app.providers.mal.browse"),
        (MediaTypes.TV.value, "app.providers.tmdb.browse"),
        (MediaTypes.MOVIE.value, "app.providers.tmdb.browse"),
    ]

    def test_browse_dispatches(self):
        for media_type, patch_target in self.BROWSE_CASES:
            with self.subTest(media_type=media_type), patch(patch_target) as mock_fn:
                mock_fn.return_value = {"results": [], "page": 1, "total_results": 0}
                services.browse(media_type, "popular", 1)
                mock_fn.assert_called_once()


class BrowseFilteredDispatchTests(TestCase):
    """Test services.browse_filtered dispatch to providers."""

    @patch("app.providers.jikan.browse")
    def test_browse_filtered_anime(self, mock_jikan):
        mock_jikan.return_value = {"results": [], "page": 1, "total_results": 0}

        services.browse_filtered(MediaTypes.ANIME.value, {"genres": "1"}, 1)

        mock_jikan.assert_called_once_with(MediaTypes.ANIME.value, {"genres": "1"}, 1)

    @patch("app.providers.jikan.browse")
    def test_browse_filtered_manga(self, mock_jikan):
        mock_jikan.return_value = {"results": [], "page": 1, "total_results": 0}

        services.browse_filtered(MediaTypes.MANGA.value, {"genres": "2"}, 1)

        mock_jikan.assert_called_once_with(MediaTypes.MANGA.value, {"genres": "2"}, 1)

    @patch("app.providers.igdb.browse_filtered")
    def test_browse_filtered_game(self, mock_igdb):
        mock_igdb.return_value = {"results": [], "page": 1, "total_results": 0}

        services.browse_filtered(MediaTypes.GAME.value, {"genres": "12"}, 1)

        mock_igdb.assert_called_once_with({"genres": "12"}, 1)

    @patch("app.providers.tmdb.discover")
    def test_browse_filtered_movie(self, mock_tmdb):
        mock_tmdb.return_value = {"results": [], "page": 1, "total_results": 0}

        services.browse_filtered(MediaTypes.MOVIE.value, {"genres": "28"}, 1)
        mock_tmdb.assert_called_once_with(MediaTypes.MOVIE.value, {"genres": "28"}, 1)

    @patch("app.providers.tmdb.discover")
    def test_browse_filtered_tv(self, mock_tmdb):
        mock_tmdb.return_value = {"results": [], "page": 1, "total_results": 0}

        services.browse_filtered(MediaTypes.TV.value, {}, 1)
        mock_tmdb.assert_called_once_with(MediaTypes.TV.value, {}, 1)

    def test_browse_filtered_unknown_type(self):
        result = services.browse_filtered("nonexistent", {}, 1)

        self.assertEqual(result["results"], [])


class GetFilterOptionsTests(TestCase):
    """Test services.get_filter_options function."""

    @patch("app.providers.jikan.get_genres")
    def test_jikan_anime_genres(self, mock_fn):
        mock_fn.return_value = [{"id": 1, "name": "Action"}]

        result = services.get_filter_options("jikan_anime_genres")

        mock_fn.assert_called_once_with(MediaTypes.ANIME.value)
        self.assertEqual(len(result), 1)

    @patch("app.providers.jikan.get_genres")
    def test_jikan_manga_genres(self, mock_fn):
        mock_fn.return_value = [{"id": 1, "name": "Shounen"}]

        services.get_filter_options("jikan_manga_genres")

        mock_fn.assert_called_once_with(MediaTypes.MANGA.value)

    @patch("app.providers.igdb.get_genres")
    def test_igdb_genres(self, mock_fn):
        mock_fn.return_value = [{"id": 1, "name": "Action"}]

        services.get_filter_options("igdb_genres")

        mock_fn.assert_called_once()

    @patch("app.providers.igdb.get_platforms")
    def test_igdb_platforms(self, mock_fn):
        mock_fn.return_value = [{"id": 48, "name": "PS4"}]

        services.get_filter_options("igdb_platforms")

        mock_fn.assert_called_once()

    @patch("app.providers.igdb.get_themes")
    def test_igdb_themes(self, mock_fn):
        mock_fn.return_value = [{"id": 1, "name": "Fantasy"}]

        services.get_filter_options("igdb_themes")

        mock_fn.assert_called_once()

    @patch("app.providers.tmdb.get_genre_list")
    def test_tmdb_movie_genres(self, mock_fn):
        mock_fn.return_value = [{"id": 28, "name": "Action"}]

        services.get_filter_options("tmdb_movie_genres")

        mock_fn.assert_called_once_with(MediaTypes.MOVIE.value)

    @patch("app.providers.tmdb.get_genre_list")
    def test_tmdb_tv_genres(self, mock_fn):
        mock_fn.return_value = [{"id": 10765, "name": "Sci-Fi"}]

        services.get_filter_options("tmdb_tv_genres")

        mock_fn.assert_called_once_with(MediaTypes.TV.value)

    def test_unknown_provider_key(self):
        result = services.get_filter_options("nonexistent")
        self.assertEqual(result, [])
