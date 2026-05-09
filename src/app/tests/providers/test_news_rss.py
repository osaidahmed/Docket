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


class ExtractImageTests(TestCase):
    def test_prefers_media_content(self):
        entry = {
            "media_content": [{"url": "https://example.com/mc.jpg"}],
            "media_thumbnail": [{"url": "https://example.com/mt.jpg"}],
        }
        self.assertEqual(news_rss._extract_image(entry), "https://example.com/mc.jpg")

    def test_falls_back_to_media_thumbnail(self):
        entry = {"media_thumbnail": [{"url": "https://example.com/mt.jpg"}]}
        self.assertEqual(news_rss._extract_image(entry), "https://example.com/mt.jpg")

    def test_uses_image_enclosure(self):
        entry = {
            "enclosures": [
                {"href": "https://example.com/skip.pdf", "type": "application/pdf"},
                {"href": "https://example.com/img.jpg", "type": "image/jpeg"},
            ],
        }
        self.assertEqual(news_rss._extract_image(entry), "https://example.com/img.jpg")

    def test_extracts_img_from_content_html(self):
        entry = {
            "content": [
                {
                    "value": '<p>Hi</p><figure><img src="https://example.com/c.jpg" /></figure>'
                }
            ],
        }
        self.assertEqual(news_rss._extract_image(entry), "https://example.com/c.jpg")

    def test_extracts_img_from_summary_html(self):
        entry = {
            "summary": '<figure class="post-thumbnail"><img width="1056" src="https://example.com/s.jpg" /></figure>Body text',
        }
        self.assertEqual(news_rss._extract_image(entry), "https://example.com/s.jpg")

    def test_returns_none_when_no_image(self):
        self.assertIsNone(news_rss._extract_image({"summary": "no images here"}))


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
        cache.set(news_rss.cache_key("comicbook-anime"), [article])
        result = news_rss.get_industry_articles("anime")
        self.assertEqual(result, [article])

    def test_returns_empty_when_no_cache(self):
        self.assertEqual(news_rss.get_industry_articles("anime"), [])

    def test_returns_empty_for_unknown_type(self):
        self.assertEqual(news_rss.get_industry_articles("unknown"), [])
