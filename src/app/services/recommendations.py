"""Frequency-based recommendation computation for media list pages."""

import logging
from collections import Counter, defaultdict

from django.apps import apps
from django.conf import settings
from django.core.cache import cache

from app.models import Status
from app.providers import services as provider_services

logger = logging.getLogger(__name__)

MAX_RECOMMENDATIONS = 20
MAX_GENRE_SECTIONS = 5
MAX_GENRE_RECS = 10
MIN_GENRE_RECS = 3
PROGRESS_TIMEOUT = 600


def get_cache_key(user_id, media_type):
    """Return the cache key for a user's recommendations of a media type."""
    return f"recommendations:{user_id}:{media_type}"


def get_progress_key(user_id, media_type):
    """Return the cache key for recommendation computation progress."""
    return f"recommendations_progress:{user_id}:{media_type}"


def get_progress(user_id, media_type):
    """Return current computation progress, or None if not running."""
    return cache.get(get_progress_key(user_id, media_type))


def compute_recommendations(user_id, media_type):
    """Build frequency-ranked recommendations from all tracked items.

    Groups results into "active" (from Planning/In Progress sources)
    and "full" (from all non-Dropped sources, excluding active results).
    """
    progress_key = get_progress_key(user_id, media_type)
    model = apps.get_model(app_label="app", model_name=media_type)
    all_items = list(model.objects.filter(user_id=user_id).select_related("item"))

    processable = [m for m in all_items if m.status != Status.DROPPED.value]
    total = len(processable)
    cache.set(progress_key, {"current": 0, "total": total}, PROGRESS_TIMEOUT)

    tracked_keys = {(str(m.item.media_id), m.item.source) for m in all_items}

    active_statuses = {Status.IN_PROGRESS.value, Status.PLANNING.value}
    active_freq = Counter()
    full_freq = Counter()
    rec_details = {}
    genre_freq = Counter()
    genre_recs = defaultdict(Counter)

    for i, media in enumerate(processable):
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
            cache.set(
                progress_key, {"current": i + 1, "total": total}, PROGRESS_TIMEOUT
            )
            continue

        genres = metadata.get("genres") or []
        for genre in genres:
            genre_freq[genre] += 1

        recs = metadata.get("related", {}).get("recommendations", [])
        for rec in recs:
            key = (str(rec["media_id"]), rec["source"])
            rec_details[key] = rec
            full_freq[key] += 1
            if media.status in active_statuses:
                active_freq[key] += 1
            for genre in genres:
                genre_recs[genre][key] += 1

        cache.set(
            progress_key, {"current": i + 1, "total": total}, PROGRESS_TIMEOUT
        )

    seen_titles = set()

    def _dedup(candidates, limit):
        result = []
        for key, _ in candidates:
            if key in tracked_keys or key in shown_keys:
                continue
            rec = rec_details[key]
            norm_title = rec.get("title", "").strip().lower()
            if norm_title in seen_titles:
                continue
            seen_titles.add(norm_title)
            shown_keys.add(key)
            result.append(rec)
            if len(result) >= limit:
                break
        return result

    shown_keys = set(tracked_keys)
    active_recs = _dedup(active_freq.most_common(), MAX_RECOMMENDATIONS)
    full_recs = _dedup(full_freq.most_common(), MAX_RECOMMENDATIONS)

    sorted_genres = sorted(
        genre_freq,
        key=lambda g: (-genre_freq[g], -sum(genre_recs[g].values()), g),
    )
    genre_sections = []
    for genre in sorted_genres:
        if len(genre_sections) >= MAX_GENRE_SECTIONS:
            break
        recs = _dedup(genre_recs[genre].most_common(), MAX_GENRE_RECS)
        if len(recs) >= MIN_GENRE_RECS:
            genre_sections.append({"name": genre, "recs": recs})

    result = {"active": active_recs, "full": full_recs, "genres": genre_sections}
    cache.set(get_cache_key(user_id, media_type), result, settings.CACHE_TIMEOUT)
    cache.delete(progress_key)
    return result
