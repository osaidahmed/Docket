"""Tests for the Browse and Discover tabs on the medialist page."""

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


def _browse_url(media_type, query=""):
    base = reverse("medialist_browse_tab", kwargs={"media_type": media_type})
    return f"{base}?tab=browse{f'&{query}' if query else ''}"


class MedialistBrowseTabTests(TestCase):
    """Browse tab partial — formerly the explore_type view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def _hx_get(self, url):
        return self.client.get(url, HTTP_HX_REQUEST="true")

    @patch("app.providers.services.browse")
    def test_default_category(self, mock_browse):
        """Default category is the first one defined for the media type."""
        mock_browse.return_value = {
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
                }
            ],
        }
        response = self._hx_get(_browse_url(MediaTypes.TV.value))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/partials/medialist_browse_tab.html")
        self.assertEqual(response.context["current_category"], "trending")
        mock_browse.assert_called_once_with(MediaTypes.TV.value, "trending", 1)

    @patch("app.providers.services.browse_filtered")
    def test_custom_category(self, mock_browse_filtered):
        mock_browse_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        response = self._hx_get(_browse_url(MediaTypes.TV.value, "category=popular"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_category"], "popular")

    @patch("app.providers.services.browse_filtered")
    def test_invalid_category_falls_back(self, mock_browse_filtered):
        mock_browse_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        response = self._hx_get(_browse_url(MediaTypes.TV.value, "category=invalid"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_category"], "trending")

    def test_non_explorable_redirects(self):
        """Non-explorable type (e.g. Season) redirects to medialist."""
        response = self._hx_get(_browse_url(MediaTypes.SEASON.value))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            response.url,
            reverse("medialist", kwargs={"media_type": MediaTypes.SEASON.value}),
        )

    @patch("app.providers.services.browse_filtered")
    def test_non_htmx_returns_partial(self, mock_browse_filtered):
        """Direct (non-HTMX) hits also return the partial — no chrome."""
        mock_browse_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        response = self.client.get(_browse_url(MediaTypes.TV.value))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/partials/medialist_browse_tab.html")

    @patch("app.providers.services.browse_filtered")
    def test_htmx_returns_partial(self, mock_browse_filtered):
        mock_browse_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        response = self._hx_get(_browse_url(MediaTypes.TV.value))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/partials/medialist_browse_tab.html")
        self.assertTemplateUsed(response, "app/explore_results.html")

    @patch("app.providers.services.browse_filtered")
    def test_htmx_includes_categories(self, mock_browse_filtered):
        mock_browse_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        response = self._hx_get(_browse_url(MediaTypes.TV.value, "category=popular"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_category"], "popular")
        self.assertGreater(len(response.context["categories"]), 0)

    @patch("app.providers.services.browse_filtered")
    def test_category_switch(self, mock_browse_filtered):
        mock_browse_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        first = self._hx_get(_browse_url(MediaTypes.TV.value))
        self.assertEqual(first.context["current_category"], "trending")
        second = self._hx_get(_browse_url(MediaTypes.TV.value, "category=top_rated"))
        self.assertEqual(second.context["current_category"], "top_rated")

    @patch("app.providers.services.browse")
    def test_pagination(self, mock_browse):
        mock_browse.return_value = {
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
                }
            ],
        }
        response = self._hx_get(
            _browse_url(MediaTypes.MOVIE.value, "category=popular&page=2")
        )
        self.assertEqual(response.status_code, 200)
        mock_browse.assert_called_once_with(MediaTypes.MOVIE.value, "popular", 2)

    @patch("app.providers.services.browse_filtered")
    def test_layout_grid(self, mock_browse_filtered):
        mock_browse_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        response = self._hx_get(_browse_url(MediaTypes.TV.value, "layout=grid"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["layout"], "grid")

    @patch("app.providers.services.browse")
    def test_enriches_results(self, mock_browse):
        item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Test Anime",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(item=item, user=self.user, status=Status.IN_PROGRESS.value)

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
                }
            ],
        }
        response = self._hx_get(_browse_url(MediaTypes.ANIME.value))
        self.assertEqual(response.status_code, 200)
        results = response.context["data"]["results"]
        self.assertEqual(len(results), 1)
        self.assertIsNotNone(results[0]["media"])

    @patch("app.providers.services.browse")
    def test_extra_params_empty_for_tmdb_no_filters(self, mock_browse):
        mock_browse.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        response = self._hx_get(_browse_url(MediaTypes.TV.value))
        self.assertEqual(response.context["extra_params"], "")

    @patch("app.providers.services.browse")
    def test_extra_params_empty_for_non_tmdb(self, mock_browse):
        mock_browse.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        response = self._hx_get(_browse_url(MediaTypes.ANIME.value))
        self.assertEqual(response.context["extra_params"], "")

    def test_requires_get(self):
        response = self.client.post(
            _browse_url(MediaTypes.TV.value),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 405)

    @patch("app.providers.services.browse")
    def test_tmdb_uses_browse_when_no_filters(self, mock_browse):
        mock_browse.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        self._hx_get(_browse_url(MediaTypes.MOVIE.value, "category=trending"))
        mock_browse.assert_called_once_with(MediaTypes.MOVIE.value, "trending", 1)

    @patch("app.providers.services.browse_filtered")
    def test_tmdb_uses_filtered_when_filters_active(self, mock_filtered):
        mock_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        self._hx_get(_browse_url(MediaTypes.MOVIE.value, "category=trending&genres=28"))
        mock_filtered.assert_called_once()

    @patch("app.providers.services.browse")
    def test_no_active_filters_without_explicit_filters(self, mock_browse):
        mock_browse.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        response = self._hx_get(_browse_url(MediaTypes.MOVIE.value))
        self.assertFalse(response.context["has_active_filters"])

    @patch("app.providers.services.browse")
    def test_order_defaults_to_desc(self, mock_browse):
        mock_browse.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        response = self._hx_get(_browse_url(MediaTypes.MOVIE.value))
        self.assertEqual(response.context["order"], "desc")

    @patch("app.providers.services.browse_filtered")
    def test_order_asc_passed_to_provider(self, mock_filtered):
        mock_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        self._hx_get(
            _browse_url(MediaTypes.MOVIE.value, "sort_by=popularity&order=asc")
        )
        call_args = mock_filtered.call_args
        self.assertEqual(call_args[0][1]["order"], "asc")

    @patch("app.providers.services.browse_filtered")
    def test_order_in_extra_params(self, mock_filtered):
        mock_filtered.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }
        response = self._hx_get(
            _browse_url(MediaTypes.MOVIE.value, "sort_by=popularity&order=asc")
        )
        self.assertIn("order=asc", response.context["extra_params"])


class MedialistFormIdCollisionTests(TestCase):
    """Regression: Collection and Browse filter forms must not share an id."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def _render_medialist_with_browse(self, media_type):
        with patch("app.providers.services.browse") as mock_browse:
            mock_browse.return_value = {
                "page": 1,
                "total_results": 0,
                "total_pages": 1,
                "results": [],
            }
            page = self.client.get(
                reverse("medialist", kwargs={"media_type": media_type}),
            ).content.decode()
            browse = self.client.get(
                _browse_url(media_type),
                HTTP_HX_REQUEST="true",
            ).content.decode()
        return page + browse

    def test_browse_form_has_unique_id(self):
        """Browse-tab filter form uses 'browse-filter-form', not 'filter-form'."""
        with patch("app.providers.services.browse") as mock_browse:
            mock_browse.return_value = {
                "page": 1,
                "total_results": 0,
                "total_pages": 1,
                "results": [],
            }
            response = self.client.get(
                _browse_url(MediaTypes.ANIME.value),
                HTTP_HX_REQUEST="true",
            )
        body = response.content.decode()
        self.assertIn('id="browse-filter-form"', body)
        self.assertNotIn('id="filter-form"', body)

    def test_combined_dom_has_no_filter_form_collision(self):
        """Combined Collection+Browse DOM has exactly one #filter-form."""
        combined = self._render_medialist_with_browse(MediaTypes.ANIME.value)
        filter_form_count = len(re.findall(r'id="filter-form"', combined))
        self.assertEqual(filter_form_count, 1)
        self.assertIn('id="browse-filter-form"', combined)

    def test_browse_panel_uses_dedicated_alpine_component(self):
        """Filter panel binds to the browseFilterPanel Alpine component."""
        with patch("app.providers.services.browse") as mock_browse:
            mock_browse.return_value = {
                "page": 1,
                "total_results": 0,
                "total_pages": 1,
                "results": [],
            }
            response = self.client.get(
                _browse_url(MediaTypes.ANIME.value),
                HTTP_HX_REQUEST="true",
            )
        body = response.content.decode()
        self.assertIn('x-data="browseFilterPanel"', body)


