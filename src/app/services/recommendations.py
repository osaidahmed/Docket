"""Frequency-based recommendation computation for media list pages."""

import logging
from collections import Counter

from django.apps import apps
from django.conf import settings
from django.core.cache import cache

from app.models import Status
from app.providers import services as provider_services

logger = logging.getLogger(__name__)

MAX_RECOMMENDATIONS = 20


def get_cache_key(user_id, media_type):
    """Return the cache key for a user's recommendations of a media type."""
    return f"recommendations:{user_id}:{media_type}"


def compute_recommendations(user_id, media_type):
    """Build frequency-ranked recommendations from all tracked items.

    Groups results into "active" (from Planning/In Progress sources)
    and "full" (from all non-Dropped sources, excluding active results).
    """
    model = apps.get_model(app_label="app", model_name=media_type)
    tracked = (
        model.objects.filter(user_id=user_id)
        .exclude(status=Status.DROPPED.value)
        .select_related("item")
    )

    active_statuses = {Status.IN_PROGRESS.value, Status.PLANNING.value}
    active_freq = Counter()
    full_freq = Counter()
    rec_details = {}
    tracked_keys = set()

    for media in tracked:
        tracked_keys.add((str(media.item.media_id), media.item.source))
        try:
            metadata = provider_services.get_media_metadata(
                media.item.media_type,
                media.item.media_id,
                media.item.source,
            )
        except Exception:  # noqa: BLE001
            logger.debug(
                "Failed to fetch metadata for %s/%s",
                media.item.media_type,
                media.item.media_id,
            )
            continue

        recs = metadata.get("related", {}).get("recommendations", [])
        for rec in recs:
            key = (str(rec["media_id"]), rec["source"])
            rec_details[key] = rec
            full_freq[key] += 1
            if media.status in active_statuses:
                active_freq[key] += 1

    active_recs = [
        rec_details[key]
        for key, _ in active_freq.most_common()
        if key not in tracked_keys
    ][:MAX_RECOMMENDATIONS]

    active_keys = {(str(r["media_id"]), r["source"]) for r in active_recs}

    full_recs = [
        rec_details[key]
        for key, _ in full_freq.most_common()
        if key not in tracked_keys and key not in active_keys
    ][:MAX_RECOMMENDATIONS]

    result = {"active": active_recs, "full": full_recs}
    cache.set(get_cache_key(user_id, media_type), result, settings.CACHE_TIMEOUT)
    return result
