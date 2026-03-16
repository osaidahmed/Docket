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
query ($type: MediaType, $page: Int, $perPage: Int) {{
    Page(page: $page, perPage: $perPage) {{
        pageInfo {{ total currentPage lastPage hasNextPage perPage }}
        media(type: $type, sort: TRENDING_DESC, isAdult: false,
              format_in: [TV, MOVIE]) {{
            {_MEDIA_FIELDS}
        }}
    }}
}}
"""

_RECENTLY_UPDATED_QUERY = f"""
query ($type: MediaType, $page: Int, $perPage: Int) {{
    Page(page: $page, perPage: $perPage) {{
        pageInfo {{ total currentPage lastPage hasNextPage perPage }}
        media(type: $type, sort: UPDATED_AT_DESC, isAdult: false,
              format_in: [TV, MOVIE],
              status_in: [RELEASING, FINISHED]) {{
            {_MEDIA_FIELDS}
        }}
    }}
}}
"""

_UPCOMING_QUERY = f"""
query ($type: MediaType, $page: Int, $perPage: Int) {{
    Page(page: $page, perPage: $perPage) {{
        pageInfo {{ total currentPage lastPage hasNextPage perPage }}
        media(type: $type, sort: POPULARITY_DESC, status: NOT_YET_RELEASED,
              isAdult: false, format_in: [TV, MOVIE]) {{
            {_MEDIA_FIELDS}
        }}
    }}
}}
"""

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


def trending(media_type, page=1, per_page=10):
    """Fetch trending anime/manga sorted by recent activity."""
    cache_key = f"anilist_trending_{media_type}_{page}_{per_page}"
    data = cache.get(cache_key)

    if data is None:
        response = _graphql_request(
            _TRENDING_QUERY,
            {"type": _anilist_type(media_type), "page": page, "perPage": per_page},
        )

        page_data = response["data"]["Page"]
        page_info = page_data["pageInfo"]
        results = [_format_media(m, media_type) for m in page_data["media"]]

        data = helpers.format_search_response(
            page, per_page, page_info.get("total", 0), results
        )
        cache.set(cache_key, data, timeout=CACHE_TTL_TRENDING)

    return data


def recently_updated(media_type, page=1, per_page=24):
    """Fetch recently updated anime/manga.

    For anime: uses airing schedule (episodes that aired in last 48h).
    For manga: falls back to UPDATED_AT_DESC since manga has no schedule.
    """
    cache_key = f"anilist_recently_updated_{media_type}_{page}_{per_page}"
    data = cache.get(cache_key)

    if data is None:
        if media_type == MediaTypes.ANIME.value:
            data = _recently_aired_anime(page, per_page)
        else:
            data = _recently_updated_manga(media_type, page, per_page)
        cache.set(cache_key, data, timeout=CACHE_TTL_RECENT)

    return data


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


def _recently_aired_anime(page, per_page):
    """Fetch recently aired episodes via airingSchedules TIME_DESC.

    Per-episode feed that is truly infinite. Deduplicates to show
    each anime once (most recent episode), filters to TV/Movie only.
    """
    cache_key = f"anilist_recent_anime_{page}_{per_page}"
    data = cache.get(cache_key)

    if data is None:
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
            page_data = response["data"]["Page"]
            has_next = page_data["pageInfo"].get("hasNextPage", False)

            for s in page_data.get("airingSchedules", []):
                media = s.get("media")
                if not media or media.get("isAdult"):
                    continue
                if media.get("format") not in _ALLOWED_FORMATS:
                    continue
                mid = media.get("idMal") or media["id"]
                if mid in seen_ids:
                    continue
                seen_ids.add(mid)
                item = _format_media(media, MediaTypes.ANIME.value)
                item["episode"] = s.get("episode")
                results.append(item)
                if len(results) >= per_page:
                    break

            if not has_next:
                break
            api_page += 1
            max_attempts -= 1

        data = helpers.format_search_response(
            page, per_page, 5000, results[:per_page]
        )
        data["has_next_page"] = len(results) >= per_page
        cache.set(cache_key, data, timeout=CACHE_TTL_RECENT)

    return data


def _recently_updated_manga(media_type, page, per_page):
    """Fetch recently updated manga via UPDATED_AT_DESC."""
    response = _graphql_request(
        _RECENTLY_UPDATED_QUERY,
        {
            "type": _anilist_type(media_type),
            "page": page,
            "perPage": per_page,
        },
    )

    page_data = response["data"]["Page"]
    page_info = page_data["pageInfo"]
    results = [_format_media(m, media_type) for m in page_data["media"]]

    data = helpers.format_search_response(
        page, per_page, page_info.get("total", 0), results
    )
    data["has_next_page"] = page_info.get("hasNextPage", False)
    return data


def upcoming(media_type, page=1, per_page=24):
    """Fetch upcoming anime/manga (not yet released, sorted by popularity)."""
    cache_key = f"anilist_upcoming_{media_type}_{page}_{per_page}"
    data = cache.get(cache_key)

    if data is None:
        response = _graphql_request(
            _UPCOMING_QUERY,
            {"type": _anilist_type(media_type), "page": page, "perPage": per_page},
        )

        page_data = response["data"]["Page"]
        page_info = page_data["pageInfo"]
        results = [_format_media(m, media_type) for m in page_data["media"]]

        data = helpers.format_search_response(
            page, per_page, page_info.get("total", 0), results
        )
        data["has_next_page"] = page_info.get("hasNextPage", False)
        cache.set(cache_key, data, timeout=CACHE_TTL_UPCOMING)

    return data


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
                "title": (s["media"]["title"].get("english")
                          or s["media"]["title"].get("romaji") or ""),
                "image": (s["media"].get("coverImage") or {}).get("large", ""),
                "airing_at": s["airingAt"],
                "episode": s["episode"],
            }
            for s in schedules
            if s.get("media")
        ]
        cache.set(cache_key, data, timeout=CACHE_TTL_SCHEDULE)

    return data
