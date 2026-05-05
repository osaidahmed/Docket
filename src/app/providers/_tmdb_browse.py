"""Browse and discover endpoints for TMDB."""

import requests
from django.conf import settings
from django.core.cache import cache

from app import helpers
from app._types import is_movie_media
from app.models import Sources
from app.providers import services
from app.providers import tmdb as _tmdb

_BROWSE_ENDPOINT_MAP = {
    ("tv", "trending"): "/trending/tv/week",
    ("tv", "popular"): "/tv/popular",
    ("tv", "top_rated"): "/tv/top_rated",
    ("tv", "on_the_air"): "/tv/on_the_air",
    ("movie", "trending"): "/trending/movie/week",
    ("movie", "popular"): "/movie/popular",
    ("movie", "top_rated"): "/movie/top_rated",
    ("movie", "now_playing"): "/movie/now_playing",
}


def _browse_tmdb(
    media_type,
    category,
    page,
    *,
    include_backdrop=False,
    cache_prefix="browse",
    cache_timeout=None,
):
    """Core TMDB browse logic shared by browse() and browse_for_discover()."""
    cache_key = f"{cache_prefix}_{Sources.TMDB.value}_{media_type}_{category}_{page}"
    data = cache.get(cache_key)

    if data is None:
        endpoint = _BROWSE_ENDPOINT_MAP.get((media_type, category))
        url = f"{_tmdb.base_url}{endpoint}"
        params = {**_tmdb.base_params, "page": page}

        try:
            response = services.api_request(
                Sources.TMDB.value,
                "GET",
                url,
                params=params,
            )
        except requests.exceptions.HTTPError as error:
            _tmdb.handle_error(error)

        results = [
            _tmdb._format_browse_result(
                m, media_type, include_backdrop=include_backdrop
            )
            for m in response["results"]
        ]

        data = helpers.format_search_response(
            page,
            20,
            response["total_results"],
            results,
            max_pages=500,
        )
        cache.set(cache_key, data, timeout=cache_timeout)

    return data


def browse(media_type, category, page):
    """Browse media on TMDB by category."""
    return _browse_tmdb(media_type, category, page)


def browse_for_discover(media_type, category, page):
    """Browse media for discover page, including backdrop images."""
    return _browse_tmdb(
        media_type,
        category,
        page,
        include_backdrop=True,
        cache_prefix="discover",
        cache_timeout=60 * 60 * 6,
    )


def discover(media_type, filters, page):
    """Browse media using TMDB discover endpoint with filters."""
    filter_hash = _build_discover_filter_hash(media_type, filters)
    cache_key = f"discover_{Sources.TMDB.value}_{media_type}_{filter_hash}_{page}"
    data = cache.get(cache_key)

    if data is None:
        url = f"{_tmdb.base_url}/discover/{media_type}"
        params = _build_discover_params(media_type, filters, page)

        try:
            response = services.api_request(
                Sources.TMDB.value, "GET", url, params=params
            )
        except requests.exceptions.HTTPError as error:
            _tmdb.handle_error(error)

        results = [
            {
                "media_id": media["id"],
                "source": Sources.TMDB.value,
                "media_type": media_type,
                "title": _tmdb.get_title(media),
                "image": _tmdb.get_image_url(media.get("poster_path")),
                "synopsis": media.get("overview", ""),
            }
            for media in response["results"]
        ]

        data = helpers.format_search_response(
            page, 20, response["total_results"], results, max_pages=500
        )
        cache.set(cache_key, data)

    return data


def _build_discover_params(media_type, filters, page):
    params = {**_tmdb.base_params, "page": page}
    if settings.TMDB_NSFW:
        params["include_adult"] = "true"
    sort_by = filters.get("sort_by", "popularity")
    order = filters.get("order", "desc")
    params["sort_by"] = f"{sort_by}.{order}"
    if filters.get("genres"):
        params["with_genres"] = filters["genres"]
    if filters.get("year"):
        year_key = (
            "primary_release_year"
            if is_movie_media(media_type)
            else "first_air_date_year"
        )
        params[year_key] = filters["year"]
    if filters.get("min_score"):
        params["vote_average.gte"] = filters["min_score"]
        params["vote_count.gte"] = 50
    return params


def get_genre_list(media_type):
    """Fetch the genre list from TMDB for a given media type."""
    cache_key = f"tmdb_{media_type}_genres"
    data = cache.get(cache_key)

    if data is None:
        url = f"{_tmdb.base_url}/genre/{media_type}/list"
        try:
            response = services.api_request(
                Sources.TMDB.value, "GET", url, params=_tmdb.base_params
            )
        except requests.exceptions.HTTPError as error:
            _tmdb.handle_error(error)

        data = [{"id": g["id"], "name": g["name"]} for g in response.get("genres", [])]
        cache.set(cache_key, data, timeout=60 * 60 * 24 * 7)

    return data


def _build_discover_filter_hash(media_type, filters):
    parts = [media_type, *[f"{k}={filters[k]}" for k in sorted(filters) if filters[k]]]
    return "_".join(parts) if len(parts) > 1 else "nofilter"
