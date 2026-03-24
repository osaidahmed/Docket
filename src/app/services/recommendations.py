"""Frequency-based recommendation computation for media list pages."""

import logging
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.apps import apps
from django.conf import settings
from django.core.cache import cache

from app.models import MediaTypes, Status
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


def _add_title_variants(title_set, title):
    """Add normalized title and base title (before first colon) to the set."""
    norm = title.strip().lower()
    title_set.add(norm)
    if ":" in norm:
        title_set.add(norm.split(":")[0].strip())


def _matches_cross_media(title, cross_media_titles):
    """Check if a title matches any cross-media title (exact or base)."""
    if not cross_media_titles:
        return False
    if title in cross_media_titles:
        return True
    if ":" in title:
        return title.split(":")[0].strip() in cross_media_titles
    return False


def compute_recommendations(user_id, media_type):
    """Build frequency-ranked recommendations from all tracked items."""
    progress_key = get_progress_key(user_id, media_type)
    model = apps.get_model(app_label="app", model_name=media_type)
    all_items = list(model.objects.filter(user_id=user_id).select_related("item"))

    processable = [m for m in all_items if m.status != Status.DROPPED.value]
    cache.set(
        progress_key,
        {"current": 0, "total": len(processable)},
        PROGRESS_TIMEOUT,
    )

    freq_data = _collect_frequencies(processable, progress_key)
    tracked_keys = {(str(m.item.media_id), m.item.source) for m in all_items}
    cross_media_titles = _build_cross_media_titles(user_id, media_type)

    deduper = _Deduplicator(tracked_keys, freq_data.rec_details, cross_media_titles)
    active_recs = deduper.select(
        freq_data.active_freq.most_common(), MAX_RECOMMENDATIONS
    )
    full_recs = deduper.select(freq_data.full_freq.most_common(), MAX_RECOMMENDATIONS)
    genre_sections = _build_genre_sections(
        freq_data.genre_freq,
        freq_data.genre_recs,
        deduper,
    )

    result = {"active": active_recs, "full": full_recs, "genres": genre_sections}
    cache.set(get_cache_key(user_id, media_type), result, settings.CACHE_TIMEOUT)
    cache.delete(progress_key)
    return result


class _FrequencyData:
    __slots__ = ("active_freq", "full_freq", "genre_freq", "genre_recs", "rec_details")

    def __init__(self):
        self.active_freq = Counter()
        self.full_freq = Counter()
        self.rec_details = {}
        self.genre_freq = Counter()
        self.genre_recs = defaultdict(Counter)


_ACTIVE_STATUSES = {Status.IN_PROGRESS.value, Status.PLANNING.value}


PROGRESS_BATCH = 10
MAX_WORKERS = 5


def _fetch_one(media):
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
        return media, None
    return media, metadata


def _process_item(data, media, metadata):
    genres = metadata.get("genres") or []
    for genre in genres:
        data.genre_freq[genre] += 1

    is_active = media.status in _ACTIVE_STATUSES
    for rec in metadata.get("related", {}).get("recommendations", []):
        key = (str(rec["media_id"]), rec["source"])
        data.rec_details[key] = rec
        data.full_freq[key] += 1
        if is_active:
            data.active_freq[key] += 1
        for genre in genres:
            data.genre_recs[genre][key] += 1


def _collect_frequencies(processable, progress_key):
    data = _FrequencyData()
    total = len(processable)
    completed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_fetch_one, m): m for m in processable}
        for future in as_completed(futures):
            media, metadata = future.result()
            completed += 1

            if metadata:
                _process_item(data, media, metadata)

            if completed % PROGRESS_BATCH == 0 or completed == total:
                cache.set(
                    progress_key,
                    {"current": completed, "total": total},
                    PROGRESS_TIMEOUT,
                )

    return data


def _build_cross_media_titles(user_id, media_type):
    if media_type != MediaTypes.MANGA.value:
        return set()
    titles = set()
    anime_model = apps.get_model(app_label="app", model_name=MediaTypes.ANIME.value)
    for m in anime_model.objects.filter(user_id=user_id).select_related("item"):
        _add_title_variants(titles, m.item.title)
        if m.item.english_title:
            _add_title_variants(titles, m.item.english_title)
    return titles


class _Deduplicator:
    def __init__(self, tracked_keys, rec_details, cross_media_titles):
        self._shown_keys = set(tracked_keys)
        self._seen_titles = set()
        self._rec_details = rec_details
        self._cross_media_titles = cross_media_titles

    def select(self, candidates, limit):
        result = []
        for key, _ in candidates:
            if key in self._shown_keys:
                continue
            rec = self._rec_details[key]
            norm_title = rec.get("title", "").strip().lower()
            if norm_title in self._seen_titles:
                continue
            if _matches_cross_media(norm_title, self._cross_media_titles):
                continue
            self._seen_titles.add(norm_title)
            self._shown_keys.add(key)
            result.append(rec)
            if len(result) >= limit:
                break
        return result


def _build_genre_sections(genre_freq, genre_recs, deduper):
    sorted_genres = sorted(
        genre_freq,
        key=lambda g: (-genre_freq[g], -sum(genre_recs[g].values()), g),
    )
    sections = []
    for genre in sorted_genres:
        if len(sections) >= MAX_GENRE_SECTIONS:
            break
        recs = deduper.select(genre_recs[genre].most_common(), MAX_GENRE_RECS)
        if len(recs) >= MIN_GENRE_RECS:
            sections.append({"name": genre, "recs": recs})
    return sections
