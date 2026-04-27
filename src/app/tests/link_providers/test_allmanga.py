from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase

from app.link_providers.base import LinkProviderError
from app.link_providers.providers.allmanga import AllMangaProvider


def _mock_response(payload):
    response = MagicMock()
    response.json.return_value = payload
    return response


def _edges(*ids_and_names):
    return {
        "data": {
            "mangas": {
                "edges": [
                    {"_id": _id, "name": name, "englishName": name}
                    for _id, name in ids_and_names
                ],
            },
        },
    }


def _empty():
    return {"data": {"mangas": {"edges": []}}}


def _item(title="Native Title", english_title="English Title"):
    return SimpleNamespace(title=title, english_title=english_title)


class AllMangaProviderTests(TestCase):
    """Unit tests for AllMangaProvider against mocked GraphQL responses."""

    @patch("app.link_providers.providers.allmanga.link_http.http_post")
    def test_returns_link_result_on_match(self, mock_post):
        mock_post.return_value = _mock_response(_edges(("abc123", "Chainsaw Man")))
        result = AllMangaProvider().find(_item(english_title="Chainsaw Man"))
        self.assertIsNotNone(result)
        self.assertEqual(result.url, "https://allmanga.to/manga/abc123")
        self.assertEqual(result.site_id, "allmanga")

    @patch("app.link_providers.providers.allmanga.link_http.http_post")
    def test_returns_none_when_no_results(self, mock_post):
        mock_post.return_value = _mock_response(_empty())
        result = AllMangaProvider().find(_item(english_title="No Such Thing"))
        self.assertIsNone(result)

    @patch("app.link_providers.providers.allmanga.link_http.http_post")
    def test_returns_none_on_malformed_response(self, mock_post):
        mock_post.return_value = _mock_response({"unexpected": "shape"})
        result = AllMangaProvider().find(_item(english_title="Anything"))
        self.assertIsNone(result)

    @patch("app.link_providers.providers.allmanga.link_http.http_post")
    def test_returns_none_on_provider_error(self, mock_post):
        mock_post.side_effect = LinkProviderError("network down")
        result = AllMangaProvider().find(_item(english_title="Anything"))
        self.assertIsNone(result)

    @patch("app.link_providers.providers.allmanga.link_http.http_post")
    def test_falls_back_to_native_title_when_english_misses(self, mock_post):
        mock_post.side_effect = [
            _mock_response(_empty()),
            _mock_response(_edges(("xyz", "Shingeki no Kyojin"))),
        ]
        item = _item(title="Shingeki no Kyojin", english_title="Attack on Titan")
        result = AllMangaProvider().find(item)
        self.assertIsNotNone(result)
        self.assertEqual(result.url, "https://allmanga.to/manga/xyz")
        self.assertEqual(mock_post.call_count, 2)

    @patch("app.link_providers.providers.allmanga.link_http.http_post")
    def test_does_not_double_search_when_titles_identical(self, mock_post):
        mock_post.return_value = _mock_response(_empty())
        item = _item(title="Same Title", english_title="Same Title")
        result = AllMangaProvider().find(item)
        self.assertIsNone(result)
        self.assertEqual(mock_post.call_count, 1)

    @patch("app.link_providers.providers.allmanga.link_http.http_post")
    def test_uses_native_title_when_english_blank(self, mock_post):
        mock_post.return_value = _mock_response(_edges(("nat1", "Berserk")))
        item = _item(title="Berserk", english_title="")
        result = AllMangaProvider().find(item)
        self.assertIsNotNone(result)
        self.assertEqual(result.url, "https://allmanga.to/manga/nat1")
        sent_body = mock_post.call_args.kwargs["json_body"]
        self.assertEqual(sent_body["variables"]["search"]["query"], "Berserk")
