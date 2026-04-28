from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import Anime, Item, MediaTypes, Sources, Status
from app.views.add_by_link import _extract_query_from_url, _search_for_media


class ExtractQueryTests(TestCase):
    """Test URL slug extraction logic."""

    def test_slug_with_trailing_numeric_id(self):
        """Strip trailing -NNN from slug."""
        url = "https://hianime.to/watch/attack-on-titan-112"
        self.assertEqual(_extract_query_from_url(url), "attack on titan")

    def test_slug_with_dot_id(self):
        """Strip trailing .NNN from slug."""
        url = "https://mangafire.to/read/one-piece.8"
        self.assertEqual(_extract_query_from_url(url), "one piece")

    def test_slug_with_underscore_id(self):
        """Strip trailing _NNN and convert underscores."""
        url = "https://example.com/show/my_hero_academia_42"
        self.assertEqual(_extract_query_from_url(url), "my hero academia")

    def test_slug_without_id(self):
        """Return slug as query when no trailing ID."""
        url = "https://hianime.to/watch/naruto"
        self.assertEqual(_extract_query_from_url(url), "naruto")

    def test_empty_path(self):
        """Return None for root path."""
        self.assertIsNone(_extract_query_from_url("https://example.com/"))

    def test_opaque_short_id(self):
        """Return None when slug is too short."""
        self.assertIsNone(_extract_query_from_url("https://example.com/v/7"))

    def test_bare_domain(self):
        """Return None for URL without path."""
        self.assertIsNone(_extract_query_from_url("https://example.com"))

    def test_multi_segment_path(self):
        """Use last path segment as slug."""
        url = "https://site.com/anime/watch/demon-slayer-123"
        self.assertEqual(_extract_query_from_url(url), "demon slayer")


MOCK_SEARCH_RESULT = {
    "page": 1,
    "total_results": 1,
    "total_pages": 1,
    "results": [
        {
            "media_id": "21",
            "source": Sources.MAL.value,
            "media_type": MediaTypes.ANIME.value,
            "title": "One Punch Man",
            "image": "https://example.com/opm.jpg",
            "synopsis": "A hero who can defeat anyone.",
        }
    ],
}

MOCK_METADATA = {
    "title": "One Punch Man",
    "english_title": "One Punch Man",
    "image": "https://example.com/opm.jpg",
    "synopsis": "A hero who can defeat anyone.",
}

MOCK_EMPTY_SEARCH = {
    "page": 1,
    "total_results": 0,
    "total_pages": 0,
    "results": [],
}

_SEARCH = "app.views.add_by_link.services.search"
_META = "app.views.add_by_link.services.get_media_metadata"


