from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import TestCase
from django.urls import reverse

from app.models import MediaTypes


class SidebarViewTests(TestCase):
    """Tests for the sidebar view."""

    @classmethod
    def setUpTestData(cls):
        """Create user for the tests."""
        cls.credentials = {"username": "testuser", "password": "testpass123"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def test_preferences_get(self):
        """Test GET request to preferences view."""
        response = self.client.get(reverse("preferences"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "users/preferences.html")

        self.assertIn("media_types", response.context)
        self.assertIn(MediaTypes.TV.value, response.context["media_types"])
        self.assertIn(MediaTypes.MOVIE.value, response.context["media_types"])
        self.assertNotIn(MediaTypes.EPISODE.value, response.context["media_types"])

    def test_sidebar_post_update_preferences(self):
        """Test POST request to update preferences."""
        for mt in [MediaTypes.TV.value, MediaTypes.MOVIE.value, MediaTypes.ANIME.value]:
            self.user.get_or_create_media_pref(mt)

        response = self.client.post(
            reverse("preferences"),
            {
                "media_types_checkboxes": [MediaTypes.TV.value, MediaTypes.ANIME.value],
            },
        )
        self.assertRedirects(response, reverse("preferences"))

        tv_pref = self.user.media_preferences.get(media_type=MediaTypes.TV.value)
        movie_pref = self.user.media_preferences.get(media_type=MediaTypes.MOVIE.value)
        anime_pref = self.user.media_preferences.get(media_type=MediaTypes.ANIME.value)
        self.assertTrue(tv_pref.enabled)
        self.assertFalse(movie_pref.enabled)
        self.assertTrue(anime_pref.enabled)

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("Settings updated", str(messages[0]))

    def test_sidebar_post_demo_user(self):
        """Test POST request from a demo user to preferences."""
        self.user.is_demo = True
        self.user.save()
        pref_tv = self.user.get_or_create_media_pref(MediaTypes.TV.value)
        pref_movie = self.user.get_or_create_media_pref(MediaTypes.MOVIE.value)
        pref_movie.enabled = False
        pref_movie.save(update_fields=["enabled"])

        response = self.client.post(
            reverse("preferences"),
            {
                "media_types_checkboxes": [MediaTypes.TV.value, MediaTypes.MOVIE.value],
            },
        )
        self.assertRedirects(response, reverse("preferences"))

        pref_tv.refresh_from_db()
        pref_movie.refresh_from_db()
        self.assertTrue(pref_tv.enabled)
        self.assertFalse(pref_movie.enabled)

        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        self.assertIn("view-only for demo accounts", str(messages[0]))


class PreferencesToggleRoundTripTests(TestCase):
    """Test that preferences save and display correctly through full round-trips."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "preftest", "password": "testpass123"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)
        if hasattr(self.user, "_pref_cache"):
            del self.user._pref_cache

    def _get_enabled_from_response(self, response):
        """Extract enabled_types from the preferences page context."""
        return response.context["enabled_types"]

    def _post_preferences(self, checked_types):
        """POST preferences form with given checked types."""
        return self.client.post(
            reverse("preferences"),
            {"media_types_checkboxes": checked_types},
        )

    def test_enable_single_new_type(self):
        """Enabling one additional type keeps existing types enabled."""
        initial = [
            MediaTypes.TV.value,
            MediaTypes.ANIME.value,
            MediaTypes.MANGA.value,
            MediaTypes.MOVIE.value,
            MediaTypes.GAME.value,
        ]
        self._post_preferences(initial)

        added = [*initial, MediaTypes.COMIC.value]
        self._post_preferences(added)

        response = self.client.get(reverse("preferences"))
        enabled = self._get_enabled_from_response(response)
        for mt in added:
            self.assertIn(mt, enabled, f"{mt} should be enabled")

    def test_disable_single_type(self):
        """Disabling one type keeps all others enabled."""
        all_types = [
            MediaTypes.TV.value,
            MediaTypes.MOVIE.value,
            MediaTypes.ANIME.value,
            MediaTypes.MANGA.value,
            MediaTypes.GAME.value,
            MediaTypes.BOOK.value,
            MediaTypes.COMIC.value,
            MediaTypes.BOARDGAME.value,
        ]
        self._post_preferences(all_types)

        without_game = [mt for mt in all_types if mt != MediaTypes.GAME.value]
        self._post_preferences(without_game)

        response = self.client.get(reverse("preferences"))
        enabled = self._get_enabled_from_response(response)
        for mt in without_game:
            self.assertIn(mt, enabled, f"{mt} should still be enabled")
        self.assertNotIn(MediaTypes.GAME.value, enabled)

    def test_enable_all_then_disable_all_except_one(self):
        """Can disable all types except one."""
        all_types = [
            MediaTypes.TV.value,
            MediaTypes.MOVIE.value,
            MediaTypes.ANIME.value,
            MediaTypes.MANGA.value,
            MediaTypes.GAME.value,
            MediaTypes.BOOK.value,
            MediaTypes.COMIC.value,
            MediaTypes.BOARDGAME.value,
        ]
        self._post_preferences(all_types)
        self._post_preferences([MediaTypes.TV.value])

        response = self.client.get(reverse("preferences"))
        enabled = self._get_enabled_from_response(response)
        self.assertIn(MediaTypes.TV.value, enabled)
        self.assertNotIn(MediaTypes.MOVIE.value, enabled)
        self.assertNotIn(MediaTypes.ANIME.value, enabled)

    def test_preferences_page_shows_correct_checked_state(self):
        """GET preferences page shows checkboxes matching saved state."""
        checked = [MediaTypes.TV.value, MediaTypes.COMIC.value]
        self._post_preferences(checked)

        response = self.client.get(reverse("preferences"))
        enabled = self._get_enabled_from_response(response)
        self.assertIn(MediaTypes.TV.value, enabled)
        self.assertIn(MediaTypes.COMIC.value, enabled)
        self.assertNotIn(MediaTypes.GAME.value, enabled)

    def test_multiple_save_cycles_preserve_state(self):
        """Saving the same preferences multiple times doesn't corrupt state."""
        checked = [
            MediaTypes.TV.value,
            MediaTypes.ANIME.value,
            MediaTypes.MANGA.value,
        ]
        for _ in range(3):
            self._post_preferences(checked)

        response = self.client.get(reverse("preferences"))
        enabled = self._get_enabled_from_response(response)
        self.assertEqual(
            {MediaTypes.TV.value, MediaTypes.ANIME.value, MediaTypes.MANGA.value},
            {mt for mt in enabled if mt != MediaTypes.SEASON.value},
        )

    def test_new_user_has_all_types_enabled_by_default(self):
        """A brand new user sees all types enabled on the preferences page."""
        new_creds = {"username": "brandnew", "password": "pass12345"}
        get_user_model().objects.create_user(**new_creds)
        self.client.login(**new_creds)

        response = self.client.get(reverse("preferences"))
        enabled = self._get_enabled_from_response(response)
        for mt in [
            MediaTypes.TV.value,
            MediaTypes.MOVIE.value,
            MediaTypes.ANIME.value,
            MediaTypes.MANGA.value,
            MediaTypes.GAME.value,
            MediaTypes.BOOK.value,
            MediaTypes.COMIC.value,
            MediaTypes.BOARDGAME.value,
        ]:
            self.assertIn(mt, enabled, f"{mt} should be enabled by default")
