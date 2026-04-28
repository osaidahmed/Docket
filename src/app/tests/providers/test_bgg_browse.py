from unittest.mock import MagicMock, patch
from xml.etree.ElementTree import Element, SubElement

import requests
from django.conf import settings
from django.core.cache import cache
from django.test import TestCase

from app.models import MediaTypes, Sources
from app.providers import bgg, services
from app.tests.providers._http_error_helpers import make_http_error


class BGGBrowse(TestCase):
    """Test the BGG browse API calls."""

    required_keys = {"media_id", "media_type", "title", "image", "synopsis"}

    def test_hot(self):
        """Test browsing hot board games."""
        response = bgg.browse("hot", 1)

        self.assertGreater(len(response["results"]), 0)
        for item in response["results"]:
            self.assertTrue(all(key in item for key in self.required_keys))
            self.assertEqual(item["media_type"], MediaTypes.BOARDGAME.value)

    def test_pagination(self):
        """Test that pagination returns different pages."""
        page1 = bgg.browse("hot", 1)
        page2 = bgg.browse("hot", 2)

        self.assertEqual(page1["page"], 1)
        self.assertEqual(page2["page"], 2)

    def test_response_format(self):
        """Test that the response has the expected keys."""
        response = bgg.browse("hot", 1)

        self.assertIn("page", response)
        self.assertIn("total_results", response)
        self.assertIn("total_pages", response)
        self.assertIn("results", response)


def _build_search_xml(items):
    root = Element("items")
    for game_id, name in items:
        item = SubElement(root, "item", {"id": game_id})
        SubElement(item, "name", {"value": name})
    return root


def _build_thing_xml(items):
    root = Element("items")
    for game_id, thumbnail, image, description in items:
        item = SubElement(root, "item", {"id": game_id})
        if thumbnail:
            t = SubElement(item, "thumbnail")
            t.text = thumbnail
        if image:
            i = SubElement(item, "image")
            i.text = image
        if description:
            d = SubElement(item, "description")
            d.text = description
    return root


def _build_boardgame_xml(
    game_id="123",
    name="Test Game",
    image_url="http://example.com/img.jpg",
    description="A test game",
    year="2020",
    minplayers="2",
    maxplayers="4",
    playtime="60",
    minage="10",
    avg_rating="7.5",
    usersrated="1000",
    categories=None,
    designers=None,
    publishers=None,
):
    root = Element("items")
    item = SubElement(root, "item", {"id": game_id, "type": "boardgame"})
    SubElement(item, "name", {"type": "primary", "value": name})
    img = SubElement(item, "image")
    img.text = image_url
    desc = SubElement(item, "description")
    desc.text = description
    SubElement(item, "yearpublished", {"value": year})
    SubElement(item, "minplayers", {"value": minplayers})
    SubElement(item, "maxplayers", {"value": maxplayers})
    SubElement(item, "playingtime", {"value": playtime})
    SubElement(item, "minage", {"value": minage})

    stats = SubElement(item, "statistics")
    ratings = SubElement(stats, "ratings")
    SubElement(ratings, "average", {"value": avg_rating})
    SubElement(ratings, "usersrated", {"value": usersrated})

    for cat in categories or []:
        SubElement(item, "link", {"type": "boardgamecategory", "value": cat})
    for des in designers or []:
        SubElement(item, "link", {"type": "boardgamedesigner", "value": des})
    for pub in publishers or []:
        SubElement(item, "link", {"type": "boardgamepublisher", "value": pub})

    return root


class BGGHandleError(TestCase):
    """Test BGG handle_error function."""

    def test_unauthorized(self):
        mock_response = MagicMock()
        mock_response.status_code = 401

        error = requests.exceptions.HTTPError("401")
        error.response = mock_response

        with self.assertRaises(services.ProviderAPIError) as cm:
            bgg.handle_error(error)

        self.assertIn("authorization", str(cm.exception).lower())

    def test_other_error(self):
        mock_response = MagicMock()
        mock_response.status_code = 500

        error = requests.exceptions.HTTPError("500")
        error.response = mock_response

        with self.assertRaises(services.ProviderAPIError):
            bgg.handle_error(error)


