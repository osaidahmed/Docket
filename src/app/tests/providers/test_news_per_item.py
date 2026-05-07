"""Tests for the news_per_item provider — per-item news from Jikan, IGDB, BGG."""

from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase

from app.providers import news_per_item


class FetchItemNewsDispatchTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_unsupported_type_returns_empty(self):
        result = news_per_item.fetch_item_news("tv", "12345")
        self.assertEqual(result, [])

    def test_caches_results(self):
        cache.set(news_per_item.cache_key("anime", "1"), [{"title": "Cached"}])
        result = news_per_item.fetch_item_news("anime", "1")
        self.assertEqual(result, [{"title": "Cached"}])

    @patch("app.providers.news_per_item._jikan_news")
    def test_dispatches_anime_to_jikan(self, mock_jikan):
        mock_jikan.return_value = []
        news_per_item.fetch_item_news("anime", "5")
        mock_jikan.assert_called_once_with("anime", "5", 5)

    @patch("app.providers.news_per_item._jikan_news")
    def test_dispatches_manga_to_jikan(self, mock_jikan):
        mock_jikan.return_value = []
        news_per_item.fetch_item_news("manga", "10")
        mock_jikan.assert_called_once_with("manga", "10", 5)

    @patch("app.providers.news_per_item.session.get")
    def test_jikan_failure_caches_empty(self, mock_get):
        mock_get.side_effect = OSError("network down")
        result = news_per_item.fetch_item_news("anime", "999")
        self.assertEqual(result, [])
        self.assertEqual(cache.get(news_per_item.cache_key("anime", "999")), [])


class JikanNewsParsingTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("app.providers.news_per_item.session.get")
    def test_jikan_parses_response(self, mock_get):
        mock_get.return_value = MagicMock(
            raise_for_status=lambda: None,
            json=lambda: {
                "data": [
                    {
                        "title": "Big News",
                        "url": "https://example.com/news/1",
                        "excerpt": "An excerpt",
                        "images": {"jpg": {"image_url": "https://img.test/1.jpg"}},
                        "date": "2026-05-01T12:00:00+00:00",
                    },
                ],
            },
        )
        result = news_per_item.fetch_item_news("anime", "42")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Big News")
        self.assertEqual(result[0]["source"], "MyAnimeList")
        self.assertEqual(result[0]["media_type"], "anime")
        self.assertEqual(result[0]["media_id"], "42")
        self.assertEqual(result[0]["image"], "https://img.test/1.jpg")


class IgdbArticlesTests(TestCase):
    def setUp(self):
        cache.clear()

    @patch("app.providers.igdb._igdb_request")
    def test_igdb_articles_failure_returns_empty(self, mock_request):
        mock_request.side_effect = OSError("auth failed")
        result = news_per_item.fetch_item_news("game", "12345")
        self.assertEqual(result, [])

    @patch("app.providers.igdb._igdb_request")
    def test_igdb_articles_parses_response(self, mock_request):
        mock_request.return_value = [
            {
                "title": "Game News",
                "url": "https://example.com/game-news",
                "summary": "Big update.",
                "image": "abc123",
                "published_at": 1714557600,
            },
        ]
        result = news_per_item.fetch_item_news("game", "42")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Game News")
        self.assertEqual(result[0]["source"], "IGDB")
        self.assertEqual(result[0]["media_type"], "game")
        self.assertIsNotNone(result[0]["image"])


class SafeParseHelperTests(TestCase):
    def test_returns_none_for_falsy(self):
        self.assertIsNone(news_per_item._safe_parse(None, lambda v: v))
        self.assertIsNone(news_per_item._safe_parse("", lambda v: v))

    def test_returns_none_on_exception(self):
        result = news_per_item._safe_parse("bad", int)
        self.assertIsNone(result)

    def test_returns_parsed_value(self):
        self.assertEqual(news_per_item._safe_parse("42", int), 42)
