"""Per-item news fetchers: Jikan (anime/manga), IGDB (game), BGG (boardgame)."""

import logging
from datetime import UTC, datetime

from defusedxml import ElementTree
from django.core.cache import cache

from app.providers.services import session

logger = logging.getLogger(__name__)

PER_ITEM_TTL = 3 * 3600  # 3 hours


def cache_key(media_type, media_id):
    """Return the Redis cache key for a per-item news entry."""
    return f"news_item_{media_type}_{media_id}"


def fetch_item_news(media_type, media_id, limit=5):
    """Fetch and cache per-item news for a supported media type."""
    fetcher = _DISPATCH.get(media_type)
    if fetcher is None:
        return []

    key = cache_key(media_type, media_id)
    cached = cache.get(key)
    if cached is not None:
        return cached

    try:
        articles = fetcher(media_id, limit)
    except Exception:  # noqa: BLE001 — third-party APIs raise diverse errors
        logger.warning(
            "Per-item news fetch failed for %s/%s", media_type, media_id, exc_info=True
        )
        articles = []

    cache.set(key, articles, PER_ITEM_TTL)
    return articles


def _jikan_anime_news(media_id, limit):
    return _jikan_news("anime", media_id, limit)


def _jikan_manga_news(media_id, limit):
    return _jikan_news("manga", media_id, limit)


def _jikan_news(endpoint, media_id, limit):
    """Hit Jikan v4 /{endpoint}/{id}/news and normalise the results."""
    url = f"https://api.jikan.moe/v4/{endpoint}/{media_id}/news"
    resp = session.get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json().get("data", [])[:limit]
    media_type = "anime" if endpoint == "anime" else "manga"
    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "source": "MyAnimeList",
            "summary": item.get("excerpt", ""),
            "image": (item.get("images") or {}).get("jpg", {}).get("image_url"),
            "published_at": _parse_iso(item.get("date")),
            "media_type": media_type,
            "media_id": media_id,
        }
        for item in data
    ]


def _igdb_articles(media_id, limit):
    """Fetch IGDB pulses for a game (best-effort; deprecated endpoint may 404)."""
    from app.providers import igdb  # noqa: PLC0415

    query = (
        "fields title,url,summary,image,published_at,website.url; "
        f"where games = ({media_id}); "
        "sort published_at desc; "
        f"limit {limit};"
    )
    try:
        response = igdb._igdb_request(f"{igdb.base_url}/pulses", query)
    except Exception:  # noqa: BLE001 — IGDB raises HTTP, auth, and parse errors
        logger.debug("IGDB pulses fetch failed for game %s", media_id, exc_info=True)
        return []

    return [
        {
            "title": item.get("title", ""),
            "url": item.get("url") or _website_url(item),
            "source": "IGDB",
            "summary": item.get("summary", ""),
            "image": _igdb_image_url(item.get("image")),
            "published_at": _parse_unix(item.get("published_at")),
            "media_type": "game",
            "media_id": media_id,
        }
        for item in response or []
    ]


def _bgg_forum_news(media_id, limit):
    """Pull recent BGG forum threads for a board game and treat as news entries."""
    list_url = f"https://boardgamegeek.com/xmlapi2/forumlist?id={media_id}&type=thing"
    resp = session.get(list_url, timeout=10)
    resp.raise_for_status()
    forum_root = ElementTree.fromstring(resp.content)
    forums = list(forum_root.findall("forum"))[:2]
    articles = []
    for forum in forums:
        articles.extend(_bgg_forum_threads(forum, media_id, limit))
        if len(articles) >= limit:
            break
    return articles[:limit]


def _bgg_forum_threads(forum, media_id, limit):
    """Fetch threads for one BGG forum and return news-shaped articles."""
    fid = forum.get("id")
    if not fid:
        return []
    thread_resp = session.get(
        f"https://boardgamegeek.com/xmlapi2/forum?id={fid}",
        timeout=10,
    )
    thread_resp.raise_for_status()
    thread_root = ElementTree.fromstring(thread_resp.content)
    threads_node = thread_root.find("threads")
    if threads_node is None:
        return []
    return [
        {
            "title": thread.get("subject", ""),
            "url": f"https://boardgamegeek.com/thread/{thread.get('id')}",
            "source": "BoardGameGeek",
            "summary": "",
            "image": None,
            "published_at": _parse_iso(thread.get("postdate")),
            "media_type": "boardgame",
            "media_id": media_id,
        }
        for thread in list(threads_node)[:limit]
    ]


def _safe_parse(value, parser):
    """Run parser(value) defensively, returning None on falsy input or errors."""
    if not value:
        return None
    try:
        return parser(value)
    except (TypeError, ValueError, AttributeError):
        return None


def _parse_iso(value):
    return _safe_parse(value, datetime.fromisoformat)


def _parse_unix(value):
    return _safe_parse(value, lambda v: datetime.fromtimestamp(int(v), tz=UTC))


def _igdb_image_url(image_field):
    if not image_field:
        return None
    if isinstance(image_field, dict):
        image_id = image_field.get("image_id")
    else:
        image_id = image_field
    if not image_id:
        return None
    return f"https://images.igdb.com/igdb/image/upload/t_thumb/{image_id}.jpg"


def _website_url(item):
    website = item.get("website") or {}
    return website.get("url", "") if isinstance(website, dict) else ""


_DISPATCH = {
    "anime": _jikan_anime_news,
    "manga": _jikan_manga_news,
    "game": _igdb_articles,
    "boardgame": _bgg_forum_news,
}