class BGGSearch(TestCase):
    """Test BGG search functionality."""

    @patch("app.providers.bgg._fetch_details")
    @patch("app.providers.services.api_request")
    def test_search_returns_results(self, mock_api, mock_details):
        mock_api.return_value = _build_search_xml(
            [
                ("1", "Catan"),
                ("2", "Ticket to Ride"),
            ]
        )
        mock_details.return_value = {
            "1": {"image": "http://img/1.jpg", "description": "Trade game"},
            "2": {"image": "http://img/2.jpg", "description": "Train game"},
        }

        response = bgg.search("Catan", 1)

        self.assertEqual(len(response["results"]), 2)
        self.assertEqual(response["results"][0]["title"], "Catan")
        self.assertEqual(
            response["results"][0]["media_type"], MediaTypes.BOARDGAME.value
        )
        self.assertEqual(response["results"][0]["source"], Sources.BGG.value)
        self.assertEqual(response["results"][0]["image"], "http://img/1.jpg")

    @patch("app.providers.bgg._fetch_details")
    @patch("app.providers.services.api_request")
    def test_search_pagination(self, mock_api, mock_details):
        items = [(str(i), f"Game {i}") for i in range(25)]
        mock_api.return_value = _build_search_xml(items)
        mock_details.return_value = {}

        page1 = bgg.search("Game", 1)
        self.assertEqual(len(page1["results"]), 20)
        self.assertEqual(page1["total_results"], 25)

        page2 = bgg.search("Game", 2)
        self.assertEqual(len(page2["results"]), 5)

    @patch("app.providers.bgg._fetch_details")
    @patch("app.providers.services.api_request")
    def test_search_missing_details_uses_defaults(self, mock_api, mock_details):
        mock_api.return_value = _build_search_xml([("1", "No Details")])
        mock_details.return_value = {}

        response = bgg.search("No Details", 1)

        self.assertEqual(response["results"][0]["image"], settings.IMG_NONE)
        self.assertEqual(response["results"][0]["synopsis"], "")


class BGGFetchDetails(TestCase):
    """Test BGG _fetch_details function."""

    @patch("app.providers.services.api_request")
    def test_empty_ids(self, mock_api):
        result = bgg._fetch_details([])
        self.assertEqual(result, {})
        mock_api.assert_not_called()

    @patch("app.providers.services.api_request")
    def test_thumbnail_preferred_over_image(self, mock_api):
        mock_api.return_value = _build_thing_xml(
            [
                ("1", "http://thumb.jpg", "http://img.jpg", "desc"),
            ]
        )
        result = bgg._fetch_details(["1"])
        self.assertEqual(result["1"]["image"], "http://thumb.jpg")

    @patch("app.providers.services.api_request")
    def test_fallback_to_image_when_no_thumbnail(self, mock_api):
        mock_api.return_value = _build_thing_xml(
            [
                ("1", None, "http://img.jpg", "desc"),
            ]
        )
        result = bgg._fetch_details(["1"])
        self.assertEqual(result["1"]["image"], "http://img.jpg")

    @patch("app.providers.services.api_request")
    def test_no_image_no_description(self, mock_api):
        mock_api.return_value = _build_thing_xml([("1", None, None, None)])
        result = bgg._fetch_details(["1"])
        self.assertNotIn("image", result["1"])
        self.assertNotIn("description", result["1"])

    @patch("app.providers.services.api_request")
    def test_http_error_returns_empty(self, mock_api):
        mock_api.side_effect = requests.exceptions.HTTPError(
            response=MagicMock(status_code=500, text="error")
        )
        result = bgg._fetch_details(["1"])
        self.assertEqual(result, {})


class BGGBoardgame(TestCase):
    """Test BGG boardgame metadata function."""

    @patch("app.providers.services.api_request")
    def test_boardgame_metadata(self, mock_api):
        mock_api.return_value = _build_boardgame_xml(
            categories=["Strategy", "Economic"],
            designers=["Klaus Teuber"],
            publishers=["Kosmos", "Catan Studio"],
        )

        response = bgg.boardgame("123")

        self.assertEqual(response["title"], "Test Game")
        self.assertEqual(response["media_id"], "123")
        self.assertEqual(response["source"], Sources.BGG.value)
        self.assertEqual(response["media_type"], MediaTypes.BOARDGAME.value)
        self.assertEqual(response["image"], "http://example.com/img.jpg")
        self.assertEqual(response["synopsis"], "A test game")
        self.assertEqual(response["genres"], ["Strategy", "Economic"])
        self.assertEqual(response["score"], 7.5)
        self.assertEqual(response["score_count"], 1000)
        self.assertEqual(response["details"]["year"], "2020")
        self.assertEqual(response["details"]["players"], "2-4 players")
        self.assertEqual(response["details"]["playtime"], "60 min")
        self.assertEqual(response["details"]["min_age"], "10+")
        self.assertEqual(response["details"]["designers"], "Klaus Teuber")
        self.assertEqual(response["details"]["publishers"], "Kosmos, Catan Studio")

    @patch("app.providers.services.api_request")
    def test_boardgame_not_found(self, mock_api):
        root = Element("items")
        mock_api.return_value = root

        with self.assertRaises(services.ProviderAPIError):
            bgg.boardgame("999999")


