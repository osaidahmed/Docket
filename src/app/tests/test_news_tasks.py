"""Tests for news_tasks Celery tasks."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from app import news_tasks
from app.mixins import disable_fetch_releases
from app.models import Anime, Item, MediaTypes, Sources, Status
from app.providers.news_per_item import cache_key as item_cache_key

_FAKE_METADATA = {
    "max_progress": 12,
    "title": "Test",
    "image": "http://example.com/img.jpg",
    "details": {},
    "related": {},
    "source": Sources.MAL.value,
    "media_type": MediaTypes.ANIME.value,
    "media_id": "1",
}


class WarmIndustryNewsTaskTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("app.providers.news_rss.fetch_source")
    def test_warm_industry_news_calls_each_unique_source(self, mock_fetch):
        news_tasks.warm_industry_news()
        # Anime and manga share ANN — should fetch only once
        slugs = {call.args[0]["slug"] for call in mock_fetch.call_args_list}
        # Expect distinct slugs across all configured types
        self.assertGreaterEqual(len(slugs), 5)

    @patch("app.providers.news_rss.fetch_source")
    def test_warm_industry_news_continues_on_failure(self, mock_fetch):
        mock_fetch.side_effect = OSError("boom")
        # Should not raise
        news_tasks.warm_industry_news()


class WarmLibraryNewsSelectionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(username="t", password="12345")

    def _create_anime(self, media_id, status=Status.PLANNING.value):
        with disable_fetch_releases():
            item = Item.objects.create(
                media_id=media_id,
                source=Sources.MAL.value,
                media_type=MediaTypes.ANIME.value,
                title=f"Anime {media_id}",
                image="http://example.com/img.jpg",
            )
            anime = Anime(item=item, user=self.user, status=status)
            anime._metadata = _FAKE_METADATA  # skip API fetch in process_status
            anime.save()

    def test_selection_caches_for_each_supported_type(self):
        for i in range(7):
            self._create_anime(str(i))

        news_tasks.warm_library_news_selection()
        selection = cache.get(news_tasks.selection_cache_key("anime"))
        self.assertIsNotNone(selection)
        self.assertLessEqual(len(selection), 5)

    def test_selection_excludes_completed_and_dropped(self):
        self._create_anime("1", status=Status.PLANNING.value)
        self._create_anime("2", status=Status.IN_PROGRESS.value)
        self._create_anime("3", status=Status.COMPLETED.value)
        self._create_anime("4", status=Status.DROPPED.value)

        news_tasks.warm_library_news_selection()
        selection = cache.get(news_tasks.selection_cache_key("anime"))
        self.assertIn("1", selection)
        self.assertIn("2", selection)
        self.assertNotIn("3", selection)
        self.assertNotIn("4", selection)

    def test_selection_empty_when_no_tracked_items(self):
        news_tasks.warm_library_news_selection()
        for media_type in ("anime", "manga", "game", "boardgame"):
            selection = cache.get(news_tasks.selection_cache_key(media_type))
            self.assertEqual(selection, [])


class WarmLibraryNewsContentTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("app.providers.news_per_item.fetch_item_news")
    def test_warms_content_for_each_selected_item(self, mock_fetch):
        cache.set(news_tasks.selection_cache_key("anime"), ["1", "2", "3"])
        news_tasks.warm_library_news_content()
        called_with = [call.args for call in mock_fetch.call_args_list]
        self.assertIn(("anime", "1"), called_with)
        self.assertIn(("anime", "2"), called_with)
        self.assertIn(("anime", "3"), called_with)

    @patch("app.providers.news_per_item.fetch_item_news")
    def test_warm_continues_on_failure(self, mock_fetch):
        mock_fetch.side_effect = OSError("api down")
        cache.set(news_tasks.selection_cache_key("anime"), ["1"])
        # Should not raise
        news_tasks.warm_library_news_content()

    @patch("app.providers.news_per_item.fetch_item_news")
    def test_warm_skips_when_no_selection(self, mock_fetch):
        news_tasks.warm_library_news_content()
        mock_fetch.assert_not_called()

    def test_item_cache_key_format(self):
        self.assertEqual(item_cache_key("anime", "5"), "news_item_anime_5")
