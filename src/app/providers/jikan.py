import logging

from django.conf import settings
from django.core.cache import cache

from app import helpers
from app.models import MediaTypes, Sources
from app.providers import services

logger = logging.getLogger(__name__)
base_url = "https://api.jikan.moe/v4"

FILTER_PARAM_MAP = {
    "sort_by": "order_by",
    "order": "sort",
    "genres": "genres",
    "min_score": "min_score",
    "anime_type": "type",
    "manga_type": "type",
}


def _build_params(filters, page):
    params = {"page": page, "limit": settings.PER_PAGE}
    if not settings.MAL_NSFW:
        params["sfw"] = "true"

    for filter_key, param_name in FILTER_PARAM_MAP.items():
        if filters.get(filter_key):
            params[param_name] = filters[filter_key]

    return params


def browse(media_type, filters, page):
    """Browse anime or manga on Jikan with filters."""
    filter_hash = _build_filter_hash(media_type, filters)
    cache_key = f"browse_jikan_{media_type}_{filter_hash}_{page}"
    data = cache.get(cache_key)

    if data is None:
        url = f"{base_url}/{media_type}"
        params = _build_params(filters, page)

        try:
            response = services.api_request("jikan", "GET", url, params=params)
        except Exception:
            logger.exception("Jikan browse failed for %s", media_type)
            return helpers.format_search_response(page, settings.PER_PAGE, 0, [])

        results = [
            {
                "media_id": item["mal_id"],
                "source": Sources.MAL.value,
                "media_type": media_type,
                "title": item.get("title", ""),
                "english_title": item.get("title_english") or "",
                "image": _get_image_url(item),
                "synopsis": item.get("synopsis") or "",
                "is_ongoing": not item.get("chapters")
                if media_type == MediaTypes.MANGA.value
                else item.get("status") == "Currently Airing",
            }
            for item in response.get("data", [])
        ]

        pagination = response.get("pagination", {})
        total_items = pagination.get("items", {}).get("total", 0)
        data = helpers.format_search_response(
            page, settings.PER_PAGE, total_items, results
        )
        cache.set(cache_key, data)

    return data


def get_genres(media_type):
    """Fetch genre list for anime or manga from Jikan."""
    cache_key = f"jikan_{media_type}_genres"
    data = cache.get(cache_key)

    if data is None:
        url = f"{base_url}/genres/{media_type}"
        try:
            response = services.api_request("jikan", "GET", url)
        except Exception:
            logger.exception("Jikan get_genres failed for %s", media_type)
            return []

        data = [
            {"id": g["mal_id"], "name": g["name"]} for g in response.get("data", [])
        ]
        cache.set(cache_key, data, timeout=60 * 60 * 24 * 7)

    return data


def _get_image_url(item):
    images = item.get("images", {})
    jpg = images.get("jpg", {})
    return jpg.get("large_image_url") or jpg.get("image_url") or settings.IMG_NONE


def _build_filter_hash(media_type, filters):
    parts = [media_type, *[f"{k}={filters[k]}" for k in sorted(filters) if filters[k]]]
    return "_".join(parts) if len(parts) > 1 else "nofilter"
