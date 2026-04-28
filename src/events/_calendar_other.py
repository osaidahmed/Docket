"""Per-item calendar processing for non-TV/anime/comic media types."""

import logging

from app import config
from app.models import MediaTypes, Sources
from app.providers import services
from events._calendar_dates import date_parser
from events.calendar import SENTINEL_DATETIME
from events.models import Event

logger = logging.getLogger(__name__)


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

    date_key = config.get_date_key(item.media_type)
    content_number = metadata["max_progress"]

    content_datetime = _parse_content_datetime(
        metadata["details"],
        date_key,
        item,
    )

    if content_datetime is not None:
        if item.media_type == MediaTypes.MOVIE.value:
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
