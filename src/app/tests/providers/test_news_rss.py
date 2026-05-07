"""Tests for the news_rss provider — feedparser-based RSS fetching."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase

from app.providers import news_rss


def _make_entry(**overrides):
    base = {
        "title": "Test Article",
        "link": "https://example.com/article",
        "summary": "A test article summary.",
        "published_parsed": (2026, 5, 1, 12, 0, 0, 0, 0, 0),
        "media_content": [{"url": "https://example.com/img.jpg"}],
    }
    base.update(overrides)
    return base


class FetchSourceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.source_cfg = {
            "slug": "test-source",
            "label": "Test Source",
            "rss_url": "https://example.com/feed",
        }

    @patch("app.providers.news_rss.feedparser.parse")
    @patch("app.providers.news_rss.session.get")
    def test_fetch_source_caches_articles(self, mock_get, mock_parse):
        mock_get.return_value = MagicMock(
            content=b"<rss />", raise_for_status=lambda: None
        )
        mock_parse.return_value = MagicMock(entries=[_make_entry()])

        articles = news_rss.fetch_source(self.source_cfg, "tv")

        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "Test Article")
        self.assertEqual(articles[0]["source"], "Test Source")
        self.assertEqual(articles[0]["media_type"], "tv")
        self.assertIsNone(articles[0]["media_id"])
        self.assertEqual(
            articles[0]["published_at"], datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
        )

        # Cache populated
        cached = cache.get(news_rss.cache_key("test-source"))
        self.assertEqual(cached, articles)

    @patch("app.providers.news_rss.session.get")
    def test_fetch_source_failure_caches_empty(self, mock_get):
        mock_get.side_effect = OSError("network down")
        articles = news_rss.fetch_source(self.source_cfg, "tv")
        self.assertEqual(articles, [])
        self.assertEqual(cache.get(news_rss.cache_key("test-source")), [])

    @patch("app.providers.news_rss.feedparser.parse")
    @patch("app.providers.news_rss.session.get")
    def test_fetch_source_respects_limit(self, mock_get, mock_parse):
        mock_get.return_value = MagicMock(
            content=b"<rss />", raise_for_status=lambda: None
        )
        mock_parse.return_value = MagicMock(
            entries=[_make_entry(title=f"Article {i}") for i in range(20)]
        )
        articles = news_rss.fetch_source(self.source_cfg, "tv", limit=5)
        self.assertEqual(len(articles), 5)


class GetIndustryArticlesTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_reads_from_cache_only(self):
        article = {
            "title": "Cached",
            "url": "u",
            "source": "S",
            "summary": "",
            "image": None,
            "published_at": None,
            "media_type": "anime",
            "media_id": None,
        }
        cache.set(news_rss.cache_key("ann"), [article])
        result = news_rss.get_industry_articles("anime")
        self.assertEqual(result, [article])

    def test_returns_empty_when_no_cache(self):
        self.assertEqual(news_rss.get_industry_articles("anime"), [])

    def test_returns_empty_for_unknown_type(self):
        self.assertEqual(news_rss.get_industry_articles("unknown"), [])