class BGGHelpers(TestCase):
    """Test BGG helper functions."""

    def test_get_title_missing(self):
        item = Element("item")
        self.assertEqual(bgg.get_title(item), "Unknown")

    def test_get_image_missing(self):
        item = Element("item")
        self.assertEqual(bgg.get_image(item), settings.IMG_NONE)

    def test_get_description_missing(self):
        item = Element("item")
        self.assertEqual(bgg.get_description(item), "No synopsis available")

    def test_get_year_missing(self):
        item = Element("item")
        self.assertIsNone(bgg.get_year(item))

    def test_get_players_same_min_max(self):
        item = Element("item")
        SubElement(item, "minplayers", {"value": "2"})
        SubElement(item, "maxplayers", {"value": "2"})
        self.assertEqual(bgg.get_players(item), "2 players")

    def test_get_players_range(self):
        item = Element("item")
        SubElement(item, "minplayers", {"value": "2"})
        SubElement(item, "maxplayers", {"value": "5"})
        self.assertEqual(bgg.get_players(item), "2-5 players")

    def test_get_players_missing(self):
        item = Element("item")
        self.assertIsNone(bgg.get_players(item))

    def test_get_playtime(self):
        item = Element("item")
        SubElement(item, "playingtime", {"value": "90"})
        self.assertEqual(bgg.get_playtime(item), "90 min")

    def test_get_playtime_missing(self):
        item = Element("item")
        self.assertIsNone(bgg.get_playtime(item))

    def test_get_min_age(self):
        item = Element("item")
        SubElement(item, "minage", {"value": "14"})
        self.assertEqual(bgg.get_min_age(item), "14+")

    def test_get_min_age_missing(self):
        item = Element("item")
        self.assertIsNone(bgg.get_min_age(item))

    def test_get_score_valid(self):
        item = Element("item")
        stats = SubElement(item, "statistics")
        ratings = SubElement(stats, "ratings")
        SubElement(ratings, "average", {"value": "8.123"})
        self.assertEqual(bgg.get_score(item), 8.1)

    def test_get_score_invalid_value(self):
        item = Element("item")
        stats = SubElement(item, "statistics")
        ratings = SubElement(stats, "ratings")
        SubElement(ratings, "average", {"value": "N/A"})
        self.assertIsNone(bgg.get_score(item))

    def test_get_score_missing(self):
        item = Element("item")
        self.assertIsNone(bgg.get_score(item))

    def test_get_score_count_valid(self):
        item = Element("item")
        stats = SubElement(item, "statistics")
        ratings = SubElement(stats, "ratings")
        SubElement(ratings, "usersrated", {"value": "500"})
        self.assertEqual(bgg.get_score_count(item), 500)

    def test_get_score_count_invalid(self):
        item = Element("item")
        stats = SubElement(item, "statistics")
        ratings = SubElement(stats, "ratings")
        SubElement(ratings, "usersrated", {"value": "N/A"})
        self.assertIsNone(bgg.get_score_count(item))

    def test_get_score_count_missing(self):
        item = Element("item")
        self.assertIsNone(bgg.get_score_count(item))

    def test_get_categories_empty(self):
        item = Element("item")
        self.assertIsNone(bgg.get_categories(item))

    def test_get_designers_empty(self):
        item = Element("item")
        self.assertIsNone(bgg.get_designers(item))

    def test_get_designers_multiple(self):
        item = Element("item")
        SubElement(item, "link", {"type": "boardgamedesigner", "value": "Alice"})
        SubElement(item, "link", {"type": "boardgamedesigner", "value": "Bob"})
        self.assertEqual(bgg.get_designers(item), "Alice, Bob")

    def test_get_publishers_empty(self):
        item = Element("item")
        self.assertIsNone(bgg.get_publishers(item))

    def test_get_publishers_truncated_to_three(self):
        item = Element("item")
        for name in ["Pub1", "Pub2", "Pub3", "Pub4"]:
            SubElement(item, "link", {"type": "boardgamepublisher", "value": name})
        self.assertEqual(bgg.get_publishers(item), "Pub1, Pub2, Pub3")


class BGGSearchHTTPError(TestCase):
    def setUp(self):
        cache.clear()

    @patch("app.providers.services.api_request")
    def test_search_http_error_raises(self, mock_api):
        mock_api.side_effect = make_http_error(500, {"err": "x"})
        with self.assertRaises(services.ProviderAPIError):
            bgg.search("anything", 1)

    @patch("app.providers.services.api_request")
    def test_browse_http_error_raises(self, mock_api):
        mock_api.side_effect = make_http_error(500, {"err": "x"})
        with self.assertRaises(services.ProviderAPIError):
            bgg.browse("hot", 1)

    @patch("app.providers.services.api_request")
    def test_boardgame_http_error_raises(self, mock_api):
        mock_api.side_effect = make_http_error(500, {"err": "x"})
        with self.assertRaises(services.ProviderAPIError):
            bgg.boardgame("123")
