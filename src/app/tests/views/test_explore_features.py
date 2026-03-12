from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import (
    Anime,
    Item,
    MediaTypes,
    Sources,
    Status,
)


class ExploreSeasonalViewTests(TestCase):
    """Test the seasonal anime browse feature."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)
        cls.anime_url = reverse(
            "explore_type", kwargs={"media_type": MediaTypes.ANIME.value}
        )

    def setUp(self):
        self.client.login(**self.credentials)

    @patch("app.config.get_current_anime_season", return_value=(2026, "winter"))
    @patch("app.providers.services.browse")
    def test_seasonal_defaults_to_current_season(self, mock_browse, _mock_season):
        mock_browse.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        response = self.client.get(self.anime_url + "?category=seasonal")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["year"], 2026)
        self.assertEqual(response.context["season"], "winter")
        mock_browse.assert_called_once_with(
            MediaTypes.ANIME.value, "seasonal", 1, year=2026, season="winter"
        )

    @patch("app.providers.services.browse")
    def test_seasonal_custom_year_and_season(self, mock_browse):
        mock_browse.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        response = self.client.get(
            self.anime_url + "?category=seasonal&year=2024&season=summer"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["year"], 2024)
        self.assertEqual(response.context["season"], "summer")
        mock_browse.assert_called_once_with(
            MediaTypes.ANIME.value, "seasonal", 1, year=2024, season="summer"
        )

    @patch("app.providers.services.browse")
    def test_seasonal_includes_season_picker_context(self, mock_browse):
        mock_browse.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        response = self.client.get(
            self.anime_url + "?category=seasonal&year=2025&season=fall"
        )

        self.assertTrue(response.context["show_season_picker"])
        self.assertEqual(response.context["prev_year"], 2024)
        self.assertEqual(response.context["next_year"], 2026)
        self.assertEqual(len(response.context["seasons"]), 4)

    @patch("app.providers.services.browse")
    def test_seasonal_extra_params_in_context(self, mock_browse):
        mock_browse.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        response = self.client.get(
            self.anime_url + "?category=seasonal&year=2025&season=spring"
        )

        self.assertIn("year=2025", response.context["extra_params"])
        self.assertIn("season=spring", response.context["extra_params"])

    @patch("app.providers.services.browse")
    def test_seasonal_pagination_preserves_params(self, mock_browse):
        mock_browse.return_value = {
            "page": 2,
            "total_results": 50,
            "total_pages": 3,
            "results": [
                {
                    "media_id": "1",
                    "title": "Test Anime",
                    "media_type": MediaTypes.ANIME.value,
                    "source": Sources.MAL.value,
                    "image": "http://example.com/image.jpg",
                    "synopsis": "",
                },
            ],
        }

        response = self.client.get(
            self.anime_url + "?category=seasonal&year=2024&season=fall&page=2"
        )

        self.assertEqual(response.status_code, 200)
        mock_browse.assert_called_once_with(
            MediaTypes.ANIME.value, "seasonal", 2, year=2024, season="fall"
        )

    @patch("app.providers.services.browse")
    def test_seasonal_htmx_includes_season_picker(self, mock_browse):
        mock_browse.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        response = self.client.get(
            self.anime_url + "?category=seasonal&year=2025&season=winter",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/explore_results.html")
        self.assertTrue(response.context["show_season_picker"])
        self.assertEqual(response.context["current_category"], "seasonal")

    @patch("app.providers.services.browse")
    def test_non_seasonal_has_no_season_picker(self, mock_browse):
        mock_browse.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        response = self.client.get(self.anime_url + "?category=airing")

        self.assertNotIn("show_season_picker", response.context)


class ExploreUpcomingTests(TestCase):
    """Test that upcoming categories hide the archive/completion button."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def _mock_results(self, media_type, source, is_ongoing=None):
        result = {
            "media_id": "999",
            "title": "Upcoming Item",
            "media_type": media_type,
            "source": source,
            "image": "http://example.com/image.jpg",
            "synopsis": "",
        }
        if is_ongoing is not None:
            result["is_ongoing"] = is_ongoing
        return {
            "page": 1,
            "total_results": 1,
            "total_pages": 1,
            "results": [result],
        }

    @patch("app.providers.services.browse")
    def test_upcoming_anime_hides_archive_button(self, mock_browse):
        mock_browse.return_value = self._mock_results(
            MediaTypes.ANIME.value, Sources.MAL.value
        )
        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.ANIME.value})
            + "?category=upcoming",
        )
        self.assertTrue(response.context["is_upcoming"])
        self.assertNotContains(response, "quick_archive")

    @patch("app.providers.services.browse")
    def test_anticipated_games_hides_archive_button(self, mock_browse):
        mock_browse.return_value = self._mock_results(
            MediaTypes.GAME.value, Sources.IGDB.value
        )
        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.GAME.value})
            + "?category=anticipated",
        )
        self.assertTrue(response.context["is_upcoming"])
        self.assertNotContains(response, "quick_archive")

    @patch("app.providers.services.browse")
    def test_airing_anime_shows_caught_up_button(self, mock_browse):
        mock_browse.return_value = self._mock_results(
            MediaTypes.ANIME.value, Sources.MAL.value, is_ongoing=True
        )
        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.ANIME.value})
            + "?category=airing",
        )
        self.assertFalse(response.context["is_upcoming"])
        self.assertContains(response, "quick_catch_up_add")
        self.assertNotContains(response, "quick_archive")

    @patch("app.config.get_current_anime_season", return_value=(2026, "winter"))
    @patch("app.providers.services.browse")
    def test_seasonal_future_hides_archive_button(self, mock_browse, _mock_season):
        mock_browse.return_value = self._mock_results(
            MediaTypes.ANIME.value, Sources.MAL.value
        )
        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.ANIME.value})
            + "?category=seasonal&year=2027&season=spring",
        )
        self.assertTrue(response.context["is_upcoming"])
        self.assertNotContains(response, "quick_archive")

    @patch("app.config.get_current_anime_season", return_value=(2026, "winter"))
    @patch("app.providers.services.browse")
    def test_seasonal_current_shows_caught_up_button(self, mock_browse, _mock_season):
        mock_browse.return_value = self._mock_results(
            MediaTypes.ANIME.value, Sources.MAL.value, is_ongoing=True
        )
        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.ANIME.value})
            + "?category=seasonal&year=2026&season=winter",
        )
        self.assertFalse(response.context["is_upcoming"])
        self.assertContains(response, "quick_catch_up_add")
        self.assertNotContains(response, "quick_archive")

    @patch("app.providers.services.browse_filtered")
    def test_tv_trending_shows_archive_button(self, mock_browse_filtered):
        mock_browse_filtered.return_value = self._mock_results(
            MediaTypes.TV.value, Sources.TMDB.value
        )
        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.TV.value})
            + "?category=trending",
        )
        self.assertFalse(response.context["is_upcoming"])
        self.assertContains(response, "quick_archive")

    @patch("app.providers.services.browse_filtered")
    def test_tv_on_the_air_shows_caught_up_button(self, mock_browse_filtered):
        mock_browse_filtered.return_value = self._mock_results(
            MediaTypes.TV.value, Sources.TMDB.value
        )
        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.TV.value})
            + "?category=on_the_air",
        )
        self.assertFalse(response.context["is_upcoming"])
        self.assertContains(response, "quick_catch_up_add")
        self.assertNotContains(response, "quick_archive")


