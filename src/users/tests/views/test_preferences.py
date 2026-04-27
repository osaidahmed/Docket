import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import Item, Manga, MediaTypes, Sources, Status


class PreferencesLinkPrefsTests(TestCase):
    """Tests for the link_preferences integration on the preferences page."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "linktester", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def test_get_renders_external_links_section(self):
        response = self.client.get(reverse("preferences"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "External Links")
        self.assertContains(response, "link_preferences")

    def test_get_includes_provider_options_per_media_type(self):
        response = self.client.get(reverse("preferences"))
        self.assertIn("link_pref_rows", response.context)
        rows_by_type = {r["media_type"]: r for r in response.context["link_pref_rows"]}
        self.assertIn("manga", rows_by_type)
        manga_providers = {p["site_id"] for p in rows_by_type["manga"]["providers"]}
        self.assertIn("allmanga", manga_providers)

    def test_post_saves_link_preferences(self):
        prefs = {
            "manga": {"provider": "allmanga", "template": ""},
            "movie": {"provider": "", "template": "https://x.test/?q={title}"},
        }
        response = self.client.post(
            reverse("preferences"),
            {"link_preferences": json.dumps(prefs)},
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.link_preferences, prefs)

    def test_post_invalid_json_is_ignored(self):
        self.user.link_preferences = {"manga": {"provider": "allmanga"}}
        self.user.save(update_fields=["link_preferences"])

        response = self.client.post(
            reverse("preferences"),
            {"link_preferences": "{not-json"},
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(
            self.user.link_preferences, {"manga": {"provider": "allmanga"}}
        )

    @patch("app.link_providers.tasks.generate_link.delay")
    def test_post_queues_backfill_for_existing_entries(self, mock_delay):
        item = Item.objects.create(
            media_id="m-backfill",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Backfill Manga",
            image="https://x.test/i.jpg",
        )
        instance = Manga.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        prefs = {"manga": {"provider": "allmanga", "template": ""}}
        response = self.client.post(
            reverse("preferences"),
            {"link_preferences": json.dumps(prefs)},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(mock_delay.call_count, 1)
        self.assertEqual(mock_delay.call_args.args, (instance.pk, "manga"))

    @patch("app.link_providers.tasks.generate_link.delay")
    def test_post_skips_backfill_for_entries_with_existing_link(self, mock_delay):
        item = Item.objects.create(
            media_id="m-haslink",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Already Linked",
            image="https://x.test/i.jpg",
        )
        Manga.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
            link="https://manual.test/",
        )

        prefs = {"manga": {"provider": "allmanga"}}
        self.client.post(
            reverse("preferences"),
            {"link_preferences": json.dumps(prefs)},
        )

        self.assertEqual(mock_delay.call_count, 0)

    def test_post_empty_link_preferences_does_not_clobber(self):
        self.user.link_preferences = {"manga": {"provider": "allmanga"}}
        self.user.save(update_fields=["link_preferences"])

        response = self.client.post(
            reverse("preferences"),
            {"link_preferences": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(
            self.user.link_preferences, {"manga": {"provider": "allmanga"}}
        )
