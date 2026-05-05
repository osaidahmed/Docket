"""Explore-page configuration helpers (airing/upcoming/category lookups)."""

from app._media_type_config import (
    AIRING_CATEGORIES,
    ANNOUNCED_STATUSES,
    MEDIA_TYPE_CONFIG,
    MONTH_TO_SEASON,
    SEASON_START_MONTH,
)
from app._types import is_anime_media


def is_announced_media(metadata):
    """Return True if the media's status indicates it's not yet released."""
    status = metadata.get("details", {}).get("status", "")
    return status in ANNOUNCED_STATUSES


def get_current_anime_season():
    """Return the current (year, season) tuple for seasonal anime."""
    from django.utils import timezone  # noqa: PLC0415

    now = timezone.now()
    return now.year, MONTH_TO_SEASON[now.month]


def is_airing_category(category):
    """Return whether the explore category represents currently airing media."""
    return category in AIRING_CATEGORIES


def is_upcoming_category(media_type, category, year=None, season_name=None):
    """Return whether the explore category represents upcoming/unreleased media."""
    if category in ("upcoming", "anticipated"):
        return True
    if (
        category == "seasonal"
        and is_anime_media(media_type)
        and year is not None
        and season_name is not None
    ):
        from datetime import date  # noqa: PLC0415

        from django.utils import timezone  # noqa: PLC0415

        start_month = SEASON_START_MONTH.get(season_name)
        if start_month:
            season_start = date(int(year), start_month, 1)
            return timezone.now().date() < season_start
    return False


def get_explore_categories(media_type):
    """Return the browse categories for a media type, or None if not explorable."""
    cfg = MEDIA_TYPE_CONFIG.get(media_type)
    return cfg.get("explore_categories") if cfg else None


def get_explore_filters(media_type):
    """Return the filter definitions for a media type, or None if no filters."""
    cfg = MEDIA_TYPE_CONFIG.get(media_type)
    return cfg.get("explore_filters") if cfg else None


def has_explore_filters(media_type):
    """Return whether the media type supports explore filters."""
    return get_explore_filters(media_type) is not None
