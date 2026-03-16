from unittest.mock import MagicMock, patch

from django.test import TestCase

from app.providers import services


def _section_cfg(key="trending", provider="anilist_trending",
                 section_type="ranked_carousel", limit=10):
    return {
        "key": key,
        "label": key.replace("_", " ").title(),
        "type": section_type,
        "provider": provider,
        "limit": limit,
    }


def _browse_cfg(key="now_playing", category="now_playing",
                section_type="card_grid", limit=12):
    return {
        "key": key,
        "label": key.replace("_", " ").title(),
        "type": section_type,
        "browse_category": category,
        "limit": limit,
    }


class ResolveSectionFetcherTests(TestCase):
    @patch("app.providers.anilist.trending")
    def test_anilist_trending(self, mock_fn):
        mock_fn.return_value = {"results": []}
        fetcher = services._resolve_section_fetcher(
            "anime", _section_cfg(provider="anilist_trending"),
        )
        fetcher(1)
        mock_fn.assert_called_once_with("anime", 1, 10)

    @patch("app.providers.anilist.recently_updated")
    def test_anilist_recently_updated(self, mock_fn):
        mock_fn.return_value = {"results": []}
        fetcher = services._resolve_section_fetcher(
            "anime", _section_cfg(provider="anilist_recently_updated"),
        )
        fetcher(2)
        mock_fn.assert_called_once_with("anime", 2, 10)

    @patch("app.providers.anilist.upcoming")
    def test_anilist_upcoming(self, mock_fn):
        mock_fn.return_value = {"results": []}
        fetcher = services._resolve_section_fetcher(
            "anime", _section_cfg(provider="anilist_upcoming"),
        )
        fetcher(1)
        mock_fn.assert_called_once_with("anime", 1, 10)

    @patch("app.providers.anilist.airing_schedule")
    def test_anilist_schedule(self, mock_fn):
        mock_fn.return_value = []
        fetcher = services._resolve_section_fetcher(
            "anime", _section_cfg(provider="anilist_schedule"),
        )
        fetcher(1)
        mock_fn.assert_called_once_with(1, 10)

    @patch("app.providers.jikan.browse_schedule")
    def test_jikan_schedule(self, mock_fn):
        mock_fn.return_value = []
        fetcher = services._resolve_section_fetcher(
            "anime", _section_cfg(provider="jikan_schedule"),
        )
        fetcher(1)
        mock_fn.assert_called_once_with(limit=10)

    @patch("app.providers.mangaupdates.browse")
    def test_mangaupdates(self, mock_fn):
        mock_fn.return_value = {"results": []}
        fetcher = services._resolve_section_fetcher(
            "manga", _section_cfg(provider="mangaupdates_releases"),
        )
        fetcher(1)
        mock_fn.assert_called_once_with("releases", 1)

    @patch("app.providers.tmdb.browse_for_discover")
    def test_spotlight_uses_tmdb_discover(self, mock_fn):
        mock_fn.return_value = {"results": []}
        cfg = _browse_cfg(
            key="spotlight", category="trending",
            section_type="spotlight_carousel",
        )
        fetcher = services._resolve_section_fetcher("movie", cfg)
        fetcher(1)
        mock_fn.assert_called_once_with("movie", "trending", 1)

    @patch("app.providers.services.browse")
    def test_generic_browse_fallback(self, mock_fn):
        mock_fn.return_value = {"results": []}
        cfg = _browse_cfg(category="popular")
        fetcher = services._resolve_section_fetcher("movie", cfg)
        fetcher(1)
        mock_fn.assert_called_once_with("movie", "popular", 1)


class DiscoverSectionsTests(TestCase):
    @patch("app.providers.services._resolve_section_fetcher")
    @patch("app.config.get_discover_sections")
    def test_returns_all_sections(self, mock_config, mock_resolver):
        mock_config.return_value = [
            _section_cfg("trending"),
            _section_cfg("upcoming", provider="anilist_upcoming"),
        ]
        mock_fetcher = MagicMock(return_value={"results": []})
        mock_resolver.return_value = mock_fetcher
        result = services.discover_sections("anime")
        self.assertIn("trending", result)
        self.assertIn("upcoming", result)

    @patch("app.config.get_discover_sections")
    def test_no_sections_returns_empty(self, mock_config):
        mock_config.return_value = None
        result = services.discover_sections("book")
        self.assertEqual(result, {})

    @patch("app.providers.services._resolve_section_fetcher")
    @patch("app.config.get_discover_sections")
    def test_partial_failure_graceful(self, mock_config, mock_resolver):
        mock_config.return_value = [
            _section_cfg("trending"),
            _section_cfg("failing", provider="anilist_upcoming"),
        ]

        def side_effect(media_type, cfg):
            if cfg["key"] == "failing":
                def fail(page):
                    msg = "API error"
                    raise Exception(msg)  # noqa: TRY002
                return fail
            return MagicMock(return_value={"results": []})

        mock_resolver.side_effect = side_effect
        result = services.discover_sections("anime")
        self.assertIsNotNone(result.get("trending"))
        self.assertIsNone(result.get("failing"))


class DiscoverSectionPageTests(TestCase):
    @patch("app.providers.services._resolve_section_fetcher")
    def test_returns_fetcher_result(self, mock_resolver):
        expected = {"results": [{"title": "Test"}]}
        mock_resolver.return_value = MagicMock(return_value=expected)
        result = services.discover_section_page(
            "anime", _section_cfg(), 2,
        )
        self.assertEqual(result, expected)

    @patch("app.providers.services._resolve_section_fetcher")
    def test_page_passed_to_fetcher(self, mock_resolver):
        mock_fetcher = MagicMock(return_value={"results": []})
        mock_resolver.return_value = mock_fetcher
        services.discover_section_page("anime", _section_cfg(), 5)
        mock_fetcher.assert_called_once_with(5)
