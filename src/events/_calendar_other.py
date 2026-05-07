"""Per-item calendar processing for non-TV/anime/comic media types."""

import logging

from app import config
from app._types import is_movie_media
from app.models import Sources
from app.providers import services
from events._calendar_dates import date_parser
from events.calendar import SENTINEL_DATETIME
from events.models import Event

logger = logging.getLogger(__name__)

_STARTED_STATUSES = frozenset({"Airing", "Publishing"})


def process_other(item, events_bulk):
    """Process other types of items and add events to the event list."""
    logger.info("Fetching releases for %s", item)
    try:
        metadata = services.get_media_metadata(
            item.media_type,
            item.media_id,
            item.source,
        )
    except services.ProviderAPIError:
        logger.warning("Failed to fetch metadata for %s", item)
        return

    if metadata is None:
        return

    details = metadata["details"]
    date_key = config.get_date_key(item.media_type)
    content_datetime = _parse_content_datetime(details, date_key, item)

    if content_datetime == SENTINEL_DATETIME and _has_started(details):
        Event.objects.filter(item=item, datetime=SENTINEL_DATETIME).delete()
        return

    _append_event(item, metadata, content_datetime, events_bulk)


def _append_event(item, metadata, content_datetime, events_bulk):
    """Append an Event to events_bulk based on the resolved datetime."""
    content_number = metadata["max_progress"]
    if content_datetime is not None:
        if is_movie_media(item.media_type):
            content_number = None
        events_bulk.append(
            Event(
                item=item,
                content_number=content_number,
                datetime=content_datetime,
            ),
        )
        return

    if item.source == Sources.MANGAUPDATES.value and content_number:
        events_bulk.append(
            Event(
                item=item,
                content_number=content_number,
                datetime=SENTINEL_DATETIME,
            ),
        )


def _has_started(details):
    """Return True if metadata status indicates release has begun."""
    return details.get("status") in _STARTED_STATUSES


def _parse_content_datetime(details, date_key, item):
    """Parse datetime from metadata details.

    Returns datetime, SENTINEL_DATETIME, or None if not applicable.
    """
    if date_key not in details:
        return None

    date_value = details[date_key]
    if not date_value:
        return SENTINEL_DATETIME

    try:
        return date_parser(date_value)
    except ValueError:
        logger.warning("Invalid date for %s: %s", item, date_value)
        return None
