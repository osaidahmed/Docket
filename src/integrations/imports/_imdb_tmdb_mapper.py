import logging

import app
from app.models import MediaTypes
from app.providers.services import ProviderAPIError

logger = logging.getLogger(__name__)

IMDB_TYPE_MAPPING = {
    "Movie": MediaTypes.MOVIE,
    "TV Series": MediaTypes.TV,
    "Short": MediaTypes.MOVIE,
    "TV Mini Series": MediaTypes.TV,
    "TV Movie": MediaTypes.MOVIE,
    "TV Special": MediaTypes.MOVIE,
    "Video": MediaTypes.MOVIE,
}

UNSUPPORTED_TYPES = {
    "TV Episode",
    "TV Short",
    "Video Game",
    "Music Video",
    "Podcast Series",
    "Podcast Episode",
}


def _movie_card(movie):
    return {
        "media_id": movie["id"],
        "title": movie["title"],
        "image": app.providers.tmdb.get_image_url(movie["poster_path"]),
        "media_type": MediaTypes.MOVIE.value,
    }


def _tv_card(tv_show):
    image = app.providers.tmdb.get_image_url(tv_show["poster_path"])
    return {
        "media_id": tv_show["id"],
        "title": tv_show["name"],
        "image": image,
        "media_type": MediaTypes.TV.value,
    }


def lookup_in_tmdb(imdb_id, title_type):
    """Look up media in TMDB using an IMDB id; return a card dict or None."""
    try:
        response = app.providers.tmdb.find(imdb_id, "imdb_id")
    except ProviderAPIError as e:
        logger.warning("Error looking up IMDB ID %s in TMDB: %s", imdb_id, e)
        return None

    media_type = IMDB_TYPE_MAPPING.get(title_type, "")

    if media_type == MediaTypes.MOVIE.value and response.get("movie_results"):
        return _movie_card(response["movie_results"][0])

    if media_type == MediaTypes.TV.value and response.get("tv_results"):
        return _tv_card(response["tv_results"][0])

    return None
