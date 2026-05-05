import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from django.db.models import Exists, OuterRef, Q, Subquery
from django.utils import timezone
from simple_history.utils import bulk_update_with_history

from app._types import is_season_media
from app.models import TV, Item, MediaTypes, Sources, Status
from events.models import Event

logger = logging.getLogger(__name__)

SENTINEL_DATETIME = datetime.min.replace(tzinfo=ZoneInfo("UTC"))


def save_events(events_bulk):
    """Save events in bulk with proper conflict handling."""
    items_updated = set()

    existing_events = Event.objects.filter(
        item__in=[e.item for e in events_bulk],
    ).select_related("item")

    existing_with_content = {
        (event.item_id, event.content_number): event
        for event in existing_events
        if event.content_number is not None
    }
    existing_without_content = {
        event.item_id: event
        for event in existing_events
        if event.content_number is None
    }

    to_create = []
    to_update = []

    for event in events_bulk:
        if event.item not in items_updated:
            items_updated.add(event.item)

        existing = _find_existing_event(
            event,
            existing_with_content,
            existing_without_content,
        )
        if existing:
            existing.datetime = event.datetime
            to_update.append(existing)
        else:
            to_create.append(event)

    if to_create:
        Event.objects.bulk_create(to_create)
    if to_update:
        Event.objects.bulk_update(to_update, ["datetime"])

    logger.info(
        "Successfully processed %d events (%d created, %d updated)",
        len(events_bulk),
        len(to_create),
        len(to_update),
    )

    return items_updated


def _find_existing_event(event, with_content, without_content):
    if event.content_number is not None:
        return with_content.get((event.item_id, event.content_number))
    return without_content.get(event.item_id)


def generate_final_message(items_to_process, items_updated):
    """Generate the final message summarizing the results."""
    processed_details = "\n".join(
        f"  - {item} ({item.get_media_type_display()})" for item in items_to_process
    )

    if items_updated:
        success_details = "\n".join(
            f"  - {item} ({item.get_media_type_display()})" for item in items_updated
        )
        return (
            f"Processed {len(items_to_process)} items:\n{processed_details}\n\n"
            f"Releases updated for {len(items_updated)} items:\n{success_details}"
        )

    return (
        f"Processed {len(items_to_process)} items:\n{processed_details}\n\n"
        f"No releases have been updated."
    )


def auto_move_completed_to_planning(events_bulk):
    """Auto-move Completed TV shows to Planning when new future events appear."""
    current_time = timezone.now()

    media_ids_with_future = {
        event.item.media_id
        for event in events_bulk
        if is_season_media(event.item.media_type) and event.datetime > current_time
    }

    if not media_ids_with_future:
        return

    completed_tvs = list(
        TV.objects.filter(
            item__media_id__in=media_ids_with_future,
            status=Status.COMPLETED.value,
        )
    )

    if not completed_tvs:
        return

    for tv in completed_tvs:
        tv.status = Status.PLANNING.value

    bulk_update_with_history(completed_tvs, TV, fields=["status"])
    logger.info(
        "Auto-moved %d Completed TV shows to Planning: %s",
        len(completed_tvs),
        ", ".join(str(tv) for tv in completed_tvs),
    )


def cleanup_invalid_events(events_bulk):
    """Remove events that are no longer valid based on updated items."""
    processed_items = {}

    for event in events_bulk:
        if event.content_number is not None:
            processed_items.setdefault(event.item.id, set()).add(
                event.content_number,
            )

    all_events = Event.objects.filter(
        item_id__in=processed_items.keys(),
    ).select_related("item")

    events_to_delete = [
        event.id
        for event in all_events
        if event.content_number is not None
        and event.item_id in processed_items
        and event.content_number not in processed_items[event.item_id]
    ]

    if events_to_delete:
        deleted_count = Event.objects.filter(id__in=events_to_delete).delete()[0]
        logger.info("Deleted %s invalid events for updated items", deleted_count)


def get_items_to_process(user=None):
    """Get items to process for the calendar."""
    media_types = [
        choice.value
        for choice in MediaTypes
        if choice not in [MediaTypes.SEASON, MediaTypes.EPISODE]
    ]

    query = Q()

    for media_type in media_types:
        media_query = Q(**{f"{media_type}__isnull": False})
        if user:
            media_query &= Q(**{f"{media_type}__user": user})
        query |= media_query

    query &= ~Q(source=Sources.MANUAL.value)

    items = Item.objects.filter(query).distinct()

    return filter_items_to_fetch(items)


def filter_items_to_fetch(items):
    """Filter items that need calendar events."""
    now = timezone.now()
    one_year_ago = now - timezone.timedelta(days=365)
    sentinel_datetime = datetime.min.replace(tzinfo=ZoneInfo("UTC"))

    tv_items = items.filter(media_type=MediaTypes.TV.value)
    tv_items_to_include = get_tv_items_to_include(tv_items, now, sentinel_datetime)

    future_events = Event.objects.filter(item=OuterRef("pk"), datetime__gte=now)
    latest_comic_event = Event.objects.filter(
        item=OuterRef("pk"),
        item__media_type=MediaTypes.COMIC.value,
    ).order_by("-datetime")

    annotated = items.annotate(
        has_future_events=Exists(future_events),
        latest_comic_event_datetime=Subquery(latest_comic_event.values("datetime")[:1]),
    )

    tv_q = Q(id__in=tv_items_to_include)
    comic_q = Q(media_type=MediaTypes.COMIC.value) & (
        Q(event__isnull=True) | Q(latest_comic_event_datetime__gte=one_year_ago)
    )
    other_q = ~Q(media_type__in=[MediaTypes.TV.value, MediaTypes.COMIC.value]) & (
        Q(event__isnull=True) | Q(has_future_events=True)
    )

    return annotated.filter(tv_q | comic_q | other_q).distinct()


def get_tv_items_to_include(tv_items, now, sentinel_datetime):
    """Return list of TV item ids that passed the season checks."""
    if not tv_items.exists():
        return []

    tv_media_ids = list(tv_items.values_list("media_id", flat=True))

    season_events = Event.objects.filter(
        item__media_id__in=tv_media_ids,
        item__media_type=MediaTypes.SEASON.value,
    ).select_related("item")

    events_by_show = {}
    for ev in season_events:
        key = (ev.item.media_id, ev.item.source)
        events_by_show.setdefault(key, []).append(ev)

    tv_items_to_include = []
    for tv_item in tv_items:
        key = (tv_item.media_id, tv_item.source)
        show_events = events_by_show.get(key, [])

        if _should_include_tv(show_events, now, sentinel_datetime):
            tv_items_to_include.append(tv_item.id)

    return tv_items_to_include


def _should_include_tv(show_events, now, sentinel_datetime):
    if not show_events:
        return True
    if any(ev.datetime >= now for ev in show_events):
        return True
    return all(ev.datetime == sentinel_datetime for ev in show_events)
