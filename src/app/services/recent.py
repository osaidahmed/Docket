"""Recently viewed items — Redis-backed tracking for search bar pre-populate."""

import json

from django.conf import settings
from redis import Redis

from app.providers.services import redis_pool

MAX_ENTRIES = 20

redis_client = Redis(connection_pool=redis_pool)


def _key(user_id):
    prefix = getattr(settings, "REDIS_PREFIX", None)
    base = f"recent:{user_id}"
    return f"{prefix}:{base}" if prefix else base


def _item_key(data):
    return f"{data['media_type']}:{data['media_id']}:{data['source']}"


def track_view(user_id, item_data):
    """Record a detail page view. Deduplicates and caps the list."""
    key = _key(user_id)
    target = _item_key(item_data)

    existing = redis_client.lrange(key, 0, -1)
    for entry in existing:
        data = json.loads(entry)
        if _item_key(data) == target:
            redis_client.lrem(key, 1, entry)
            break

    redis_client.lpush(key, json.dumps(item_data))
    redis_client.ltrim(key, 0, MAX_ENTRIES - 1)


def get_recent(user_id, media_type_filter=None, limit=5):
    """Return recently viewed items, optionally filtered by media type."""
    key = _key(user_id)
    entries = redis_client.lrange(key, 0, -1)

    results = []
    for entry in entries:
        data = json.loads(entry)
        if media_type_filter and data["media_type"] != media_type_filter:
            continue
        results.append(data)
        if len(results) >= limit:
            break
    return results