class ExplorePaginationDisplayTests(TestCase):
    """Test pagination display for exact vs inexact totals."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    @patch("app.providers.services.browse_filtered")
    def test_exact_total_shows_page_count(self, mock_browse_filtered):
        mock_browse_filtered.return_value = {
            "page": 1,
            "total_results": 50,
            "total_pages": 3,
            "total_exact": True,
            "results": [
                {
                    "media_id": "1",
                    "title": "Test Movie",
                    "media_type": MediaTypes.MOVIE.value,
                    "source": Sources.TMDB.value,
                    "image": "http://example.com/image.jpg",
                    "synopsis": "",
                },
            ],
        }

        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.MOVIE.value})
            + "?category=popular",
        )

        self.assertContains(response, "Page 1 of 3 (50 results)")

    @patch("app.providers.services.browse")
    def test_inexact_total_hides_page_count(self, mock_browse):
        mock_browse.return_value = {
            "page": 1,
            "total_results": 120,
            "total_pages": 6,
            "total_exact": False,
            "results": [
                {
                    "media_id": "1",
                    "title": "Test Anime",
                    "media_type": MediaTypes.ANIME.value,
                    "source": Sources.MAL.value,
                    "image": "http://example.com/image.jpg",
                    "synopsis": "",
                },
            ],
        }

        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.ANIME.value})
            + "?category=all",
        )

        self.assertNotContains(response, "of 6")
        self.assertNotContains(response, "120 results")


class ExploreFilterTests(TestCase):
    """Test explore filter and hide_watched_anime functionality."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "filter_test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    @patch("app.providers.services.browse_filtered")
    def test_explore_anime_with_genre_filter(self, mock_filtered):
        mock_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.ANIME.value})
            + "?category=all&genres=1,2",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["has_active_filters"])
        mock_filtered.assert_called_once()

    @patch("app.providers.services.browse")
    def test_hide_watched_anime_filters_manga(self, mock_browse):
        anime_item = Item.objects.create(
            media_id="100",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Attack on Titan",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
            item=anime_item,
            user=self.user,
            status=Status.COMPLETED.value,
        )

        mock_browse.return_value = {
            "page": 1,
            "total_results": 2,
            "total_pages": 1,
            "results": [
                {
                    "media_id": "200",
                    "title": "Attack on Titan",
                    "media_type": MediaTypes.MANGA.value,
                    "source": Sources.MAL.value,
                    "image": "http://example.com/image.jpg",
                    "synopsis": "",
                },
                {
                    "media_id": "201",
                    "title": "Berserk",
                    "media_type": MediaTypes.MANGA.value,
                    "source": Sources.MAL.value,
                    "image": "http://example.com/image2.jpg",
                    "synopsis": "",
                },
            ],
        }

        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.MANGA.value})
            + "?category=all&hide_watched_anime=1",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["hide_watched_anime"])
        self.assertIn("hide_watched_anime=1", response.context["extra_params"])
