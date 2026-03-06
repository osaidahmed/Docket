from unittest.mock import MagicMock, patch

import requests
from django.conf import settings
from django.test import TestCase

from app.models import MediaTypes, Sources
from app.providers import comicvine, services


class ComicVineBrowse(TestCase):
    """Test the ComicVine browse API calls."""

    required_keys = {"media_id", "media_type", "title", "image", "synopsis"}

    def test_recent(self):
        """Test browsing recently added comics."""
        response = comicvine.browse("recent", 1)

        self.assertGreater(len(response["results"]), 0)
        for item in response["results"]:
            self.assertTrue(all(key in item for key in self.required_keys))
            self.assertEqual(item["media_type"], MediaTypes.COMIC.value)

    def test_updated(self):
        """Test browsing recently updated comics."""
        response = comicvine.browse("updated", 1)

        self.assertGreater(len(response["results"]), 0)

    def test_pagination(self):
        """Test that pagination returns different pages."""
        page1 = comicvine.browse("recent", 1)
        page2 = comicvine.browse("recent", 2)

        self.assertEqual(page1["page"], 1)
        self.assertEqual(page2["page"], 2)

    def test_response_format(self):
        """Test that the response has the expected keys."""
        response = comicvine.browse("recent", 1)

        self.assertIn("page", response)
        self.assertIn("total_results", response)
        self.assertIn("total_pages", response)
        self.assertIn("results", response)


class ComicVineHandleError(TestCase):
    """Test ComicVine handle_error function."""

    def test_unauthorized(self):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.json.return_value = {"error": "Invalid API Key"}

        error = requests.exceptions.HTTPError("401")
        error.response = mock_response

        with self.assertRaises(services.ProviderAPIError) as cm:
            comicvine.handle_error(error)

        self.assertEqual(cm.exception.provider, Sources.COMICVINE.value)

    def test_json_decode_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = requests.exceptions.JSONDecodeError(
            "err", "", 0
        )

        error = requests.exceptions.HTTPError("500")
        error.response = mock_response

        with self.assertRaises(services.ProviderAPIError):
            comicvine.handle_error(error)

    def test_other_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 503
        mock_response.json.return_value = {"error": "Service Unavailable"}

        error = requests.exceptions.HTTPError("503")
        error.response = mock_response

        with self.assertRaises(services.ProviderAPIError):
            comicvine.handle_error(error)


class ComicVineSearch(TestCase):
    """Test ComicVine search functionality."""

    @patch("app.providers.services.api_request")
    def test_search_returns_results(self, mock_api):
        mock_api.return_value = {
            "results": [
                {
                    "id": 1234,
                    "name": "Batman",
                    "image": {"medium_url": "http://img/bat.jpg"},
                    "description": "<p>Dark Knight</p>",
                },
            ],
            "number_of_total_results": 1,
        }

        response = comicvine.search("Batman", 1)

        self.assertEqual(len(response["results"]), 1)
        self.assertEqual(response["results"][0]["title"], "Batman")
        self.assertEqual(response["results"][0]["media_id"], "1234")
        self.assertEqual(response["results"][0]["source"], Sources.COMICVINE.value)
        self.assertEqual(response["results"][0]["image"], "http://img/bat.jpg")
        self.assertIn("Dark Knight", response["results"][0]["synopsis"])

    @patch("app.providers.services.api_request")
    def test_search_no_description(self, mock_api):
        mock_api.return_value = {
            "results": [
                {
                    "id": 5678,
                    "name": "Unknown Comic",
                    "image": {"medium_url": "http://img/unk.jpg"},
                    "description": None,
                },
            ],
            "number_of_total_results": 1,
        }

        response = comicvine.search("Unknown", 1)

        self.assertEqual(response["results"][0]["synopsis"], "")


