from pathlib import Path
from unittest.mock import MagicMock, patch

import requests
from django.conf import settings
from django.core.cache import cache
from django.test import TestCase

from app.models import MediaTypes, Sources
from app.providers import (
    igdb,
    jikan,
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


class JikanBrowseTests(TestCase):
    """Test Jikan browse functionality."""

    @patch("app.providers.services.api_request")
    def test_browse_anime(self, mock_api):
        mock_api.return_value = {
            "data": [
                {
                    "mal_id": 1,
                    "title": "Cowboy Bebop",
                    "title_english": "Cowboy Bebop",
                    "images": {"jpg": {"large_image_url": "http://img/cb.jpg"}},
                    "synopsis": "A bounty hunter story",
                    "status": "Finished Airing",
                    "chapters": None,
                },
            ],
            "pagination": {"items": {"total": 1}},
        }

        result = jikan.browse(MediaTypes.ANIME.value, {"min_score": "1"}, 1)

        self.assertEqual(len(result["results"]), 1)
        self.assertEqual(result["results"][0]["title"], "Cowboy Bebop")
        self.assertEqual(result["results"][0]["source"], Sources.MAL.value)

    @patch("app.providers.services.api_request")
    def test_browse_manga_ongoing(self, mock_api):
        mock_api.return_value = {
            "data": [
                {
                    "mal_id": 1,
                    "title": "Monster",
                    "title_english": None,
                    "images": {"jpg": {"large_image_url": "http://img/m.jpg"}},
                    "synopsis": "A thriller manga",
                    "chapters": None,
                },
            ],
            "pagination": {"items": {"total": 1}},
        }

        result = jikan.browse(MediaTypes.MANGA.value, {"min_score": "1"}, 1)

        self.assertEqual(result["results"][0]["is_ongoing"], True)

    @patch("app.providers.services.api_request")
    def test_browse_manga_with_chapters(self, mock_api):
        mock_api.return_value = {
            "data": [
                {
                    "mal_id": 1,
                    "title": "Monster",
                    "title_english": None,
                    "images": {"jpg": {"large_image_url": "http://img/m.jpg"}},
                    "synopsis": "A thriller manga",
                    "chapters": 162,
                },
            ],
            "pagination": {"items": {"total": 1}},
        }

        result = jikan.browse(MediaTypes.MANGA.value, {"min_score": "2"}, 1)

        self.assertEqual(result["results"][0]["is_ongoing"], False)

    @patch("app.providers.services.api_request")
    def test_browse_with_filters(self, mock_api):
        mock_api.return_value = {
            "data": [],
            "pagination": {"items": {"total": 0}},
        }

        filters = {"genres": "1,2", "min_score": "7", "anime_type": "TV"}
        jikan.browse(MediaTypes.ANIME.value, filters, 1)

        call_kwargs = mock_api.call_args
        params = (
            call_kwargs[1]["params"]
            if "params" in call_kwargs[1]
            else call_kwargs[0][3]
        )
        self.assertEqual(params["genres"], "1,2")
        self.assertEqual(params["min_score"], "7")
        self.assertEqual(params["type"], "TV")

    @patch("app.providers.services.api_request")
    def test_browse_error_returns_empty(self, mock_api):
        mock_api.side_effect = Exception("API down")

        result = jikan.browse(MediaTypes.ANIME.value, {"min_score": "99"}, 1)

        self.assertEqual(result["results"], [])
        self.assertEqual(result["total_results"], 0)


class JikanGetGenresTests(TestCase):
    """Test Jikan get_genres function."""

    @patch("app.providers.services.api_request")
    def test_get_genres_anime(self, mock_api):
        mock_api.return_value = {
            "data": [
                {"mal_id": 1, "name": "Action"},
                {"mal_id": 2, "name": "Adventure"},
            ],
        }

        cache.delete("jikan_anime_genres")

        result = jikan.get_genres(MediaTypes.ANIME.value)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], 1)
        self.assertEqual(result[0]["name"], "Action")

    @patch("app.providers.services.api_request")
    def test_get_genres_error_returns_empty(self, mock_api):
        mock_api.side_effect = Exception("API down")

        cache.delete("jikan_manga_genres")

        result = jikan.get_genres(MediaTypes.MANGA.value)

        self.assertEqual(result, [])


class JikanHelperTests(TestCase):
    """Test Jikan helper functions."""

    def test_get_image_url_with_large(self):
        item = {"images": {"jpg": {"large_image_url": "http://img/large.jpg"}}}
        self.assertEqual(jikan._get_image_url(item), "http://img/large.jpg")

    def test_get_image_url_fallback_to_regular(self):
        item = {"images": {"jpg": {"image_url": "http://img/reg.jpg"}}}
        self.assertEqual(jikan._get_image_url(item), "http://img/reg.jpg")

    def test_get_image_url_no_images(self):
        self.assertEqual(jikan._get_image_url({}), settings.IMG_NONE)

    def test_build_filter_hash_with_filters(self):
        result = jikan._build_filter_hash("anime", {"genres": "1", "min_score": "7"})
        self.assertIn("anime", result)
        self.assertIn("genres=1", result)
        self.assertIn("min_score=7", result)

    def test_build_filter_hash_no_filters(self):
        result = jikan._build_filter_hash("anime", {})
        self.assertEqual(result, "nofilter")

    def test_build_params_nsfw(self):
        params = jikan._build_params({}, 1)
        self.assertEqual(params["page"], 1)
        self.assertEqual(params["limit"], settings.PER_PAGE)
