"""Tests for the /news view (cross-type news aggregator)."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from app.models import MediaTypes
from app.news_tasks import selection_cache_key
from app.providers.news_per_item import cache_key as item_cache_key
from app.providers.news_rss import cache_key as rss_cache_key


def _industry_article(title="Headline", media_type="tv"):
    return {
        "title": title,
        "url": "https://example.com/article",
        "source": "Example",
        "summary": "summary",
        "image": None,
        "published_at": None,
        "media_type": media_type,
        "media_id": None,
    }


def _per_item_article(title="Anime News", media_type="anime", media_id="1"):
    return {
        "title": title,
        "url": "https://example.com/anime-news",
        "source": "MyAnimeList",
        "summary": "",
        "image": None,
        "published_at": None,
        "media_type": media_type,
        "media_id": media_id,
    }


class NewsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        cache.clear()
        self.client.login(**self.credentials)

    def test_empty_state_when_no_cache(self):
        response = self.client.get(reverse("news"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/news.html")
        self.assertTrue(response.context["all_empty"])

    def test_industry_lane_renders_when_cache_populated(self):
        cache.set(rss_cache_key("deadline-tv"), [_industry_article(media_type="tv")])
        response = self.client.get(reverse("news"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["all_empty"])
        industry = response.context["industry_lanes"]
        types = [lane["media_type"] for lane in industry]
        self.assertIn(MediaTypes.TV.value, types)

    def test_industry_lane_skips_disabled_media_types(self):
        cache.set(rss_cache_key("deadline-tv"), [_industry_article(media_type="tv")])
        pref = self.user.get_or_create_media_pref("tv")
        pref.enabled = False
        pref.save(update_fields=["enabled"])
        if hasattr(self.user, "_pref_cache"):
            del self.user._pref_cache

        response = self.client.get(reverse("news"))
        types = [lane["media_type"] for lane in response.context["industry_lanes"]]
        self.assertNotIn(MediaTypes.TV.value, types)

    def test_library_lane_skipped_when_no_selection(self):
        response = self.client.get(reverse("news"))
        self.assertEqual(response.context["library_lanes"], [])

    def test_library_lane_renders_when_selection_populated(self):
        cache.set(selection_cache_key("anime"), ["1"])
        cache.set(item_cache_key("anime", "1"), [_per_item_article()])

        response = self.client.get(reverse("news"))
        library = response.context["library_lanes"]
        self.assertEqual(len(library), 1)
        self.assertEqual(library[0]["media_type"], "anime")
        self.assertEqual(len(library[0]["articles"]), 1)

    def test_library_lane_excludes_unsupported_types(self):
        # TV has no per-item news support; even if cached, should not appear
        cache.set(selection_cache_key("tv"), ["1"])
        response = self.client.get(reverse("news"))
        library_types = [
            lane["media_type"] for lane in response.context["library_lanes"]
        ]
        self.assertNotIn("tv", library_types)

    def test_news_rejects_post(self):
        response = self.client.post(reverse("news"))
        self.assertEqual(response.status_code, 405)

    def test_news_requires_auth(self):
        self.client.logout()
        response = self.client.get(reverse("news"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response.url)

    def test_sidebar_highlights_news_on_news_page(self):
        response = self.client.get(reverse("news"))
        content = response.content.decode()
        self.assertIn("News", content)
