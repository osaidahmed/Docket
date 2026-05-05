import logging

from django.core.cache import cache

import app

logger = logging.getLogger(__name__)

_MAPPING_URL = (
    "https://raw.githubusercontent.com/Kometa-Team/Anime-IDs/"
    "refs/heads/master/anime_ids.json"
)


def fetch_mapping_data():
    """Fetch anime mapping data with caching."""
    data = cache.get("anime_mapping_data")
    if data is None:
        data = app.providers.services.api_request("GITHUB", "GET", _MAPPING_URL)
        cache.set("anime_mapping_data", data)
    return data


def parse_mal_id(mal_id):
    """Parse MAL ID from a comma-separated string, returning the first id."""
    if isinstance(mal_id, str) and "," in mal_id:
        return mal_id.split(",")[0].strip()
    return mal_id


def find_mal_id_in_mapping(mapping_data, field, value):
    """Find MAL ID in mapping_data by matching field == value."""
    for entry in mapping_data.values():
        if entry.get(field) == value and "mal_id" in entry:
            return parse_mal_id(entry["mal_id"])
    return None


def mal_id_from_tmdb_movie(mapping_data, tmdb_movie_id):
    """Find MAL ID for a TMDB movie id."""
    return find_mal_id_in_mapping(mapping_data, "tmdb_movie_id", tmdb_movie_id)


def mal_id_from_imdb(mapping_data, imdb_id):
    """Find MAL ID for an IMDB id."""
    return find_mal_id_in_mapping(mapping_data, "imdb_id", imdb_id)


def mal_id_from_tvdb(mapping_data, tvdb_id, season_number, episode_number):
    """Find (mal_id, episode_in_anime) for a tvdb episode."""
    matching = [
        entry
        for entry in mapping_data.values()
        if entry.get("tvdb_id") == tvdb_id
        and entry.get("tvdb_season") == season_number
        and "mal_id" in entry
    ]
    if not matching:
        return None, None

    matching.sort(key=lambda x: x.get("tvdb_epoffset", 0))
    for i, entry in enumerate(matching):
        current_offset = entry.get("tvdb_epoffset", 0)
        next_offset = (
            matching[i + 1].get("tvdb_epoffset", float("inf"))
            if i < len(matching) - 1
            else float("inf")
        )
        if current_offset < episode_number <= next_offset:
            return parse_mal_id(entry["mal_id"]), episode_number - current_offset

    return None, None


def detect_anime_movie(ids):
    """Try to detect anime movie from external IDs, returning a MAL id or None."""
    mapping_data = fetch_mapping_data()

    if ids["tmdb_id"]:
        mal_id = mal_id_from_tmdb_movie(mapping_data, ids["tmdb_id"])
        if mal_id:
            logger.info("Detected anime movie with MAL ID: %s (via TMDB)", mal_id)
            return mal_id

    if ids["imdb_id"]:
        mal_id = mal_id_from_imdb(mapping_data, ids["imdb_id"])
        if mal_id:
            logger.info("Detected anime movie with MAL ID: %s (via IMDB)", mal_id)
            return mal_id

    return None
