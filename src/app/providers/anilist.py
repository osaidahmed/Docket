import html
import logging
import re
import time

import requests
from django.core.cache import cache

from app import helpers
from app.models import MediaTypes, Sources
from app.providers import services

logger = logging.getLogger(__name__)

base_url = "https://graphql.anilist.co"

CACHE_TTL_RECENT = 60 * 60 * 2
CACHE_TTL_TRENDING = 60 * 60 * 6
CACHE_TTL_SCHEDULE = 60 * 60 * 6
CACHE_TTL_UPCOMING = 60 * 60 * 24

_MEDIA_FIELDS = """
    id
    idMal
    title { romaji english }
    coverImage { large extraLarge }
    bannerImage
    description(asHtml: false)
    episodes
    chapters
    status
    nextAiringEpisode { airingAt episode }
    startDate { year month day }
    popularity
    trending
    isAdult
"""

_TRENDING_QUERY = f"""
query ($type: MediaType, $page: Int, $perPage: Int, $formats: [MediaFormat]) {{
    Page(page: $page, perPage: $perPage) {{
        pageInfo {{ total currentPage lastPage hasNextPage perPage }}
        media(type: $type, sort: TRENDING_DESC, isAdult: false,
              format_in: $formats) {{
            {_MEDIA_FIELDS}
        }}
    }}
}}
"""

_RECENTLY_UPDATED_QUERY = f"""
query ($type: MediaType, $page: Int, $perPage: Int, $formats: [MediaFormat]) {{
    Page(page: $page, perPage: $perPage) {{
        pageInfo {{ total currentPage lastPage hasNextPage perPage }}
        media(type: $type, sort: UPDATED_AT_DESC, isAdult: false,
              format_in: $formats,
              status_in: [RELEASING, FINISHED]) {{
            {_MEDIA_FIELDS}
        }}
    }}
}}
"""

_UPCOMING_QUERY = f"""
query ($type: MediaType, $page: Int, $perPage: Int, $formats: [MediaFormat]) {{
    Page(page: $page, perPage: $perPage) {{
        pageInfo {{ total currentPage lastPage hasNextPage perPage }}
        media(type: $type, sort: POPULARITY_DESC, status: NOT_YET_RELEASED,
              isAdult: false, format_in: $formats) {{
            {_MEDIA_FIELDS}
        }}
    }}
}}
"""

_ANIME_FORMATS = ["TV", "MOVIE"]
_MANGA_FORMATS = ["MANGA", "ONE_SHOT"]

_SCHEDULE_QUERY = """
query ($page: Int, $perPage: Int, $start: Int, $end: Int) {
    Page(page: $page, perPage: $perPage) {
        pageInfo { total currentPage lastPage hasNextPage perPage }
        airingSchedules(airingAt_greater: $start, airingAt_lesser: $end, sort: TIME) {
            airingAt
            episode
            media {
                id
                idMal
                title { romaji english }
                coverImage { large }
                status
            }
        }
    }
}
"""

_RECENTLY_AIRED_SCHEDULE = """
query ($page: Int, $perPage: Int, $end: Int) {
    Page(page: $page, perPage: $perPage) {
        pageInfo { total hasNextPage }
        airingSchedules(airingAt_lesser: $end, sort: TIME_DESC) {
            episode
            airingAt
            media {
                id
                idMal
                title { romaji english }
                coverImage { large extraLarge }
                bannerImage
                description(asHtml: false)
                episodes
                status
                isAdult
                format
            }
        }
    }
}
"""

_ALLOWED_FORMATS = {"TV", "MOVIE"}


# --- Internal helpers ---


def _graphql_request(query, variables):
    """Make an AniList GraphQL request."""
    try:
        return services.api_request(
            "anilist",
            "POST",
            base_url,
            params={"query": query, "variables": variables},
        )
    except requests.exceptions.HTTPError as error:
        logger.exception("AniList GraphQL request failed")
        msg = "anilist"
        raise services.ProviderAPIError(msg, error) from error


def _clean_html(text):
    """Strip HTML tags and decode entities from AniList descriptions."""
    if not text:
        return ""
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _anilist_type(media_type):
    """Map Docket media type to AniList MediaType enum."""
    return "MANGA" if media_type == MediaTypes.MANGA.value else "ANIME"


def _format_media(media, media_type):
    """Convert AniList media object to Docket's standard item format."""
    mal_id = media.get("idMal")
    title_obj = media.get("title", {})
    romaji = title_obj.get("romaji") or ""
    english = title_obj.get("english") or ""
    return {
        "media_id": str(mal_id) if mal_id else str(media["id"]),
        "source": Sources.MAL.value,
        "media_type": media_type,
        "title": romaji or english,
        "english_title": english if english != romaji else "",
        "image": (media.get("coverImage") or {}).get("extraLarge")
        or (media.get("coverImage") or {}).get("large")
        or "",
        "backdrop": media.get("bannerImage"),
        "synopsis": _clean_html(media.get("description", "")),
    }


def _formats_for_type(media_type):
    """Return the allowed format list for a media type."""
    if media_type == MediaTypes.MANGA.value:
        return _MANGA_FORMATS
    return _ANIME_FORMATS


def _with_cache(cache_key, ttl, compute_fn):
    """Cache wrapper: return cached value or compute, cache, and return it."""
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    data = compute_fn()
    cache.set(cache_key, data, timeout=ttl)
    return data


