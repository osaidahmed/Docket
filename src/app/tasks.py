"""Celery tasks for the app."""

import logging
import time

from celery import shared_task

# Register nested task modules with Celery's autodiscover (which only scans
# `<app>/tasks.py`, not nested submodules).
from app.link_providers import tasks as _link_provider_tasks  # noqa: F401

logger = logging.getLogger(__name__)


@shared_task(name="Refresh anime relationships")
def refresh_anime_relationships_task(user_id):
    """Fetch related anime data from MAL to populate grouping relationships."""
    from django.contrib.auth import get_user_model  # noqa: PLC0415

    from app.models import Anime, ItemRelationship, Sources  # noqa: PLC0415
    from app.providers import mal  # noqa: PLC0415

    user = get_user_model().objects.get(id=user_id)
    tracked = (
        Anime.objects.filter(user=user)
        .select_related("item")
        .filter(item__source=Sources.MAL.value)
    )

    items_with_rels = set(
        ItemRelationship.objects.values_list("from_item_id", flat=True)
    )

    for anime in tracked:
        if anime.item_id in items_with_rels:
            continue
        try:
            data = mal.anime(anime.item.media_id)
            related = data.get("related", {}).get("related_anime", [])
            if related:
                mal._save_anime_relationships(anime.item.media_id, related)
            time.sleep(0.5)
        except Exception:
            logger.debug(
                "Skipping relationship fetch for anime %s",
                anime.item.media_id,
            )


@shared_task(name="Compute recommendations")
def compute_recommendations_task(user_id, media_type):
    """Compute and cache recommendations for a user's media type."""
    from app.services.recommendations import compute_recommendations  # noqa: PLC0415

    try:
        compute_recommendations(user_id, media_type)
    except Exception:
        logger.exception(
            "Failed to compute recommendations for user=%s type=%s",
            user_id,
            media_type,
        )
        from django.conf import settings  # noqa: PLC0415
        from django.core.cache import cache  # noqa: PLC0415

        from app.services.recommendations import (  # noqa: PLC0415
            get_cache_key,
            get_progress_key,
        )

        cache.set(
            get_cache_key(user_id, media_type),
            {"active": [], "full": [], "genres": []},
            settings.CACHE_TIMEOUT,
        )
        cache.delete(get_progress_key(user_id, media_type))
