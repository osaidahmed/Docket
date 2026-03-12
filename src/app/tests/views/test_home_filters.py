from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from app.helpers import enrich_items_with_user_data
from app.models import Anime, Item, Manga, MediaTypes, Movie, Sources, Status
from app.providers.mal import get_english_title


class MultiSelectFilterTests(TestCase):
    """Tests for multi-select media type filtering on home page."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.anime_item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Test Anime",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
            item=cls.anime_item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
        )

        cls.movie_item = Item.objects.create(
            media_id="2",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=cls.movie_item,
            user=cls.user,
            status=Status.PLANNING.value,
        )

        cls.manga_item = Item.objects.create(
            media_id="3",
            source=Sources.MAL.value,
            media_type=MediaTypes.MANGA.value,
            title="Test Manga",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=cls.manga_item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
        )

    def setUp(self):
        self.client.login(**self.credentials)
        self.user.home_default_types = []
        self.user.save(update_fields=["home_default_types"])

    def test_multi_select_filters_to_selected_types(self):
        """Comma-separated type param restricts to those types only."""
        response = self.client.get(reverse("home") + "?type=anime,manga")

        media_types_in_groups = {
            group["media_type"] for group in response.context["groups"]
        }
        self.assertIn(MediaTypes.ANIME.value, media_types_in_groups)
        self.assertIn(MediaTypes.MANGA.value, media_types_in_groups)
        self.assertNotIn(MediaTypes.MOVIE.value, media_types_in_groups)

    def test_multi_select_persists_across_requests(self):
        """Type selection is saved and restored when no param is given."""
        self.client.get(reverse("home") + "?type=anime,manga")

        self.user.refresh_from_db()
        self.assertEqual(self.user.home_default_types, ["anime", "manga"])

        response = self.client.get(reverse("home"))
        self.assertEqual(response.context["selected_types"], {"anime", "manga"})

    def test_all_resets_saved_filter(self):
        """type=all clears the saved filter to empty list."""
        self.user.home_default_types = ["anime"]
        self.user.save(update_fields=["home_default_types"])

        response = self.client.get(reverse("home") + "?type=all")

        self.user.refresh_from_db()
        self.assertEqual(self.user.home_default_types, [])
        self.assertEqual(response.context["selected_types"], set())

    def test_invalid_types_are_dropped(self):
        """Invalid media types in param are silently ignored."""
        response = self.client.get(reverse("home") + "?type=anime,invalid,manga")

        self.assertEqual(response.context["selected_types"], {"anime", "manga"})

    def test_show_type_headers_multi_select(self):
        """Group headers shown when multiple types are selected."""
        response = self.client.get(reverse("home") + "?type=anime,movie")
        self.assertTrue(response.context["show_type_headers"])

    def test_hide_type_headers_single_select(self):
        """Group headers hidden when exactly one type is selected."""
        response = self.client.get(reverse("home") + "?type=anime")
        self.assertFalse(response.context["show_type_headers"])

    def test_show_type_headers_all(self):
        """Group headers shown when no types are selected (all)."""
        response = self.client.get(reverse("home") + "?type=all")
        self.assertTrue(response.context["show_type_headers"])

    def test_rewatch_extracted_in_multi_select(self):
        """Rewatches get own group when multiple types are selected."""
        rewatch_item = Item.objects.create(
            media_id="5010",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Multi Rewatch",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
            item=rewatch_item,
            user=self.user,
            status=Status.PLANNING.value,
            is_rewatch=True,
        )

        response = self.client.get(reverse("home") + "?type=anime,movie")
        groups = response.context["groups"]
        media_types = {g["media_type"] for g in groups}
        self.assertIn("rewatch", media_types)

    def test_sort_dropdown_preserves_multi_select(self):
        """Sort links include the comma-separated type param."""
        response = self.client.get(reverse("home") + "?type=anime,manga")
        self.assertContains(response, "&type=anime,manga")

    def test_default_is_all_types(self):
        """Fresh user with no saved filter sees all types."""
        response = self.client.get(reverse("home"))
        self.assertEqual(response.context["selected_types"], set())

    def test_toggle_url_adds_type(self):
        """Chip toggle URL adds the type when not selected."""
        response = self.client.get(reverse("home") + "?type=anime")
        chips = response.context["type_filter_choices"]
        manga_chip = next(c for c in chips if c["value"] == "manga")
        self.assertIn("anime", manga_chip["toggle_url"])
        self.assertIn("manga", manga_chip["toggle_url"])

    def test_toggle_url_removes_type(self):
        """Chip toggle URL removes the type when already selected."""
        response = self.client.get(reverse("home") + "?type=anime,manga")
        chips = response.context["type_filter_choices"]
        anime_chip = next(c for c in chips if c["value"] == "anime")
        self.assertIn("manga", anime_chip["toggle_url"])
        self.assertNotIn("anime", anime_chip["toggle_url"])

    def test_toggle_url_reverts_to_all(self):
        """Removing the last selected type produces type=all."""
        response = self.client.get(reverse("home") + "?type=anime")
        chips = response.context["type_filter_choices"]
        anime_chip = next(c for c in chips if c["value"] == "anime")
        self.assertIn("type=all", anime_chip["toggle_url"])

    def test_all_chip_rendered_on_backlog(self):
        """'All' chip is rendered with correct link on backlog page."""
        response = self.client.get(reverse("home") + "?type=all")
        self.assertContains(response, "type=all")

    def test_chips_render_as_links_with_toggle_urls(self):
        """Filter chips render as <a> tags with server-computed toggle URLs."""
        response = self.client.get(reverse("home") + "?type=anime")
        chips = response.context["type_filter_choices"]
        for chip in chips:
            html_url = chip["toggle_url"].replace("&", "&amp;")
            self.assertContains(response, html_url)

    def test_toggle_url_follows_through(self):
        """Clicking a toggle URL actually produces the right filter."""
        response = self.client.get(reverse("home") + "?type=anime")
        chips = response.context["type_filter_choices"]
        manga_chip = next(c for c in chips if c["value"] == "manga")

        response2 = self.client.get(manga_chip["toggle_url"])
        self.assertEqual(
            response2.context["selected_types"],
            {"anime", "manga"},
        )

    def test_archive_toggle_urls_include_view_param(self):
        """Toggle URLs on archive page include view=archive."""
        response = self.client.get(reverse("home") + "?view=archive")
        chips = response.context["type_filter_choices"]
        for chip in chips:
            self.assertIn("view=archive", chip["toggle_url"])


class EnrichmentTests(TestCase):
    """Test the enrich_items_with_user_data helper."""

    @classmethod
    def setUpTestData(cls):
        """Create a user and test data."""
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )

    def setUp(self):
        self.factory = RequestFactory()

    def _make_request(self):
        request = self.factory.get("/")
        request.user = self.user
        return request

    def _search_items(self):
        return [
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        ]

    @patch("app.providers.services.get_media_metadata")
    def test_enrichment_prefers_completed_over_active(self, mock_metadata):
        """Test that completed/dropped instances are preferred over active."""
        mock_metadata.return_value = {"max_progress": None}
        completed = Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
        )
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        results = enrich_items_with_user_data(
            self._make_request(), self._search_items(), "search"
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["media"].id, completed.id)
        self.assertEqual(results[0]["media"].status, Status.COMPLETED.value)
        self.assertTrue(results[0]["has_active"])

    @patch("app.providers.services.get_media_metadata")
    def test_enrichment_has_active_true(self, mock_metadata):
        """Test that has_active is True when an active instance exists."""
        mock_metadata.return_value = {"max_progress": None}
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
        )
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        results = enrich_items_with_user_data(
            self._make_request(), self._search_items(), "search"
        )

        self.assertTrue(results[0]["has_active"])

    @patch("app.providers.services.get_media_metadata")
    def test_enrichment_has_active_false(self, mock_metadata):
        """Test that has_active is False with only completed instances."""
        mock_metadata.return_value = {"max_progress": None}
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
        )

        results = enrich_items_with_user_data(
            self._make_request(), self._search_items(), "search"
        )

        self.assertFalse(results[0]["has_active"])

    @patch("app.providers.services.get_media_metadata")
    def test_enrichment_prefers_completed_over_dropped(self, mock_metadata):
        """After canceling a rewatch, enrichment shows Completed not Dropped."""
        mock_metadata.return_value = {"max_progress": None}
        completed = Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
        )
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.DROPPED.value,
        )

        results = enrich_items_with_user_data(
            self._make_request(), self._search_items(), "search"
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["media"].id, completed.id)
        self.assertEqual(results[0]["media"].status, Status.COMPLETED.value)
        self.assertFalse(results[0]["has_active"])


class EnglishTitleTests(TestCase):
    """Test English title display and search."""

    @classmethod
    def setUpTestData(cls):
        """Create anime item with English title for testing."""
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.item = Item.objects.create(
            media_id="16498",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Shingeki no Kyojin",
            english_title="Attack on Titan",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
            item=cls.item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
        )

    def setUp(self):
        self.client.login(**self.credentials)

    def test_english_title_displayed_on_backlog_card(self):
        """Test that English title subtitle appears on home backlog cards."""
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Attack on Titan")

    def test_english_title_not_shown_when_empty(self):
        """Test that no subtitle is rendered when english_title is empty."""
        self.item.english_title = ""
        self.item.save()
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "Attack on Titan")

    @patch("app.providers.services.get_media_metadata")
    def test_english_title_on_media_details(self, mock_metadata):
        """Test that English title subtitle appears on media details page."""
        mock_metadata.return_value = {
            "media_id": "16498",
            "source": Sources.MAL.value,
            "source_url": "https://myanimelist.net/anime/16498",
            "media_type": MediaTypes.ANIME.value,
            "title": "Shingeki no Kyojin",
            "english_title": "Attack on Titan",
            "image": "http://example.com/image.jpg",
            "synopsis": "Test synopsis",
            "genres": [],
            "score": None,
            "score_count": 0,
            "max_progress": 25,
            "details": {},
            "related": {},
        }
        response = self.client.get(
            reverse(
                "media_details",
                kwargs={
                    "source": Sources.MAL.value,
                    "media_type": MediaTypes.ANIME.value,
                    "media_id": "16498",
                    "title": "shingeki-no-kyojin",
                },
            )
        )
        self.assertContains(response, "Attack on Titan")

    def test_search_matches_english_title(self):
        """Test that in-library search finds items by English title."""
        response = self.client.get(
            reverse("medialist", kwargs={"media_type": MediaTypes.ANIME.value})
            + "?search=Attack"
        )
        self.assertContains(response, "Shingeki no Kyojin")

    def test_search_matches_original_title(self):
        """Test that in-library search still finds items by original title."""
        response = self.client.get(
            reverse("medialist", kwargs={"media_type": MediaTypes.ANIME.value})
            + "?search=Shingeki"
        )
        self.assertContains(response, "Shingeki no Kyojin")

    def test_search_no_match(self):
        """Test that search returns no results for unrelated queries."""
        response = self.client.get(
            reverse("medialist", kwargs={"media_type": MediaTypes.ANIME.value})
            + "?search=Naruto"
        )
        self.assertNotContains(response, "Shingeki no Kyojin")


class GetEnglishTitleTests(TestCase):
    """Test the get_english_title helper from MAL provider."""

    def test_returns_english_title(self):
        """Test extraction of English title from alternative_titles."""
        response = {
            "title": "Shingeki no Kyojin",
            "alternative_titles": {
                "en": "Attack on Titan",
                "ja": "\u9032\u6483\u306e\u5de8\u4eba",
            },
        }
        self.assertEqual(get_english_title(response), "Attack on Titan")

    def test_returns_empty_when_same_as_title(self):
        """Test that empty string is returned when English title matches main title."""
        response = {
            "title": "Attack on Titan",
            "alternative_titles": {"en": "Attack on Titan"},
        }
        self.assertEqual(get_english_title(response), "")

    def test_returns_empty_when_no_alternative_titles(self):
        """Test graceful handling when alternative_titles field is missing."""
        response = {"title": "Some Anime"}
        self.assertEqual(get_english_title(response), "")

    def test_returns_empty_when_en_is_empty_string(self):
        """Test that empty English title string is treated as no title."""
        response = {
            "title": "Some Anime",
            "alternative_titles": {
                "en": "",
                "ja": "\u4f55\u304b\u306e\u30a2\u30cb\u30e1",
            },
        }
        self.assertEqual(get_english_title(response), "")

    def test_returns_empty_when_alternative_titles_empty(self):
        """Test handling of empty alternative_titles dict."""
        response = {
            "title": "Some Anime",
            "alternative_titles": {},
        }
        self.assertEqual(get_english_title(response), "")
