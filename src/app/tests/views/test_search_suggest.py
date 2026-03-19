from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import (
    TV,
    Anime,
    Game,
    Item,
    Manga,
    MediaTypes,
    Movie,
    Sources,
    Status,
)


class SearchSuggestLocalViewTests(TestCase):
    """Test the search_suggest_local view."""

    def setUp(self):
        """Create users and sample media for suggestion tests."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

        credentials2 = {"username": "other", "password": "12345"}
        self.user2 = get_user_model().objects.create_user(**credentials2)

        # Anime: Naruto (owned by user)
        item_anime = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Naruto",
            english_title="Naruto",
            image="http://example.com/naruto.jpg",
        )
        Anime.objects.create(
            item=item_anime,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        # Manga: Naruto (owned by user)
        item_manga = Item.objects.create(
            media_id="50",
            source=Sources.MAL.value,
            media_type=MediaTypes.MANGA.value,
            title="Naruto",
            image="http://example.com/naruto_manga.jpg",
        )
        Manga.objects.create(
            item=item_manga,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        # Game: Naruto Ultimate Ninja Storm (owned by user)
        item_game = Item.objects.create(
            media_id="10",
            source=Sources.IGDB.value,
            media_type=MediaTypes.GAME.value,
            title="Naruto Ultimate Ninja Storm",
            image="http://example.com/naruto_game.jpg",
        )
        Game.objects.create(
            item=item_game,
            user=self.user,
            status=Status.COMPLETED.value,
        )

        # Movie: The Godfather (owned by user, should NOT match "Naruto")
        item_movie = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="The Godfather",
            image="http://example.com/godfather.jpg",
        )
        Movie.objects.create(
            item=item_movie,
            user=self.user,
            status=Status.COMPLETED.value,
        )

        # TV: Breaking Bad (owned by user2, NOT by user)
        item_tv = Item.objects.create(
            media_id="100",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Breaking Bad",
            image="http://example.com/bb.jpg",
        )
        TV.objects.create(
            item=item_tv,
            user=self.user2,
            status=Status.PLANNING.value,
        )

    def test_short_query_returns_empty(self):
        """Queries with fewer than 2 characters return an empty partial."""
        response = self.client.get(
            reverse("search_suggest_local") + "?q=N",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/search_suggest_local.html")
        self.assertNotIn("results", response.context)

    def test_empty_query_returns_empty(self):
        """Empty query string returns an empty partial."""
        response = self.client.get(
            reverse("search_suggest_local") + "?q=",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("results", response.context)

    def test_valid_query_returns_matching_items(self):
        """Query 'Naruto' matches the Anime, Manga, and Game items."""
        response = self.client.get(
            reverse("search_suggest_local") + "?q=Naruto",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/search_suggest_local.html")
        results = response.context["results"]
        self.assertEqual(len(results), 3)

    def test_results_limited_to_five(self):
        """At most 5 results are returned even when more match."""
        for i in range(7):
            item = Item.objects.create(
                media_id=str(1000 + i),
                source=Sources.TMDB.value,
                media_type=MediaTypes.MOVIE.value,
                title=f"TestMovie {i}",
                image="http://example.com/img.jpg",
            )
            Movie.objects.create(
                item=item,
                user=self.user,
                status=Status.PLANNING.value,
            )

        response = self.client.get(
            reverse("search_suggest_local") + "?q=TestMovie",
        )

        self.assertEqual(len(response.context["results"]), 5)

    def test_prefix_match_ranked_before_contains(self):
        """Prefix matches appear before substring-only matches."""
        item_contains = Item.objects.create(
            media_id="999",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Boruto: Naruto Next Generations",
            image="http://example.com/boruto.jpg",
        )
        Anime.objects.create(
            item=item_contains,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.get(
            reverse("search_suggest_local") + "?q=Naruto",
        )

        results = response.context["results"]
        self.assertTrue(results[0]["title"].startswith("Naruto"))
        # All prefix matches come before contains-only matches
        prefix_indices = [
            i for i, r in enumerate(results) if r["title"].lower().startswith("naruto")
        ]
        contains_indices = [
            i
            for i, r in enumerate(results)
            if not r["title"].lower().startswith("naruto")
        ]
        if prefix_indices and contains_indices:
            self.assertLess(max(prefix_indices), min(contains_indices))

    def test_other_user_items_not_returned(self):
        """Items belonging to other users are not included."""
        response = self.client.get(
            reverse("search_suggest_local") + "?q=Breaking",
        )

        self.assertEqual(response.status_code, 200)
        results = response.context.get("results", [])
        self.assertEqual(len(results), 0)

    def test_english_title_matches(self):
        """Items are found by english_title as well as title."""
        item = Item.objects.create(
            media_id="16498",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Shingeki no Kyojin",
            english_title="Attack on Titan",
            image="http://example.com/aot.jpg",
        )
        Anime.objects.create(
            item=item,
            user=self.user,
            status=Status.COMPLETED.value,
        )

        response = self.client.get(
            reverse("search_suggest_local") + "?q=Attack",
        )

        results = response.context["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Shingeki no Kyojin")

    def test_disabled_media_type_excluded(self):
        """Disabled media types are excluded from local suggestions."""
        pref = self.user.get_or_create_media_pref("anime")
        pref.enabled = False
        pref.save(update_fields=["enabled"])
        if hasattr(self.user, "_pref_cache"):
            del self.user._pref_cache

        response = self.client.get(
            reverse("search_suggest_local") + "?q=Naruto",
        )

        results = response.context["results"]
        media_types = [r["media_type"] for r in results]
        self.assertNotIn(MediaTypes.ANIME.value, media_types)
        # Manga and Game should still appear
        self.assertIn(MediaTypes.MANGA.value, media_types)
        self.assertIn(MediaTypes.GAME.value, media_types)

    def test_requires_get(self):
        """POST requests are rejected with 405."""
        response = self.client.post(reverse("search_suggest_local"))
        self.assertEqual(response.status_code, 405)

    def test_results_include_media_type_and_status(self):
        """Each result dict contains media_type, status, and image."""
        response = self.client.get(
            reverse("search_suggest_local") + "?q=Naruto",
        )

        for result in response.context["results"]:
            self.assertIn("media_type", result)
            self.assertIn("status", result)
            self.assertIn("image", result)
            self.assertIn("title", result)
            self.assertIn("media_id", result)
            self.assertIn("source", result)


class SearchSuggestApiViewTests(TestCase):
    """Test the search_suggest_api view."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    @patch("app.providers.services.search_suggest_api")
    def test_short_query_returns_empty(self, mock_suggest):
        """Queries with fewer than 3 characters return an empty partial."""
        response = self.client.get(
            reverse("search_suggest_api") + "?q=Na",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/search_suggest_api.html")
        self.assertNotIn("results", response.context)
        mock_suggest.assert_not_called()

    @patch("app.providers.services.search_suggest_api")
    def test_valid_query_returns_api_results(self, mock_suggest):
        """Valid query returns combined API results."""
        mock_suggest.return_value = [
            {
                "media_id": "20",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.TV.value,
                "title": "Narcos",
                "image": "http://example.com/narcos.jpg",
            },
            {
                "media_id": "21",
                "source": Sources.MAL.value,
                "media_type": MediaTypes.ANIME.value,
                "title": "Naruto Shippuden",
                "image": "http://example.com/shippuden.jpg",
            },
        ]

        response = self.client.get(
            reverse("search_suggest_api") + "?q=Naruto",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/search_suggest_api.html")
        results = response.context["results"]
        self.assertEqual(len(results), 2)
        mock_suggest.assert_called_once()

    @patch("app.providers.services.search_suggest_api")
    def test_local_keys_parsed_from_query_param(self, mock_suggest):
        """local_keys query param is parsed and forwarded to the service."""
        mock_suggest.return_value = []

        self.client.get(
            reverse("search_suggest_api") + "?q=Naruto&local_keys=20:mal,100:tmdb",
        )

        call_kwargs = mock_suggest.call_args
        local_keys = call_kwargs[1].get("local_keys") or call_kwargs[0][2]
        self.assertIn(("20", "mal"), local_keys)
        self.assertIn(("100", "tmdb"), local_keys)

    @patch("app.providers.services.search_suggest_api")
    def test_empty_local_keys_param(self, mock_suggest):
        """Omitting local_keys param passes empty set to the service."""
        mock_suggest.return_value = []

        self.client.get(
            reverse("search_suggest_api") + "?q=Naruto",
        )

        local_keys = mock_suggest.call_args[1].get("local_keys", set())
        self.assertEqual(local_keys, set())

    @patch("app.providers.services.search_suggest_api")
    def test_malformed_local_keys_ignored(self, mock_suggest):
        """Malformed local_keys entries are silently skipped."""
        mock_suggest.return_value = []

        self.client.get(
            reverse("search_suggest_api") + "?q=Naruto&local_keys=invalid,20:mal,,:",
        )

        call_kwargs = mock_suggest.call_args
        local_keys = call_kwargs[1].get("local_keys") or call_kwargs[0][2]
        self.assertIn(("20", "mal"), local_keys)
        # "invalid" has no colon, should be skipped
        self.assertNotIn(("invalid",), local_keys)

    @patch("app.providers.services.search_suggest_api")
    def test_results_capped_at_five(self, mock_suggest):
        """At most 5 results are shown even if the service returns more."""
        mock_suggest.return_value = [
            {
                "media_id": str(i),
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.TV.value,
                "title": f"Result {i}",
                "image": "http://example.com/img.jpg",
            }
            for i in range(10)
        ]

        response = self.client.get(
            reverse("search_suggest_api") + "?q=Result",
        )

        self.assertLessEqual(len(response.context["results"]), 5)

    @patch("app.providers.services.search_suggest_api")
    def test_query_passed_to_template(self, mock_suggest):
        """The template receives the query string in context."""
        mock_suggest.return_value = []

        response = self.client.get(
            reverse("search_suggest_api") + "?q=Naruto",
        )

        self.assertEqual(response.context["query"], "Naruto")

    @patch("app.providers.services.search_suggest_api")
    def test_disabled_types_not_searched(self, mock_suggest):
        """Disabled media types are excluded from enabled_types."""
        pref = self.user.get_or_create_media_pref("anime")
        pref.enabled = False
        pref.save(update_fields=["enabled"])
        if hasattr(self.user, "_pref_cache"):
            del self.user._pref_cache
        mock_suggest.return_value = []

        self.client.get(
            reverse("search_suggest_api") + "?q=Naruto",
        )

        call_args = mock_suggest.call_args
        enabled_types = call_args[0][1]
        self.assertNotIn(MediaTypes.ANIME.value, enabled_types)

    def test_requires_get(self):
        """POST requests are rejected with 405."""
        response = self.client.post(reverse("search_suggest_api"))
        self.assertEqual(response.status_code, 405)
