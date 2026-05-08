from unittest.mock import patch

from django.test import TestCase

from app.models import MediaTypes, Sources
from app.providers import (
    anilist,
    comicvine,
    igdb,
    mangaupdates,
    tmdb,
)


class IgdbBuildGameMetadataShapeTests(TestCase):
    def _fixture(self):
        return {
            "id": 1942,
            "url": "https://www.igdb.com/games/the-witcher-3",
            "name": "The Witcher 3",
            "summary": "A fantasy RPG.",
            "game_type": 0,
            "cover": {"image_id": "co1234"},
            "first_release_date": 1431993600,
            "total_rating": 95.0,
            "total_rating_count": 1500,
            "genres": [{"name": "RPG"}],
            "themes": [{"name": "Fantasy"}],
            "platforms": [{"name": "PC"}, {"name": "PS4"}],
            "involved_companies": [{"company": {"name": "CD Projekt RED"}}],
            "parent_game": None,
            "remasters": None,
            "remakes": None,
            "expansions": None,
            "dlcs": None,
            "standalone_expansions": None,
            "expanded_games": None,
            "similar_games": None,
        }

    def test_full_key_set(self):
        data = igdb._build_game_metadata(self._fixture())
        assert set(data.keys()) == {
            "media_id",
            "source",
            "source_url",
            "media_type",
            "title",
            "max_progress",
            "image",
            "synopsis",
            "genres",
            "score",
            "score_count",
            "details",
            "related",
        }

    def test_details_key_set(self):
        data = igdb._build_game_metadata(self._fixture())
        assert set(data["details"].keys()) == {
            "format",
            "release_date",
            "themes",
            "platforms",
            "companies",
        }

    def test_related_key_set(self):
        data = igdb._build_game_metadata(self._fixture())
        assert set(data["related"].keys()) == {
            "parent_game",
            "remasters",
            "remakes",
            "expansions",
            "dlcs",
            "standalone_expansions",
            "expanded_games",
            "recommendations",
        }

    def test_scalar_values(self):
        data = igdb._build_game_metadata(self._fixture())
        assert data["media_id"] == 1942
        assert data["source"] == Sources.IGDB.value
        assert data["source_url"] == "https://www.igdb.com/games/the-witcher-3"
        assert data["media_type"] == MediaTypes.GAME.value
        assert data["title"] == "The Witcher 3"
        assert data["max_progress"] is None
        assert data["synopsis"] == "A fantasy RPG."
        assert data["score"] == 9.5
        assert data["score_count"] == 1500
        assert data["genres"] == ["RPG"]
        assert data["details"]["format"] == "Main game"
        assert data["details"]["themes"] == ["Fantasy"]
        assert data["details"]["platforms"] == ["PC", "PS4"]
        assert data["details"]["companies"] == "CD Projekt RED"


class IgdbGameTypeMappingTests(TestCase):
    def test_full_mapping(self):
        expected = {
            0: "Main game",
            1: "DLC",
            2: "Expansion",
            3: "Bundle",
            4: "Standalone expansion",
            5: "Mod",
            6: "Episode",
            7: "Season",
            8: "Remake",
            9: "Remaster",
            10: "Expanded game",
            11: "Port",
            12: "Fork",
            13: "Pack",
            14: "Update",
        }
        for game_type_id, label in expected.items():
            assert igdb.get_game_type(game_type_id) == label

    def test_unknown_returns_none(self):
        assert igdb.get_game_type(999) is None