def _cached_media_query(query, media_type, page, per_page, cache_prefix, ttl):
    """Execute a cached AniList media query and return paginated results."""
    cache_key = f"anilist_{cache_prefix}_{media_type}_{page}_{per_page}"
    return _with_cache(
        cache_key,
        ttl,
        lambda: _run_media_query(query, media_type, page, per_page),
    )


def _run_media_query(query, media_type, page, per_page):
    """Run a paginated AniList media GraphQL query and format the response."""
    response = _graphql_request(
        query,
        {
            "type": _anilist_type(media_type),
            "page": page,
            "perPage": per_page,
            "formats": _formats_for_type(media_type),
        },
    )
    page_data = response["data"]["Page"]
    page_info = page_data["pageInfo"]
    results = [_format_media(m, media_type) for m in page_data["media"]]
    data = helpers.format_search_response(
        page,
        per_page,
        page_info.get("total", 0),
        results,
    )
    data["has_next_page"] = page_info.get("hasNextPage", False)
    return data


def _extract_schedule_item(entry, seen_ids):
    """Extract a valid anime item from an airing schedule entry, or None."""
    media = entry.get("media")
    if not media or media.get("isAdult"):
        return None
    if media.get("format") not in _ALLOWED_FORMATS:
        return None
    mid = media.get("idMal") or media["id"]
    if mid in seen_ids:
        return None
    seen_ids.add(mid)
    item = _format_media(media, MediaTypes.ANIME.value)
    item["episode"] = entry.get("episode")
    return item


# --- Public API ---


def trending(media_type, page=1, per_page=10):
    """Fetch trending anime/manga sorted by recent activity."""
    return _cached_media_query(
        _TRENDING_QUERY, media_type, page, per_page, "trending", CACHE_TTL_TRENDING
    )


def recently_updated(media_type, page=1, per_page=24):
    """Fetch recently updated anime/manga.

    For anime: uses airing schedule (episodes that recently aired).
    For manga: uses UPDATED_AT_DESC query.
    """
    cache_key = f"anilist_recently_updated_{media_type}_{page}_{per_page}"
    if media_type == MediaTypes.ANIME.value:
        compute = lambda: _recently_aired_anime(page, per_page)  # noqa: E731
    else:
        compute = lambda: _cached_media_query(  # noqa: E731
            _RECENTLY_UPDATED_QUERY,
            media_type,
            page,
            per_page,
            f"recent_manga_{page}",
            CACHE_TTL_RECENT,
        )
    return _with_cache(cache_key, CACHE_TTL_RECENT, compute)


def _recently_aired_anime(page, per_page):
    """Fetch recently aired episodes via airingSchedules TIME_DESC.

    Deduplicates to show each anime once (most recent episode).
    """
    now = int(time.time())
    seen_ids = set()
    results = []
    api_page = (page - 1) * 2 + 1
    max_attempts = 6

    while len(results) < per_page and max_attempts > 0:
        response = _graphql_request(
            _RECENTLY_AIRED_SCHEDULE,
            {"page": api_page, "perPage": 50, "end": now},
        )
        if not _collect_aired_entries_page(response, results, seen_ids, per_page):
            break
        api_page += 1
        max_attempts -= 1

    data = helpers.format_search_response(page, per_page, 5000, results[:per_page])
    data["has_next_page"] = len(results) >= per_page
    return data


def _collect_aired_entries_page(response, results, seen_ids, per_page):
    """Append schedule items from one page. Return False to stop paging."""
    page_data = response["data"]["Page"]
    for entry in page_data.get("airingSchedules", []):
        item = _extract_schedule_item(entry, seen_ids)
        if item:
            results.append(item)
        if len(results) >= per_page:
            return False
    return page_data["pageInfo"].get("hasNextPage", False)


def upcoming(media_type, page=1, per_page=24):
    """Fetch upcoming anime/manga (not yet released, sorted by popularity)."""
    return _cached_media_query(
        _UPCOMING_QUERY, media_type, page, per_page, "upcoming", CACHE_TTL_UPCOMING
    )


def airing_schedule(page=1, per_page=20):
    """Fetch today's anime airing schedule with air times."""
    now = int(time.time())
    day_start = now - (now % 86400)
    day_end = day_start + 86400

    cache_key = f"anilist_schedule_{day_start}_{page}_{per_page}"
    data = cache.get(cache_key)

    if data is None:
        response = _graphql_request(
            _SCHEDULE_QUERY,
            {
                "page": page,
                "perPage": per_page,
                "start": day_start,
                "end": day_end,
            },
        )

        page_data = response["data"]["Page"]
        schedules = page_data.get("airingSchedules", [])

        data = [
            {
                "media_id": str(s["media"].get("idMal") or s["media"]["id"]),
                "source": Sources.MAL.value,
                "media_type": MediaTypes.ANIME.value,
                "title": (
                    s["media"]["title"].get("english")
                    or s["media"]["title"].get("romaji")
                    or ""
                ),
                "image": (s["media"].get("coverImage") or {}).get("large", ""),
                "airing_at": s["airingAt"],
                "episode": s["episode"],
            }
            for s in schedules
            if s.get("media")
        ]
        cache.set(cache_key, data, timeout=CACHE_TTL_SCHEDULE)

    return data