class ComicVineHelpers(TestCase):
    """Test ComicVine helper functions."""

    def test_get_image_present(self):
        response = {"image": {"medium_url": "http://img/test.jpg"}}
        self.assertEqual(comicvine.get_image(response), "http://img/test.jpg")

    def test_get_image_missing(self):
        self.assertEqual(comicvine.get_image({}), settings.IMG_NONE)

    def test_get_synopsis_present(self):
        response = {"description": "<p>A  comic  series</p>"}
        result = comicvine.get_synopsis(response)
        self.assertEqual(result, "A comic series")

    def test_get_synopsis_missing(self):
        self.assertEqual(comicvine.get_synopsis({}), "No synopsis available")

    def test_get_genres_present(self):
        response = {"concepts": [{"name": "Horror"}, {"name": "Superhero"}]}
        self.assertEqual(comicvine.get_genres(response), ["Horror", "Superhero"])

    def test_get_genres_missing(self):
        self.assertIsNone(comicvine.get_genres({}))

    def test_get_publisher_name_present(self):
        response = {"publisher": {"name": "Marvel"}}
        self.assertEqual(comicvine.get_publisher_name(response), "Marvel")

    def test_get_publisher_name_missing(self):
        self.assertIsNone(comicvine.get_publisher_name({}))

    def test_get_publisher_name_not_dict(self):
        self.assertIsNone(comicvine.get_publisher_name({"publisher": "string"}))

    def test_get_last_issue_name_present(self):
        response = {"last_issue": {"name": "Final Chapter"}}
        self.assertEqual(comicvine.get_last_issue_name(response), "Final Chapter")

    def test_get_last_issue_name_missing(self):
        self.assertIsNone(comicvine.get_last_issue_name({}))

    def test_get_issue_number_integer(self):
        self.assertEqual(comicvine.get_issue_number("42"), 42)

    def test_get_issue_number_compound(self):
        self.assertEqual(comicvine.get_issue_number("463-464"), 464)

    def test_get_issue_number_invalid(self):
        self.assertIsNone(comicvine.get_issue_number("Annual"))

    def test_get_last_issue_number_present(self):
        response = {"last_issue": {"issue_number": "10"}}
        self.assertEqual(comicvine.get_last_issue_number(response), "10")

    def test_get_last_issue_number_missing(self):
        self.assertIsNone(comicvine.get_last_issue_number({}))

    def test_get_people_present(self):
        response = {"people": [{"name": "Writer A"}, {"name": "Artist B"}]}
        self.assertEqual(comicvine.get_people(response), ["Writer A", "Artist B"])

    def test_get_people_empty(self):
        self.assertEqual(comicvine.get_people({}), [])


class ComicVineComic(TestCase):
    """Test ComicVine comic metadata function."""

    @patch("app.providers.comicvine.get_publisher_comics")
    @patch("app.providers.services.api_request")
    def test_comic_not_found(self, mock_api, _mock_pub):
        mock_api.return_value = {"results": {}}

        with self.assertRaises(services.ProviderAPIError):
            comicvine.comic("999999")


class ComicVinePublisherComics(TestCase):
    """Test ComicVine get_publisher_comics function."""

    @patch("app.providers.services.api_request")
    def test_get_publisher_comics(self, mock_api):
        mock_api.return_value = {
            "results": [
                {
                    "id": 100,
                    "name": "Spider-Man",
                    "image": {"medium_url": "http://img/sm.jpg"},
                },
                {
                    "id": 200,
                    "name": "Other Comic",
                    "image": {"medium_url": "http://img/oc.jpg"},
                },
            ],
        }

        result = comicvine.get_publisher_comics("1", "100")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Other Comic")


class ComicVineIssue(TestCase):
    """Test ComicVine issue function."""

    @patch("app.providers.services.api_request")
    def test_issue_returns_dates(self, mock_api):
        mock_api.return_value = {
            "results": {
                "cover_date": "2023-01-15",
                "store_date": "2023-01-10",
            },
        }

        result = comicvine.issue("99901")

        self.assertEqual(result["cover_date"], "2023-01-15")
        self.assertEqual(result["store_date"], "2023-01-10")

    @patch("app.providers.services.api_request")
    def test_issue_missing_dates(self, mock_api):
        mock_api.return_value = {"results": {}}

        result = comicvine.issue("99902")

        self.assertIsNone(result["cover_date"])
        self.assertIsNone(result["store_date"])
