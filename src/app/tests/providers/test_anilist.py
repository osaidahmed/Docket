from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from app.models import MediaTypes, Sources
from app.providers import anilist, services
from app.tests.providers._http_error_helpers import make_http_error


class CacheClearMixin:
    def setUp(self):
        cache.clear()


def _mock_page_response(media_list, total=100, has_next=True):
    return {
        "data": {
            "Page": {
                "pageInfo": {
                    "total": total,
                    "hasNextPage": has_next,
                    "currentPage": 1,
                    "lastPage": 5,
                    "perPage": 10,
                },
                "media": media_list,
            }
        }
    }


def _mock_schedule_response(schedules, has_next=True):
    return {
        "data": {
            "Page": {
                "pageInfo": {"total": 100, "hasNextPage": has_next},
                "airingSchedules": schedules,
            }
        }
    }


def _make_media(
    mal_id=123, romaji="Test Anime", english="Test Anime EN", is_adult=False, fmt="TV"
):
    return {
        "id": 999,
        "idMal": mal_id,
        "title": {"romaji": romaji, "english": english},
        "coverImage": {
            "large": "https://img.test/l.jpg",
            "extraLarge": "https://img.test/xl.jpg",
        },
        "bannerImage": "https://img.test/banner.jpg",
        "description": "<b>Synopsis</b> text",
        "episodes": 12,
        "chapters": None,
        "status": "RELEASING",
        "nextAiringEpisode": None,
        "startDate": {"year": 2026, "month": 1, "day": 5},
        "popularity": 5000,
        "trending": 80,
        "isAdult": is_adult,
        "format": fmt,
    }


def _make_schedule_entry(
    mal_id=123, romaji="Test", english="Test EN", episode=5, is_adult=False, fmt="TV"
):
    return {
        "episode": episode,
        "airingAt": 1700000000,
        "media": _make_media(mal_id, romaji, english, is_adult, fmt),
    }


class FormatMediaTests(TestCase):
    def test_prefers_romaji_title(self):
        media = _make_media(romaji="Romaji Title", english="English Title")
        result = anilist._format_media(media, MediaTypes.ANIME.value)
        self.assertEqual(result["title"], "Romaji Title")

    def test_fallback_to_english(self):
        media = _make_media(romaji="", english="English Only")
        result = anilist._format_media(media, MediaTypes.ANIME.value)
        self.assertEqual(result["title"], "English Only")

    def test_english_subtitle_when_different(self):
        media = _make_media(romaji="Romaji", english="English")
        result = anilist._format_media(media, MediaTypes.ANIME.value)
        self.assertEqual(result["english_title"], "English")

    def test_no_english_subtitle_when_same(self):
        media = _make_media(romaji="Same", english="Same")
        result = anilist._format_media(media, MediaTypes.ANIME.value)
        self.assertEqual(result["english_title"], "")

    def test_uses_mal_id(self):
        media = _make_media(mal_id=456)
        result = anilist._format_media(media, MediaTypes.ANIME.value)
        self.assertEqual(result["media_id"], "456")
        self.assertEqual(result["source"], Sources.MAL.value)

    def test_fallback_anilist_id(self):
        media = _make_media()
        media["idMal"] = None
        result = anilist._format_media(media, MediaTypes.ANIME.value)
        self.assertEqual(result["media_id"], "999")


class CleanHtmlTests(TestCase):
    def test_strips_tags(self):
        self.assertEqual(anilist._clean_html("<b>bold</b> text"), "bold text")

    def test_empty_input(self):
        self.assertEqual(anilist._clean_html(""), "")
        self.assertEqual(anilist._clean_html(None), "")

    def test_br_to_newline(self):
        self.assertIn("\n", anilist._clean_html("line1<br>line2"))


class ExtractScheduleItemTests(TestCase):
    def test_valid_entry(self):
        seen = set()
        entry = _make_schedule_entry(mal_id=1)
        result = anilist._extract_schedule_item(entry, seen)
        self.assertIsNotNone(result)
        self.assertEqual(result["episode"], 5)
        self.assertIn(1, seen)

    def test_filters_adult(self):
        seen = set()
        entry = _make_schedule_entry(is_adult=True)
        self.assertIsNone(anilist._extract_schedule_item(entry, seen))

    def test_filters_wrong_format(self):
        seen = set()
        entry = _make_schedule_entry(fmt="MUSIC")
        self.assertIsNone(anilist._extract_schedule_item(entry, seen))

    def test_filters_duplicate(self):
        seen = {123}
        entry = _make_schedule_entry(mal_id=123)
        self.assertIsNone(anilist._extract_schedule_item(entry, seen))

    def test_filters_missing_media(self):
        seen = set()
        self.assertIsNone(anilist._extract_schedule_item({"media": None}, seen))


