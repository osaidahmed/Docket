"""Legacy /explore URL redirect tests — actual behavior lives in test_medialist_tabs."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import MediaTypes


class ExploreRedirectTests(TestCase):
    """Legacy /explore/<type> and /explore/<type>/section/<key> URLs redirect."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def test_explore_type_redirects_to_browse_tab(self):
        """Hitting /explore/<type> redirects to /medialist/<type>?tab=browse."""
        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.TV.value}),
        )
        self.assertEqual(response.status_code, 302)
        target = reverse("medialist", kwargs={"media_type": MediaTypes.TV.value})
        self.assertIn(target, response.url)
        self.assertIn("tab=browse", response.url)

    def test_explore_type_with_view_discover_redirects(self):
        """?view=discover on legacy URL routes to ?tab=discover."""
        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.TV.value})
            + "?view=discover",
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("tab=discover", response.url)
        self.assertNotIn("view=discover", response.url)

    def test_explore_type_preserves_other_params(self):
        """Category/page params should survive the redirect."""
        response = self.client.get(
            reverse("explore_type", kwargs={"media_type": MediaTypes.TV.value})
            + "?category=popular&page=2",
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("category=popular", response.url)
        self.assertIn("page=2", response.url)

    def test_explore_section_redirects_to_discover_tab(self):
        """Legacy /explore/<type>/section/<key> redirects to ?tab=discover."""
        response = self.client.get(
            reverse(
                "explore_section",
                kwargs={"media_type": MediaTypes.TV.value, "section_key": "trending"},
            ),
        )
        self.assertEqual(response.status_code, 302)
        target = reverse("medialist", kwargs={"media_type": MediaTypes.TV.value})
        self.assertIn(target, response.url)
        self.assertIn("tab=discover", response.url)