class MedialistStatusFilterRedirectTests(TestCase):
    """Status-filter redirect must not smuggle Browse-tab params."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)
        cls.item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Anime",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
            item=cls.item,
            user=cls.user,
            status=Status.PLANNING.value,
        )

    def setUp(self):
        self.client.login(**self.credentials)

    def test_planning_filter_does_not_carry_browse_tab_to_redirect(self):
        """Status=Planning HTMX redirect URL omits tab=browse and browse params."""
        response = self.client.get(
            reverse("medialist", kwargs={"media_type": MediaTypes.ANIME.value}),
            data={
                "sort": "score",
                "sort_dir": "desc",
                "status": "Planning",
                "search": "",
                "layout": "cards",
            },
            HTTP_HX_REQUEST="true",
        )
        redirect_target = response.headers.get("HX-Redirect")
        if redirect_target is not None:
            self.assertNotIn("tab=browse", redirect_target)
            self.assertNotIn("category=", redirect_target)
            self.assertNotIn("sort_by=", redirect_target)


class MedialistTabSidebarTests(TestCase):
    """The medialist page sidebar should highlight the media type, not News."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def test_browse_tab_highlights_media_type_not_news(self):
        """Visiting /medialist/<type>?tab=browse highlights the media type lane."""
        response = self.client.get(
            reverse("medialist", kwargs={"media_type": MediaTypes.TV.value})
            + "?tab=browse",
        )
        content = response.content.decode()
        news_url = reverse("news")
        # News sidebar entry should NOT be highlighted on a medialist page
        highlighted = re.findall(r'<a\s+href="([^"]+)"[^>]*bg-line[^>]*>', content)
        self.assertNotIn(news_url, highlighted)
