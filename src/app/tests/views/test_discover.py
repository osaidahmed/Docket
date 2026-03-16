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
        url = reverse("discover_type", kwargs={"media_type": "movie"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/discover.html")

    @patch("app.providers.services.discover_sections")
    def test_discover_tv_200(self, mock_discover):
        mock_discover.return_value = {"trending": _mock_section_data()}
        url = reverse("discover_type", kwargs={"media_type": "tv"})
        self.assertEqual(self.client.get(url).status_code, 200)

    @patch("app.providers.services.discover_sections")
    def test_discover_anime_200(self, mock_discover):
        mock_discover.return_value = {
            "trending": _mock_section_data(),
            "schedule": _mock_schedule_data(),
        }
        url = reverse("discover_type", kwargs={"media_type": "anime"})
        self.assertEqual(self.client.get(url).status_code, 200)

    @patch("app.providers.services.discover_sections")
    def test_discover_manga_200(self, mock_discover):
        mock_discover.return_value = {"trending": _mock_section_data()}
        url = reverse("discover_type", kwargs={"media_type": "manga"})
        self.assertEqual(self.client.get(url).status_code, 200)

    @patch("app.providers.services.discover_sections")
    def test_discover_game_200(self, mock_discover):
        mock_discover.return_value = {"trending": _mock_section_data()}
        url = reverse("discover_type", kwargs={"media_type": "game"})
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_unsupported_type_redirects(self):
        url = reverse("discover_type", kwargs={"media_type": "book"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)

    @patch("app.providers.services.discover_sections")
    def test_context_has_sections(self, mock_discover):
        mock_discover.return_value = {
            "trending": _mock_section_data(),
            "now_playing": _mock_section_data(),
        }
        url = reverse("discover_type", kwargs={"media_type": "movie"})
        response = self.client.get(url)
        self.assertIn("sections", response.context)

    @patch("app.providers.services.discover_sections")
    def test_context_has_text_color(self, mock_discover):
        mock_discover.return_value = {"trending": _mock_section_data()}
        url = reverse("discover_type", kwargs={"media_type": "movie"})
        response = self.client.get(url)
        self.assertIn("text_color", response.context)
        self.assertTrue(response.context["text_color"])

    @patch("app.providers.services.discover_sections")
    def test_none_section_skipped(self, mock_discover):
        mock_discover.return_value = {
            "trending": _mock_section_data(),
            "upcoming": None,
        }
        url = reverse("discover_type", kwargs={"media_type": "movie"})
        response = self.client.get(url)
        section_keys = [s["key"] for s in response.context["sections"]]
        self.assertNotIn("upcoming", section_keys)

    def test_requires_auth(self):
        self.client.logout()
        url = reverse("discover_type", kwargs={"media_type": "anime"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    @patch("app.providers.services.discover_sections")
    def test_post_not_allowed(self, mock_discover):
        url = reverse("discover_type", kwargs={"media_type": "movie"})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 405)


class DiscoverSectionTests(TestCase):
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
            "discover_section",
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
            "discover_section",
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
            "discover_section",
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
            "discover_section",
            kwargs={"media_type": "anime", "section_key": "recently_updated"},
        )
        response = self.client.get(url + "?page=2")
        self.assertContains(response, "Load more")

    def test_invalid_section_key_returns_empty(self):
        url = reverse(
            "discover_section",
            kwargs={"media_type": "anime", "section_key": "nonexistent"},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
