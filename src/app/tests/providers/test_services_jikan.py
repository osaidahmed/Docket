from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import TestCase

from app.models import MediaTypes, Sources
from app.providers import jikan


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