class TmdbBuildMovieMetadataShapeTests(TestCase):
    def _fixture(self):
        return {
            "id": 27205,
            "title": "Inception",
            "overview": "A thief who steals corporate secrets.",
            "poster_path": "/poster.jpg",
            "genres": [{"id": 28, "name": "Action"}],
            "vote_average": 8.4,
            "vote_count": 33000,
            "release_date": "2010-07-15",
            "status": "Released",
            "runtime": 148,
            "production_companies": [{"name": "Warner Bros."}],
            "production_countries": [{"name": "United States"}],
            "spoken_languages": [{"english_name": "English"}],
            "credits": {"cast": []},
            "external_ids": {},
            "belongs_to_collection": None,
            "recommendations": {"results": []},
        }

    def test_full_key_set(self):
        with patch("app.providers.tmdb.services.api_request") as mock_api:
            mock_api.return_value = {}
            data = tmdb._build_movie_metadata("27205", self._fixture())
        assert set(data.keys()) == {
            "media_id",
            "source",
            "source_url",
            "media_type",
            "title",
            "max_progress",
            "image",
            "synopsis",
            "genres",
            "score",
            "score_count",
            "details",
            "cast",
            "external_links",
            "related",
        }

    def test_details_key_set(self):
        with patch("app.providers.tmdb.services.api_request") as mock_api:
            mock_api.return_value = {}
            data = tmdb._build_movie_metadata("27205", self._fixture())
        assert set(data["details"].keys()) == {
            "format",
            "release_date",
            "status",
            "runtime",
            "studios",
            "country",
            "languages",
        }

    def test_scalar_values(self):
        with patch("app.providers.tmdb.services.api_request") as mock_api:
            mock_api.return_value = {}
            data = tmdb._build_movie_metadata("27205", self._fixture())
        assert data["media_id"] == "27205"
        assert data["source"] == Sources.TMDB.value
        assert data["source_url"] == "https://www.themoviedb.org/movie/27205"
        assert data["media_type"] == MediaTypes.MOVIE.value
        assert data["title"] == "Inception"
        assert data["max_progress"] == 1
        assert data["synopsis"] == "A thief who steals corporate secrets."
        assert data["score"] == 8.4
        assert data["score_count"] == 33000
        assert data["details"]["status"] == "Released"

    def test_synopsis_falls_back_when_empty(self):
        fixture = self._fixture()
        fixture["overview"] = ""
        with patch("app.providers.tmdb.services.api_request") as mock_api:
            mock_api.return_value = {}
            data = tmdb._build_movie_metadata("27205", fixture)
        assert data["synopsis"] == "No synopsis available."


class AnilistFormatMediaShapeTests(TestCase):
    def _fixture(self):
        return {
            "id": 21,
            "idMal": 100,
            "title": {
                "romaji": "Shingeki no Kyojin",
                "english": "Attack on Titan",
            },
            "coverImage": {"extraLarge": "https://example/xl.jpg"},
            "bannerImage": "https://example/banner.jpg",
            "description": "<p>Humanity vs titans.</p>",
        }

    def test_full_key_set(self):
        data = anilist._format_media(self._fixture(), MediaTypes.ANIME.value)
        assert set(data.keys()) == {
            "media_id",
            "source",
            "media_type",
            "title",
            "english_title",
            "image",
            "backdrop",
            "synopsis",
        }

    def test_scalar_values(self):
        data = anilist._format_media(self._fixture(), MediaTypes.ANIME.value)
        assert data["media_id"] == "100"
        assert data["source"] == Sources.MAL.value
        assert data["media_type"] == MediaTypes.ANIME.value
        assert data["title"] == "Shingeki no Kyojin"
        assert data["english_title"] == "Attack on Titan"
        assert data["image"] == "https://example/xl.jpg"
        assert data["backdrop"] == "https://example/banner.jpg"
        assert data["synopsis"] == "Humanity vs titans."

    def test_falls_back_to_anilist_id_when_no_mal_id(self):
        fixture = self._fixture()
        fixture["idMal"] = None
        data = anilist._format_media(fixture, MediaTypes.ANIME.value)
        assert data["media_id"] == "21"

    def test_null_title_does_not_crash(self):
        fixture = self._fixture()
        fixture["title"] = None
        data = anilist._format_media(fixture, MediaTypes.ANIME.value)
        assert data["title"] == ""
        assert data["english_title"] == ""

    def test_english_blank_when_equal_to_romaji(self):
        fixture = self._fixture()
        fixture["title"] = {"romaji": "Same", "english": "Same"}
        data = anilist._format_media(fixture, MediaTypes.ANIME.value)
        assert data["english_title"] == ""


