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

        from app.services.recommendations import get_cache_key  # noqa: PLC0415

        cache.set(
            get_cache_key(user_id, media_type),
            {"active": [], "full": []},
            settings.CACHE_TIMEOUT,
        )
