"""Celery tasks for the app."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


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