class AddByLinkViewTests(TestCase):
    """Test the add-by-link views."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def test_get_renders_form(self):
        """GET returns the form with media type dropdown."""
        response = self.client.get(reverse("add_by_link"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/add_by_link.html")
        self.assertIn("media_types", response.context)
        self.assertContains(response, "Paste URLs here")

    def test_get_excludes_season_episode(self):
        """Dropdown omits season and episode sub-types."""
        response = self.client.get(reverse("add_by_link"))
        values = [mt["value"] for mt in response.context["media_types"]]
        self.assertNotIn(MediaTypes.SEASON.value, values)
        self.assertNotIn(MediaTypes.EPISODE.value, values)

    @patch(_META, return_value=MOCK_METADATA)
    @patch(_SEARCH, return_value=MOCK_SEARCH_RESULT)
    def test_post_creates_media_with_link(self, _mock_s, _mock_m):
        """POST creates Item + Media with link field set."""
        url = "https://hianime.to/watch/one-punch-man-100"
        response = self.client.post(
            reverse("add_by_link_process"),
            {"media_type": "anime", "links": url},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["added_count"], 1)

        anime = Anime.objects.filter(user=self.user).first()
        self.assertIsNotNone(anime)
        self.assertEqual(anime.status, Status.PLANNING.value)
        self.assertEqual(anime.link, url)
        self.assertEqual(anime.item.title, "One Punch Man")

    @patch(_SEARCH, return_value=MOCK_SEARCH_RESULT)
    def test_post_already_tracked_updates_empty_link(self, _mock_s):
        """Already-tracked item with empty link gets link populated."""
        item = Item.objects.create(
            media_id="21",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="One Punch Man",
            image="https://example.com/opm.jpg",
        )
        Anime.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
            link="",
        )

        url = "https://hianime.to/watch/one-punch-man-100"
        response = self.client.post(
            reverse("add_by_link_process"),
            {"media_type": "anime", "links": url},
        )
        self.assertEqual(response.context["tracked_count"], 1)
        tracked = response.context["already_tracked"][0]
        self.assertTrue(tracked["link_updated"])

        anime = Anime.objects.get(user=self.user)
        self.assertEqual(anime.link, url)

    @patch(_SEARCH, return_value=MOCK_SEARCH_RESULT)
    def test_post_already_tracked_preserves_existing_link(self, _mock_s):
        """Already-tracked item with existing link is not overwritten."""
        item = Item.objects.create(
            media_id="21",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="One Punch Man",
            image="https://example.com/opm.jpg",
        )
        existing_link = "https://other-site.com/opm"
        Anime.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
            link=existing_link,
        )

        response = self.client.post(
            reverse("add_by_link_process"),
            {
                "media_type": "anime",
                "links": "https://hianime.to/watch/one-punch-man-100",
            },
        )
        self.assertEqual(response.context["tracked_count"], 1)
        tracked = response.context["already_tracked"][0]
        self.assertFalse(tracked["link_updated"])

        anime = Anime.objects.get(user=self.user)
        self.assertEqual(anime.link, existing_link)

    @patch(_SEARCH, return_value=MOCK_EMPTY_SEARCH)
    def test_post_no_results_reports_failure(self, _mock_s):
        """URL with no search results is reported as failed."""
        response = self.client.post(
            reverse("add_by_link_process"),
            {
                "media_type": "anime",
                "links": "https://hianime.to/watch/nonexistent-anime-999",
            },
        )
        self.assertEqual(response.context["failed_count"], 1)
        reason = response.context["failed"][0]["reason"]
        self.assertIn("No results found", reason)

    def test_post_unparseable_url_reports_failure(self):
        """URL with unparseable slug is reported as failed."""
        response = self.client.post(
            reverse("add_by_link_process"),
            {"media_type": "anime", "links": "https://example.com/"},
        )
        self.assertEqual(response.context["failed_count"], 1)
        reason = response.context["failed"][0]["reason"]
        self.assertIn("Could not extract", reason)

    @patch(_META, return_value=MOCK_METADATA)
    @patch(_SEARCH)
    def test_post_multiple_links(self, mock_search, _mock_m):
        """Batch with mixed outcomes: 1 added, 1 tracked, 1 failed."""
        item = Item.objects.create(
            media_id="21",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="One Punch Man",
            image="https://example.com/opm.jpg",
        )
        Anime.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        new_result = {
            "page": 1,
            "total_results": 1,
            "total_pages": 1,
            "results": [
                {
                    "media_id": "99",
                    "source": Sources.MAL.value,
                    "media_type": MediaTypes.ANIME.value,
                    "title": "Naruto",
                    "image": "https://example.com/naruto.jpg",
                    "synopsis": "A ninja.",
                }
            ],
        }
        _mock_m.return_value = {
            "title": "Naruto",
            "english_title": "",
            "image": "https://example.com/naruto.jpg",
            "synopsis": "A ninja.",
        }

        def side_effect(_media_type, query, page):
            if "one punch" in query:
                return MOCK_SEARCH_RESULT
            if "naruto" in query:
                return new_result
            return MOCK_EMPTY_SEARCH

        mock_search.side_effect = side_effect

        links = (
            "https://hianime.to/watch/naruto-20\n"
            "https://hianime.to/watch/one-punch-man-100\n"
            "https://hianime.to/watch/nonexistent-xyz-404"
        )
        response = self.client.post(
            reverse("add_by_link_process"),
            {"media_type": "anime", "links": links},
        )
        self.assertEqual(response.context["added_count"], 1)
        self.assertEqual(response.context["tracked_count"], 1)
        self.assertEqual(response.context["failed_count"], 1)

    def test_post_empty_links_ignored(self):
        """Blank-only textarea returns error."""
        response = self.client.post(
            reverse("add_by_link_process"),
            {"media_type": "anime", "links": "\n\n  \n"},
        )
        self.assertIn("error", response.context)

    def test_post_invalid_media_type(self):
        """Invalid media_type returns error."""
        response = self.client.post(
            reverse("add_by_link_process"),
            {
                "media_type": "invalid",
                "links": "https://example.com/test-123",
            },
        )
        self.assertIn("error", response.context)


class SearchForMediaTests(TestCase):
    """Test the _search_for_media helper directly."""

    @patch(_SEARCH, side_effect=ConnectionError("provider down"))
    def test_api_exception_returns_error(self, _mock):
        """When the provider API raises, return None with an error message."""
        result, error = _search_for_media("anime", "one punch man")
        self.assertIsNone(result)
        self.assertEqual(error, "API search failed")

    @patch(_SEARCH, return_value=MOCK_SEARCH_RESULT)
    def test_successful_search_returns_best_match(self, _mock):
        """First result is returned when search succeeds."""
        result, error = _search_for_media("anime", "one punch man")
        self.assertIsNone(error)
        self.assertEqual(result["media_id"], "21")

    @patch(_SEARCH, return_value=MOCK_EMPTY_SEARCH)
    def test_empty_results_returns_no_results_error(self, _mock):
        """When provider returns zero results, return a clear error."""
        result, error = _search_for_media("anime", "xyznonexistent")
        self.assertIsNone(result)
        self.assertEqual(error, "No results found")


class ExtractQueryEdgeCaseTests(TestCase):
    """Edge cases for URL query extraction."""

    def test_malformed_url_returns_none(self):
        """A URL that causes urlparse to raise ValueError returns None."""
        self.assertIsNone(_extract_query_from_url("http://[invalid"))

    def test_whitespace_only_slug(self):
        """A path whose slug becomes empty after cleanup returns None."""
        self.assertIsNone(_extract_query_from_url("https://example.com/---"))

    def test_single_char_slug_returns_none(self):
        """A slug shorter than _MIN_QUERY_LENGTH returns None."""
        self.assertIsNone(_extract_query_from_url("https://example.com/v/x"))


class AddByLinkAPIFailureTests(TestCase):
    """Test the full view when the provider API fails."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test_api_fail", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    @patch(_SEARCH, side_effect=ConnectionError("timeout"))
    def test_api_failure_reports_failed_with_reason(self, _mock):
        """When provider API raises, the result shows 'API search failed'."""
        response = self.client.post(
            reverse("add_by_link_process"),
            {
                "media_type": "anime",
                "links": "https://hianime.to/watch/one-punch-man-100",
            },
        )
        self.assertEqual(response.context["failed_count"], 1)
        self.assertIn("API search failed", response.context["failed"][0]["reason"])
