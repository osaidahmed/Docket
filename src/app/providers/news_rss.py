"""RSS article fetcher for the news aggregator."""

import logging
from datetime import UTC, datetime

import feedparser
from django.core.cache import cache

from app._news_config import get_news_sources
from app.providers.services import session

logger = logging.getLogger(__name__)

INDUSTRY_TTL = 3600  # 1 hour


def cache_key(source_slug):
    """Return the Redis cache key for a given RSS source slug."""
    return f"news_rss_{source_slug}"


def fetch_source(source_cfg, media_type, limit=10):
    """Fetch articles for an RSS source, write to cache, and return them."""
    key = cache_key(source_cfg["slug"])
    try:
        resp = session.get(source_cfg["rss_url"], timeout=10)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        articles = [
            _parse_entry(e, source_cfg["label"], media_type)
            for e in feed.entries[:limit]
        ]
    except Exception:  # noqa: BLE001 — RSS sources raise diverse network/parse errors
        logger.warning("RSS fetch failed for %s", source_cfg["slug"], exc_info=True)
        articles = []
    cache.set(key, articles, INDUSTRY_TTL)
    return articles


def get_industry_articles(media_type, limit=10):
    """Read cached articles across all sources for a media type."""
    articles = []
    for src in get_news_sources(media_type):
        articles.extend(cache.get(cache_key(src["slug"])) or [])
    return articles[:limit]


def _parse_entry(entry, source_label, media_type):
    """Normalise a feedparser entry into the article dict shape."""
    return {
        "title": entry.get("title", ""),
        "url": entry.get("link", ""),
        "source": source_label,
        "summary": entry.get("summary", ""),
        "image": _extract_image(entry),
        "published_at": _extract_published(entry),
        "media_type": media_type,
        "media_id": None,
    }


def _extract_image(entry):
    """Pick the best available image from a feedparser entry."""
    if entry.get("media_content"):
        return entry["media_content"][0].get("url")
    if entry.get("media_thumbnail"):
        return entry["media_thumbnail"][0].get("url")
    return None


def _extract_published(entry):
    """Return a timezone-aware datetime for the entry's publish time, or None."""
    published_raw = entry.get("published_parsed") or entry.get("updated_parsed")
    if not published_raw:
        return None
    return datetime(*published_raw[:6], tzinfo=UTC)