@patch("app.providers.anilist._graphql_request")
class TrendingTests(CacheClearMixin, TestCase):
    def test_returns_formatted_results(self, mock_gql):
        mock_gql.return_value = _mock_page_response([_make_media()])
        data = anilist.trending(MediaTypes.ANIME.value)
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["source"], Sources.MAL.value)

    def test_anime_type_param(self, mock_gql):
        mock_gql.return_value = _mock_page_response([])
        anilist.trending(MediaTypes.ANIME.value)
        variables = mock_gql.call_args[0][1]
        self.assertEqual(variables["type"], "ANIME")

    def test_manga_type_param(self, mock_gql):
        mock_gql.return_value = _mock_page_response([])
        anilist.trending(MediaTypes.MANGA.value)
        variables = mock_gql.call_args[0][1]
        self.assertEqual(variables["type"], "MANGA")

    def test_anime_uses_anime_formats(self, mock_gql):
        mock_gql.return_value = _mock_page_response([])
        anilist.trending(MediaTypes.ANIME.value)
        variables = mock_gql.call_args[0][1]
        self.assertIn("TV", variables["formats"])
        self.assertNotIn("MANGA", variables["formats"])

    def test_manga_uses_manga_formats(self, mock_gql):
        mock_gql.return_value = _mock_page_response([])
        anilist.trending(MediaTypes.MANGA.value)
        variables = mock_gql.call_args[0][1]
        self.assertIn("MANGA", variables["formats"])
        self.assertNotIn("TV", variables["formats"])

    def test_pagination(self, mock_gql):
        mock_gql.return_value = _mock_page_response([])
        anilist.trending(MediaTypes.ANIME.value, page=3)
        variables = mock_gql.call_args[0][1]
        self.assertEqual(variables["page"], 3)

    def test_cached(self, mock_gql):
        mock_gql.return_value = _mock_page_response([_make_media()])
        anilist.trending(MediaTypes.ANIME.value, per_page=5)
        anilist.trending(MediaTypes.ANIME.value, per_page=5)
        mock_gql.assert_called_once()


@patch("app.providers.anilist._graphql_request")
class UpcomingTests(CacheClearMixin, TestCase):
    def test_returns_results(self, mock_gql):
        mock_gql.return_value = _mock_page_response([_make_media()])
        data = anilist.upcoming(MediaTypes.ANIME.value)
        self.assertEqual(len(data["results"]), 1)

    def test_manga_upcoming_uses_manga_formats(self, mock_gql):
        mock_gql.return_value = _mock_page_response([])
        anilist.upcoming(MediaTypes.MANGA.value)
        variables = mock_gql.call_args[0][1]
        self.assertIn("MANGA", variables["formats"])
        self.assertNotIn("TV", variables["formats"])

    def test_has_next_page(self, mock_gql):
        mock_gql.return_value = _mock_page_response([_make_media()], has_next=True)
        data = anilist.upcoming(MediaTypes.ANIME.value)
        self.assertTrue(data["has_next_page"])

    def test_cached(self, mock_gql):
        mock_gql.return_value = _mock_page_response([_make_media()])
        anilist.upcoming(MediaTypes.ANIME.value, per_page=7)
        anilist.upcoming(MediaTypes.ANIME.value, per_page=7)
        mock_gql.assert_called_once()


