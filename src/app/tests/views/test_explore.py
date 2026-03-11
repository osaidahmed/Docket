import re
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


class ExploreViewTests(TestCase):
    """Test the explore landing page view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def test_explore_landing_page(self):
        """Test the explore landing page renders correctly."""
        response = self.client.get(reverse("explore"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/explore.html")
        self.assertIn("explorable_types", response.context)

    def test_explore_shows_enabled_types_only(self):
        """Test that only enabled explorable types are shown."""
        self.user.game_enabled = False
        self.user.save()

        response = self.client.get(reverse("explore"))

        types = [t["media_type"] for t in response.context["explorable_types"]]
        self.assertIn(MediaTypes.TV.value, types)
        self.assertIn(MediaTypes.ANIME.value, types)
        self.assertNotIn(MediaTypes.GAME.value, types)

    def test_explore_excludes_non_explorable_types(self):
        """Test that types without explore support are excluded."""
        response = self.client.get(reverse("explore"))

        types = [t["media_type"] for t in response.context["explorable_types"]]
        self.assertNotIn(MediaTypes.SEASON.value, types)
        self.assertNotIn(MediaTypes.EPISODE.value, types)

    def test_explore_type_cards_include_categories(self):
        """Test that each explorable type card includes its categories."""
        response = self.client.get(reverse("explore"))

        for type_info in response.context["explorable_types"]:
            self.assertIn("categories", type_info)
            self.assertGreater(len(type_info["categories"]), 0)

    def test_explore_requires_get(self):
        """Test that explore rejects POST requests."""
        response = self.client.post(reverse("explore"))
        self.assertEqual(response.status_code, 405)


class ExploreTypeViewTests(TestCase):
    """Test the explore_type view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    @patch("app.providers.services.browse_filtered")
    def test_explore_type_default_category(self, mock_browse_filtered):
        """Test that explore_type uses the first category as default."""
        mock_browse_filtered.return_value = {
            "page": 1,
            "total_results": 1,
            "total_pages": 1,
            "results": [
                {
                    "media_id": "1",
                    "title": "Test TV",
                    "media_type": MediaTypes.TV.value,
                    "source": Sources.TMDB.value,
                    "image": "http://example.com/image.jpg",
                    "synopsis": "A test synopsis.",
                },
            ],
        }

        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.TV.value}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/explore_type.html")
        self.assertEqual(response.context["current_category"], "trending")
        mock_browse_filtered.assert_called_once_with(
            MediaTypes.TV.value, {"sort_by": "popularity.desc"}, 1
        )

    @patch("app.providers.services.browse_filtered")
    def test_explore_type_custom_category(self, mock_browse_filtered):
        """Test that explore_type accepts a category query parameter."""
        mock_browse_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.TV.value})
            + "?category=popular",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_category"], "popular")

    @patch("app.providers.services.browse_filtered")
    def test_explore_type_invalid_category_falls_back(self, mock_browse_filtered):
        """Test that an invalid category falls back to the first category."""
        mock_browse_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.TV.value})
            + "?category=invalid",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_category"], "trending")

    def test_explore_type_non_explorable_redirects(self):
        """Test that a non-explorable type redirects to the explore landing."""
        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.SEASON.value}),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("explore"))

    @patch("app.providers.services.browse_filtered")
    def test_explore_type_htmx_returns_partial(self, mock_browse_filtered):
        """Test that HTMX requests return the partial template."""
        mock_browse_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.TV.value}),
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/explore_results.html")

    @patch("app.providers.services.browse_filtered")
    def test_explore_type_htmx_includes_category_context(self, mock_browse_filtered):
        """Test that HTMX partial includes categories for chip highlighting."""
        mock_browse_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.TV.value})
            + "?category=popular",
            HTTP_HX_REQUEST="true",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_category"], "popular")
        self.assertIn("categories", response.context)
        self.assertGreater(len(response.context["categories"]), 0)

    @patch("app.providers.services.browse_filtered")
    def test_explore_type_htmx_category_switch(self, mock_browse_filtered):
        """Test that switching categories via HTMX updates current_category."""
        mock_browse_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        # First request with default category
        response1 = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.TV.value}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response1.context["current_category"], "trending")

        # Switch to top_rated via HTMX
        response2 = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.TV.value})
            + "?category=top_rated",
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response2.context["current_category"], "top_rated")

    @patch("app.providers.services.browse_filtered")
    def test_explore_type_pagination(self, mock_browse_filtered):
        """Test that page parameter is passed to browse_filtered."""
        mock_browse_filtered.return_value = {
            "page": 2,
            "total_results": 50,
            "total_pages": 3,
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
            + "?category=popular&page=2",
        )

        self.assertEqual(response.status_code, 200)
        mock_browse_filtered.assert_called_once_with(
            MediaTypes.MOVIE.value, {"sort_by": "popularity.desc"}, 2
        )

    @patch("app.providers.services.browse_filtered")
    def test_explore_type_layout_grid(self, mock_browse_filtered):
        """Test that layout parameter is passed to the context."""
        mock_browse_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.TV.value})
            + "?layout=grid",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["layout"], "grid")

    @patch("app.providers.services.browse")
    def test_explore_type_enriches_results(self, mock_browse):
        """Test that results are enriched with user tracking data."""
        item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Test Anime",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        mock_browse.return_value = {
            "page": 1,
            "total_results": 1,
            "total_pages": 1,
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
            reverse("explore_type", kwargs={"media_type": MediaTypes.ANIME.value}),
        )

        self.assertEqual(response.status_code, 200)
        results = response.context["data"]["results"]
        self.assertEqual(len(results), 1)
        self.assertIsNotNone(results[0]["media"])

    @patch("app.providers.services.browse_filtered")
    def test_explore_type_extra_params_includes_default_sort(self, mock_filtered):
        """Test that TMDB types include default sort_by in extra_params."""
        mock_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.TV.value}),
        )

        self.assertIn("sort_by=popularity.desc", response.context["extra_params"])

    @patch("app.providers.services.browse")
    def test_explore_type_extra_params_empty_for_non_tmdb(self, mock_browse):
        """Test that extra_params is empty for non-TMDB, non-seasonal categories."""
        mock_browse.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.ANIME.value}),
        )

        self.assertEqual(response.context["extra_params"], "")

    def test_explore_type_requires_get(self):
        """Test that explore_type rejects POST requests."""
        response = self.client.post(
            reverse("explore_type", kwargs={"media_type": MediaTypes.TV.value}),
        )
        self.assertEqual(response.status_code, 405)

    @patch("app.providers.services.browse_filtered")
    def test_explore_type_sidebar_only_highlights_explore(self, mock_browse_filtered):
        """Regression: explore_type should highlight only the Explore sidebar item."""
        mock_browse_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.TV.value}),
        )

        content = response.content.decode()
        medialist_url = reverse("medialist", kwargs={"media_type": MediaTypes.TV.value})
        explore_url = reverse("explore")

        # Find all highlighted sidebar links (anchor tags with bg-line)
        highlighted_links = re.findall(
            r'<a\s+href="([^"]+)"[^>]*bg-line[^>]*>', content
        )

        self.assertNotIn(medialist_url, highlighted_links)
        self.assertIn(explore_url, highlighted_links)
