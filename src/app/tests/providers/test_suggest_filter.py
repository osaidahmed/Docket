from unittest.mock import patch

from django.test import TestCase

from app.models import MediaTypes, Sources
from app.providers import services


class SearchSuggestFilterTests(TestCase):
    """Test type filtering, dedup, and exclusion logic."""

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_respects_enabled_types(self, mock_tmdb, mock_mal):
        """Disabled types are not queried."""
        mock_tmdb.return_value = []
        mock_mal.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        services.search_suggest_api("Test", [MediaTypes.MANGA.value])

        mock_tmdb.assert_not_called()
        self.assertEqual(mock_mal.call_count, 1)

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_deduplication_by_media_id_and_source(self, mock_tmdb, mock_mal):
        """Duplicate (media_id, source) pairs are removed."""
        mock_tmdb.return_value = [
            {
                "media_id": 20,
                "source": Sources.TMDB.value,
                "media_type": "tv",
                "title": "Show A",
                "image": "http://example.com/a.jpg",
            },
        ]
        mock_mal.side_effect = [
            {
                "page": 1,
                "total_results": 1,
                "total_pages": 1,
                "results": [
                    {
                        "media_id": 20,
                        "source": Sources.TMDB.value,
                        "media_type": "tv",
                        "title": "Show A Duplicate",
                        "image": "http://example.com/a2.jpg",
                        "synopsis": "",
                    },
                ],
            },
            {
                "page": 1,
                "total_results": 0,
                "total_pages": 1,
                "results": [],
            },
        ]

        enabled = [
            MediaTypes.TV.value,
            MediaTypes.MOVIE.value,
            MediaTypes.ANIME.value,
            MediaTypes.MANGA.value,
        ]
        results = services.search_suggest_api("Show", enabled)

        keys = [(str(r["media_id"]), r["source"]) for r in results]
        self.assertEqual(len(keys), len(set(keys)))

    @patch("app.providers.mal.search")
    @patch("app.providers.tmdb.search_multi")
    def test_excludes_local_keys(self, mock_tmdb, mock_mal):
        """Items matching local_keys are excluded from results."""
        mock_tmdb.return_value = [
            {
                "media_id": 100,
                "source": Sources.TMDB.value,
                "media_type": "tv",
                "title": "Narcos",
                "image": "http://example.com/narcos.jpg",
            },
            {
                "media_id": 200,
                "source": Sources.TMDB.value,
                "media_type": "movie",
                "title": "Narnia",
                "image": "http://example.com/narnia.jpg",
            },
        ]
        mock_mal.return_value = {
            "page": 1,
            "total_results": 0,
            "total_pages": 1,
            "results": [],
        }

        local_keys = {("100", Sources.TMDB.value)}
        results = services.search_suggest_api(
            "Nar",
            [MediaTypes.TV.value, MediaTypes.MOVIE.value],
            local_keys=local_keys,
        )

        result_ids = [(str(r["media_id"]), r["source"]) for r in results]
        self.assertNotIn(("100", Sources.TMDB.value), result_ids)
        self.assertIn(("200", Sources.TMDB.value), result_ids)

    def test_empty_query_returns_empty(self):
        """Empty or whitespace query returns empty list."""
        enabled = [
            MediaTypes.TV.value,
            MediaTypes.MOVIE.value,
            MediaTypes.ANIME.value,
            MediaTypes.MANGA.value,
        ]
        result = services.search_suggest_api("", enabled)
        self.assertEqual(result, [])

        result = services.search_suggest_api("   ", enabled)
        self.assertEqual(result, [])