class ComicvineAssembleComicShapeTests(TestCase):
    def _fixture(self):
        return {
            "name": "Spider-Man",
            "site_detail_url": "https://comicvine.example/spiderman",
            "image": {"medium_url": "https://example/cover.jpg"},
            "description": "<p>Web-slinger.</p>",
            "concepts": [{"name": "Superhero"}],
            "start_year": "1962",
            "publisher": {"name": "Marvel"},
            "count_of_issues": 100,
            "last_issue": {
                "issue_number": "100",
                "id": 9999,
                "name": "The End",
            },
            "people": [],
            "date_last_updated": "2026-05-01 12:00:00",
        }

    def test_full_key_set(self):
        data = comicvine._assemble_comic_metadata(self._fixture(), [], "1234")
        assert set(data.keys()) == {
            "media_id",
            "source",
            "source_url",
            "media_type",
            "title",
            "max_progress",
            "max_issue_number",
            "image",
            "synopsis",
            "genres",
            "score",
            "score_count",
            "details",
            "related",
            "last_issue_id",
        }

    def test_details_key_set(self):
        data = comicvine._assemble_comic_metadata(self._fixture(), [], "1234")
        assert set(data["details"].keys()) == {
            "start_date",
            "publisher",
            "issues_count",
            "last_issue_name",
            "last_issue_number",
            "people",
            "last_updated",
        }

    def test_scalar_values(self):
        data = comicvine._assemble_comic_metadata(self._fixture(), [], "1234")
        assert data["media_id"] == "1234"
        assert data["source"] == Sources.COMICVINE.value
        assert data["source_url"] == "https://comicvine.example/spiderman"
        assert data["media_type"] == MediaTypes.COMIC.value
        assert data["title"] == "Spider-Man"
        assert data["score"] is None
        assert data["score_count"] is None
        assert data["last_issue_id"] == 9999
        assert data["details"]["last_updated"] == "2026-05-01"
        assert data["related"]["recommendations"] == []


class MangaupdatesAssembleShapeTests(TestCase):
    def _fixture(self, *, completed=True):
        return {
            "title": "Berserk",
            "description": "Dark fantasy.",
            "image": {"url": {"original": "https://example/berserk.jpg"}},
            "year": "1989",
            "type": "Manga",
            "status": "Ongoing",
            "completed": completed,
            "latest_chapter": 364,
            "bayesian_rating": 9.5,
            "rating_votes": 1000,
            "authors": [{"name": "Kentaro Miura", "type": "Author"}],
            "genres": [{"genre": "Fantasy"}],
            "url": "https://www.mangaupdates.com/series/123",
        }

    def test_full_key_set(self):
        data = mangaupdates._assemble_manga_metadata("123", self._fixture())
        assert set(data.keys()) >= {
            "media_id",
            "source",
            "source_url",
            "media_type",
            "title",
            "image",
            "synopsis",
            "max_progress",
            "genres",
            "score",
            "score_count",
            "details",
        }

    def test_details_key_set(self):
        data = mangaupdates._assemble_manga_metadata("123", self._fixture())
        assert set(data["details"].keys()) == {
            "format",
            "authors",
            "year",
            "status_in_country_of_origin",
            "latest_chapter_translated",
        }

    def test_scalar_values(self):
        data = mangaupdates._assemble_manga_metadata("123", self._fixture())
        assert data["media_id"] == "123"
        assert data["source"] == Sources.MANGAUPDATES.value
        assert data["source_url"] == "https://www.mangaupdates.com/series/123"
        assert data["media_type"] == MediaTypes.MANGA.value
        assert data["title"] == "Berserk"
        assert data["max_progress"] == 364
        assert data["details"]["format"] == "Manga"
        assert data["details"]["year"] == "1989"

    def test_max_progress_none_when_not_completed(self):
        data = mangaupdates._assemble_manga_metadata(
            "123",
            self._fixture(completed=False),
        )
        assert data["max_progress"] is None
