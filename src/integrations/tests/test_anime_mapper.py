from unittest.mock import patch

from django.test import TestCase

from integrations.webhooks import _anime_mapper

_MAPPING = {
    "movie_a": {"tmdb_movie_id": 100, "mal_id": "555"},
    "movie_b": {"imdb_id": "tt9999", "mal_id": "777"},
    "show_a": {"tvdb_id": 200, "tvdb_season": 1, "tvdb_epoffset": 0, "mal_id": "111"},
    "show_b": {"tvdb_id": 200, "tvdb_season": 1, "tvdb_epoffset": 12, "mal_id": "222"},
}


class DetectAnimeMovieTests(TestCase):
    @patch.object(_anime_mapper, "fetch_mapping_data", return_value=_MAPPING)
    def test_resolves_via_tmdb(self, _mock):
        ids = {"tmdb_id": 100, "imdb_id": None}
        self.assertEqual(_anime_mapper.detect_anime_movie(ids), "555")

    @patch.object(_anime_mapper, "fetch_mapping_data", return_value=_MAPPING)
    def test_falls_back_to_imdb(self, _mock):
        ids = {"tmdb_id": None, "imdb_id": "tt9999"}
        self.assertEqual(_anime_mapper.detect_anime_movie(ids), "777")

    @patch.object(_anime_mapper, "fetch_mapping_data", return_value=_MAPPING)
    def test_returns_none_when_no_match(self, _mock):
        ids = {"tmdb_id": 999, "imdb_id": "tt0000"}
        self.assertIsNone(_anime_mapper.detect_anime_movie(ids))

    @patch.object(_anime_mapper, "fetch_mapping_data", return_value=_MAPPING)
    def test_tmdb_takes_precedence_over_imdb(self, _mock):
        ids = {"tmdb_id": 100, "imdb_id": "tt9999"}
        self.assertEqual(_anime_mapper.detect_anime_movie(ids), "555")
