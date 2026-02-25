from pathlib import Path
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

mock_path = Path(__file__).resolve().parent.parent / "mock_data"


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

    @patch("app.providers.services.api_request")
    def test_request_error_handling_rate_limit(self, mock_api_request):
        """Test the request_error_handling function with rate limiting."""
        mock_response = MagicMock()
        mock_response.status_code = 429  # Too many requests
        mock_response.headers = {"Retry-After": "5"}

        error = requests.exceptions.HTTPError("429 Too Many Requests")
        error.response = mock_response

        mock_api_request.return_value = {"data": "retry_success"}

        result = services.api_request(
            error,
            "TEST",
            "GET",
            "https://example.com/api",
            {"param": "value"},
            None,
            None,
        )

        mock_api_request.assert_called_once()

        self.assertEqual(result, {"data": "retry_success"})

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
