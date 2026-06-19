"""Celery tasks for warming the news aggregator caches."""

import logging
import random
from concurrent.futures import ThreadPoolExecutor

from celery import shared_task
from django.apps import apps
from django.core.cache import cache

from app._news_config import (
    NEWS_SOURCES,
    PER_ITEM_NEWS_SUPPORT,
    get_sample_size,
)

logger = logging.getLogger(__name__)

SELECTION_TTL = 86400  # 24 hours
# parallel I/O-bound fetches; the rate limiter still serialises per host
FETCH_WORKERS = 6


def _fetch_all_parallel(jobs, fetch_fn, label_fn):
    """Run fetch_fn over each job in parallel, isolating and logging failures."""

    def _run(job):
        try:
            fetch_fn(job)
        except Exception:
            logger.exception("Failed to warm news: %s", label_fn(job))

    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        list(pool.map(_run, jobs))


def selection_cache_key(media_type):
    """Return the Redis cache key for the daily per-type item selection."""
    return f"news_selection_{media_type}"


@shared_task(name="Warm industry news")
def warm_industry_news():
    """Fetch all unique RSS sources in parallel and populate their caches."""
    from app.providers.news_rss import fetch_source  # noqa: PLC0415

    seen = set()
    jobs = []
    for media_type, sources in NEWS_SOURCES.items():
        for src in sources:
            if src["slug"] in seen:
                continue
            seen.add(src["slug"])
            jobs.append((src, media_type))

    _fetch_all_parallel(
        jobs,
        lambda job: fetch_source(job[0], job[1]),
        lambda job: job[0]["slug"],
    )


@shared_task(name="Warm library news selection")
def warm_library_news_selection():
    """Sample tracked items per supported type and cache the selection IDs."""
    for media_type in PER_ITEM_NEWS_SUPPORT:
        try:
            ids = _collect_candidate_ids(media_type)
        except Exception:
            logger.exception("Failed to collect candidates for %s", media_type)
            continue
        sample = random.sample(ids, min(get_sample_size(media_type), len(ids)))
        cache.set(selection_cache_key(media_type), sample, SELECTION_TTL)


@shared_task(name="Warm library news content")
def warm_library_news_content():
    """For each cached item selection, fetch and cache per-item news in parallel."""
    from app.providers.news_per_item import fetch_item_news  # noqa: PLC0415

    jobs = []
    for media_type in PER_ITEM_NEWS_SUPPORT:
        selection = cache.get(selection_cache_key(media_type)) or []
        jobs.extend((media_type, str(media_id)) for media_id in selection)

    _fetch_all_parallel(
        jobs,
        lambda job: fetch_item_news(job[0], job[1]),
        lambda job: f"{job[0]}/{job[1]}",
    )


def _collect_candidate_ids(media_type):
    """Return the distinct media_ids for tracked items eligible for spotlighting."""
    from app.models import Status  # noqa: PLC0415

    model = apps.get_model(app_label="app", model_name=media_type)
    return list(
        model.objects.filter(
            status__in=[Status.PLANNING.value, Status.IN_PROGRESS.value],
        )
        .select_related("item")
        .values_list("item__media_id", flat=True)
        .distinct()
    )
