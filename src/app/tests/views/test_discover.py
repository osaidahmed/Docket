from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import MediaTypes, Sources


def _mock_section_data(count=3):
    return {
        "page": 1,
        "total_results": count,
        "total_pages": 1,
        "results": [
            {
                "media_id": str(i),
                "source": Sources.MAL.value,
                "media_type": MediaTypes.ANIME.value,
                "title": f"Test Anime {i}",
                "image": f"https://img.test/{i}.jpg",
                "synopsis": "Synopsis",
            }
            for i in range(count)
        ],
        "has_next_page": False,
    }


def _mock_schedule_data():
    return [
        {
            "media_id": "1",
            "source": Sources.MAL.value,
            "media_type": MediaTypes.ANIME.value,
            "title": "Scheduled Anime",
            "image": "https://img.test/1.jpg",
            "airing_at": 1700000000,
            "episode": 5,
        }
    ]


def _discover_url(media_type):
    return (
        reverse("medialist_browse_tab", kwargs={"media_type": media_type})
        + "?tab=discover"
    )


class DiscoverViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    @patch("app.providers.services.discover_sections")
    def test_discover_movie_200(self, mock_discover):
        mock_discover.return_value = {"trending": _mock_section_data()}
        response = self.client.get(_discover_url("movie"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/partials/discover_content.html")

    @patch("app.providers.services.discover_sections")
    def test_discover_tv_200(self, mock_discover):
        mock_discover.return_value = {"trending": _mock_section_data()}
        self.assertEqual(self.client.get(_discover_url("tv")).status_code, 200)

    @patch("app.providers.services.discover_sections")
    def test_discover_anime_200(self, mock_discover):
        mock_discover.return_value = {
            "trending": _mock_section_data(),
            "schedule": _mock_schedule_data(),
        }
        self.assertEqual(self.client.get(_discover_url("anime")).status_code, 200)

    @patch("app.providers.services.discover_sections")
    def test_discover_manga_200(self, mock_discover):
        mock_discover.return_value = {"trending": _mock_section_data()}
        self.assertEqual(self.client.get(_discover_url("manga")).status_code, 200)

    @patch("app.providers.services.discover_sections")
    def test_discover_game_200(self, mock_discover):
        mock_discover.return_value = {"trending": _mock_section_data()}
        self.assertEqual(self.client.get(_discover_url("game")).status_code, 200)

    def test_unsupported_type_redirects_to_medialist(self):
        """Discover for a type without sections (e.g. book) redirects to medialist."""
        response = self.client.get(_discover_url("book"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url, reverse("medialist", kwargs={"media_type": "book"})
        )

    @patch("app.providers.services.discover_sections")
    def test_context_has_current_view_discover(self, mock_discover):
        mock_discover.return_value = {"trending": _mock_section_data()}
        response = self.client.get(_discover_url("movie"))
        self.assertEqual(response.context["current_view"], "discover")

    @patch("app.providers.services.browse")
    def test_browse_default_view(self, mock_browse):
        mock_browse.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        url = reverse("medialist_browse_tab", kwargs={"media_type": "movie"})
        response = self.client.get(url)
        self.assertEqual(response.context["current_view"], "browse")

    @patch("app.providers.services.browse")
    def test_has_discover_in_browse_context(self, mock_browse):
        mock_browse.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        url = reverse("medialist_browse_tab", kwargs={"media_type": "anime"})
        response = self.client.get(url)
        self.assertTrue(response.context["has_discover"])

    @patch("app.providers.services.browse")
    def test_no_discover_for_book(self, mock_browse):
        mock_browse.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        url = reverse("medialist_browse_tab", kwargs={"media_type": "book"})
        response = self.client.get(url)
        self.assertFalse(response.context["has_discover"])

    @patch("app.providers.services.discover_sections")
    def test_section_with_none_data_skipped(self, mock_discover):
        mock_discover.return_value = {
            "trending": _mock_section_data(),
            "upcoming": None,
        }
        response = self.client.get(_discover_url("movie"))
        section_keys = [s["key"] for s in response.context["sections"]]
        self.assertNotIn("upcoming", section_keys)

    def test_requires_auth(self):
        self.client.logout()
        response = self.client.get(_discover_url("anime"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)


class MedialistSectionTests(TestCase):
    """Tests for the discover section load-more endpoint at /medialist/<type>/section/<key>."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    @patch("app.providers.services.discover_section_page")
    def test_load_more_returns_items(self, mock_page):
        mock_page.return_value = _mock_section_data(5)
        url = reverse(
            "medialist_section",
            kwargs={"media_type": "anime", "section_key": "recently_updated"},
        )
        response = self.client.get(url + "?page=2")
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/partials/discover_grid_items.html")

    @patch("app.providers.services.discover_section_page")
    def test_load_more_has_next_page_true(self, mock_page):
        data = _mock_section_data(5)
        data["has_next_page"] = True
        mock_page.return_value = data
        url = reverse(
            "medialist_section",
            kwargs={"media_type": "anime", "section_key": "recently_updated"},
        )
        response = self.client.get(url + "?page=2")
        self.assertContains(response, "Load more")

    @patch("app.providers.services.discover_section_page")
    def test_load_more_has_next_page_false(self, mock_page):
        data = _mock_section_data(5)
        data["has_next_page"] = False
        mock_page.return_value = data
        url = reverse(
            "medialist_section",
            kwargs={"media_type": "anime", "section_key": "recently_updated"},
        )
        response = self.client.get(url + "?page=2")
        self.assertNotContains(response, "Load more")

    @patch("app.providers.services.discover_section_page")
    def test_load_more_uses_total_pages_fallback(self, mock_page):
        mock_page.return_value = {
            "page": 2,
            "total_results": 100,
            "total_pages": 5,
            "results": [
                {
                    "media_id": "1",
                    "source": Sources.MAL.value,
                    "media_type": MediaTypes.ANIME.value,
                    "title": "Test",
                    "image": "https://img.test/1.jpg",
                    "synopsis": "",
                }
            ],
        }
        url = reverse(
            "medialist_section",
            kwargs={"media_type": "anime", "section_key": "recently_updated"},
        )
        response = self.client.get(url + "?page=2")
        self.assertContains(response, "Load more")

    def test_invalid_section_key_returns_empty(self):
        url = reverse(
            "medialist_section",
            kwargs={"media_type": "anime", "section_key": "nonexistent"},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class DiscoverHelperTests(TestCase):
    def test_has_next_with_non_dict(self):
        from app.views.discover import _has_next

        self.assertFalse(_has_next(None))
        self.assertFalse(_has_next([]))

    def test_has_next_with_explicit_flag(self):
        from app.views.discover import _has_next

        self.assertTrue(_has_next({"has_next_page": True}))
        self.assertFalse(_has_next({"has_next_page": False}))

    def test_has_next_uses_pagination(self):
        from app.views.discover import _has_next

        self.assertTrue(_has_next({"page": 1, "total_pages": 5}))
        self.assertFalse(_has_next({"page": 5, "total_pages": 5}))