@patch("app.providers.anilist._graphql_request")
class RecentlyUpdatedTests(CacheClearMixin, TestCase):
    def test_anime_uses_schedule_query(self, mock_gql):
        mock_gql.return_value = _mock_schedule_response(
            [_make_schedule_entry(mal_id=i) for i in range(5)],
            has_next=False,
        )
        anilist.recently_updated(MediaTypes.ANIME.value, per_page=5)
        query_used = mock_gql.call_args[0][0]
        self.assertIn("airingSchedules", query_used)

    def test_manga_uses_updated_at_query(self, mock_gql):
        mock_gql.return_value = _mock_page_response([_make_media()])
        anilist.recently_updated(MediaTypes.MANGA.value)
        query_used = mock_gql.call_args[0][0]
        self.assertIn("UPDATED_AT_DESC", query_used)

    def test_manga_recently_updated_uses_manga_formats(self, mock_gql):
        mock_gql.return_value = _mock_page_response([_make_media()])
        anilist.recently_updated(MediaTypes.MANGA.value)
        variables = mock_gql.call_args[0][1]
        self.assertIn("MANGA", variables["formats"])
        self.assertNotIn("TV", variables["formats"])

    def test_manga_recently_updated_returns_results(self, mock_gql):
        mock_gql.return_value = _mock_page_response([_make_media()])
        data = anilist.recently_updated(MediaTypes.MANGA.value)
        self.assertEqual(len(data["results"]), 1)

    def test_deduplicates_anime(self, mock_gql):
        mock_gql.return_value = _mock_schedule_response(
            [_make_schedule_entry(mal_id=1, episode=i) for i in range(5)],
            has_next=False,
        )
        data = anilist.recently_updated(MediaTypes.ANIME.value, per_page=10)
        self.assertEqual(len(data["results"]), 1)

    def test_filters_adult_anime(self, mock_gql):
        mock_gql.return_value = _mock_schedule_response(
            [_make_schedule_entry(mal_id=1, is_adult=True)],
            has_next=False,
        )
        data = anilist.recently_updated(MediaTypes.ANIME.value, per_page=10)
        self.assertEqual(len(data["results"]), 0)

    def test_filters_non_tv_movie(self, mock_gql):
        mock_gql.return_value = _mock_schedule_response(
            [_make_schedule_entry(mal_id=1, fmt="MUSIC")],
            has_next=False,
        )
        data = anilist.recently_updated(MediaTypes.ANIME.value, per_page=10)
        self.assertEqual(len(data["results"]), 0)

    def test_has_next_page_when_full(self, mock_gql):
        entries = [_make_schedule_entry(mal_id=i) for i in range(5)]
        mock_gql.return_value = _mock_schedule_response(entries, has_next=True)
        data = anilist.recently_updated(MediaTypes.ANIME.value, per_page=5)
        self.assertTrue(data["has_next_page"])


@patch("app.providers.anilist._graphql_request")
class AiringScheduleTests(CacheClearMixin, TestCase):
    def test_returns_list(self, mock_gql):
        mock_gql.return_value = {
            "data": {
                "Page": {
                    "pageInfo": {"total": 10, "hasNextPage": False},
                    "airingSchedules": [
                        {
                            "airingAt": 1700000000,
                            "episode": 3,
                            "media": {
                                "id": 1,
                                "idMal": 100,
                                "title": {"romaji": "Test", "english": "Test EN"},
                                "coverImage": {"large": "https://img.test/l.jpg"},
                                "status": "RELEASING",
                            },
                        }
                    ],
                }
            }
        }
        data = anilist.airing_schedule()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["episode"], 3)
        self.assertEqual(data[0]["airing_at"], 1700000000)

    def test_filters_missing_media(self, mock_gql):
        mock_gql.return_value = {
            "data": {
                "Page": {
                    "pageInfo": {"total": 1, "hasNextPage": False},
                    "airingSchedules": [{"airingAt": 1, "episode": 1, "media": None}],
                }
            }
        }
        data = anilist.airing_schedule()
        self.assertEqual(len(data), 0)


class GraphqlRequestErrorTests(TestCase):
    @patch("app.providers.anilist.services.api_request")
    def test_http_error_wraps_in_provider_error(self, mock_api):
        mock_api.side_effect = make_http_error(500, {"errors": ["server"]})
        with self.assertRaises(services.ProviderAPIError):
            anilist._graphql_request("query {}", {})


@patch("app.providers.anilist._graphql_request")
class RecentlyAiredMultiPageTests(CacheClearMixin, TestCase):
    def test_continues_paginating_until_filled(self, mock_gql):
        first_page = _mock_schedule_response(
            [_make_schedule_entry(mal_id=1)],
            has_next=True,
        )
        second_page = _mock_schedule_response(
            [_make_schedule_entry(mal_id=2), _make_schedule_entry(mal_id=3)],
            has_next=False,
        )
        mock_gql.side_effect = [first_page, second_page]

        data = anilist.recently_updated(MediaTypes.ANIME.value, per_page=3)

        self.assertEqual(len(data["results"]), 3)
        self.assertEqual(mock_gql.call_count, 2)
