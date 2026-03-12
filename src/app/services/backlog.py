from collections import defaultdict

from django.apps import apps
from django.db.models import F, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

import users
from app import config
from app.models import BasicMedia, MediaTypes, Status


def get_backlog(user, sort_by, media_type_filter=None, group_by="type"):
    """Get grouped backlog items and archive."""
    backlog_statuses = [
        Status.IN_PROGRESS.value,
        Status.PLANNING.value,
        Status.PAUSED.value,
    ]

    media_types = _get_media_types_to_process(user, media_type_filter)
    archive_all = []

    if group_by == "status":
        groups = _build_status_groups(
            user, media_types, backlog_statuses, sort_by, archive_all
        )
    else:
        groups = _build_type_groups(
            user, media_types, backlog_statuses, sort_by, archive_all
        )
        if not media_type_filter or len(media_type_filter) > 1:
            groups = _extract_rewatches(groups, backlog_statuses, sort_by)
        groups = _extract_not_yet_airing(groups, backlog_statuses)

    archive_all.sort(
        key=lambda m: (
            m.end_date is None,
            -(m.end_date.timestamp() if m.end_date else 0),
        ),
    )
    return {
        "groups": groups,
        "archive": archive_all,
        "archive_count": len(archive_all),
    }


def _fetch_and_partition(user, media_type, backlog_statuses):
    """Fetch media list and split into backlog and completed items."""
    wanted_statuses = [*backlog_statuses, Status.COMPLETED.value]
    media_list = BasicMedia.objects.get_media_list(
        user=user,
        media_type=media_type,
        status_filter=wanted_statuses,
        sort_filter=None,
    )
    backlog_items = [m for m in media_list if m.status in backlog_statuses]
    completed_items = [m for m in media_list if m.status == Status.COMPLETED.value]

    if backlog_items:
        BasicMedia.objects.annotate_max_progress(backlog_items, media_type)
        annotate_next_event(backlog_items)

    return backlog_items, completed_items


def _build_type_groups(user, media_types, backlog_statuses, sort_by, archive_all):
    """Build groups organized by media type, then status."""
    groups = []

    for media_type in media_types:
        backlog_items, completed_items = _fetch_and_partition(
            user, media_type, backlog_statuses
        )
        archive_all.extend(completed_items)

        if not backlog_items:
            continue

        status_groups = _build_status_subgroups(
            backlog_items, backlog_statuses, sort_by
        )
        if status_groups:
            groups.append(
                {
                    "media_type": media_type,
                    "label": config.get_plural_label(media_type),
                    "status_groups": status_groups,
                }
            )

    return groups


def _build_status_groups(user, media_types, backlog_statuses, sort_by, archive_all):
    """Build groups organized by status (flat, across all media types)."""
    all_backlog = []

    for media_type in media_types:
        backlog_items, completed_items = _fetch_and_partition(
            user, media_type, backlog_statuses
        )
        all_backlog.extend(backlog_items)
        archive_all.extend(completed_items)

    nya_items = [m for m in all_backlog if getattr(m, "not_yet_airing", False)]
    all_backlog = [m for m in all_backlog if not getattr(m, "not_yet_airing", False)]

    groups = _build_flat_groups(all_backlog, backlog_statuses, sort_by)
    _append_nya_group(groups, nya_items)
    return groups


def _build_flat_groups(all_backlog, backlog_statuses, sort_by):
    """Build top-level groups where each status is its own group."""
    groups = []
    for status_val in backlog_statuses:
        items = [m for m in all_backlog if m.status == status_val]
        if not items:
            continue
        sg = {
            "status": status_val,
            "items": _sort_in_progress_media(items, sort_by),
        }
        if status_val == Status.PLANNING.value:
            _split_pinned(sg)
        groups.append(
            {
                "media_type": f"status_{status_val}",
                "label": status_val,
                "status_groups": [sg],
            }
        )
    return groups


def _append_nya_group(groups, nya_items):
    """Append a Not Yet Airing group if items exist."""
    if not nya_items:
        return
    nya_items.sort(
        key=lambda m: (
            m.next_event is None,
            m.next_event.datetime if m.next_event else None,
        )
    )
    groups.append(
        {
            "media_type": "not_yet_airing",
            "label": "Not Yet Airing",
            "status_groups": [{"status": "Planning", "items": nya_items}],
        }
    )


def _build_status_subgroups(items, backlog_statuses, sort_by):
    """Build sorted status sub-groups from a flat list of items."""
    status_groups = []
    for status_val in backlog_statuses:
        matched = [m for m in items if m.status == status_val]
        if not matched:
            continue
        sg = {
            "status": status_val,
            "items": _sort_in_progress_media(matched, sort_by),
        }
        if status_val == Status.PLANNING.value:
            _split_pinned(sg)
        status_groups.append(sg)
    return status_groups


def _extract_from_status_groups(status_groups, predicate):
    """Remove items matching predicate from status groups, return them."""
    extracted = []
    for sg in status_groups:
        matches = [m for m in sg["items"] if predicate(m)]
        sg["items"] = [m for m in sg["items"] if not predicate(m)]
        extracted.extend(matches)
        if "pinned_items" in sg:
            pinned_matches = [m for m in sg["pinned_items"] if predicate(m)]
            sg["pinned_items"] = [m for m in sg["pinned_items"] if not predicate(m)]
            extracted.extend(pinned_matches)
    return extracted


def _cleanup_empty_groups(groups):
    """Remove empty status groups and empty top-level groups."""
    for group in groups:
        group["status_groups"] = [
            sg for sg in group["status_groups"] if sg["items"] or sg.get("pinned_items")
        ]
    return [g for g in groups if g["status_groups"]]


def _extract_rewatches(groups, backlog_statuses, sort_by):
    """Separate is_rewatch items into a dedicated Rewatches group."""
    rewatch_items = []
    for group in groups:
        rewatch_items.extend(
            _extract_from_status_groups(group["status_groups"], lambda m: m.is_rewatch)
        )
    groups = _cleanup_empty_groups(groups)

    if not rewatch_items:
        return groups

    rewatch_status_groups = _build_status_subgroups(
        rewatch_items, backlog_statuses, sort_by
    )
    if rewatch_status_groups:
        groups.append(
            {
                "media_type": "rewatch",
                "label": "Rewatches",
                "status_groups": rewatch_status_groups,
            }
        )

    return groups


def _extract_not_yet_airing(groups, backlog_statuses):
    """Separate not-yet-airing TV/Anime items into a dedicated group."""
    tv_anime_types = (MediaTypes.TV.value, MediaTypes.ANIME.value)
    nya_items = []
    for group in groups:
        if group["media_type"] not in tv_anime_types:
            continue
        nya_items.extend(
            _extract_from_status_groups(
                group["status_groups"],
                lambda m: getattr(m, "not_yet_airing", False),
            )
        )
    groups = _cleanup_empty_groups(groups)

    if not nya_items:
        return groups

    _append_nya_sorted_groups(groups, nya_items, backlog_statuses)
    return groups


def _append_nya_sorted_groups(groups, nya_items, backlog_statuses):
    """Build and append not-yet-airing status groups sorted by next event."""
    nya_status_groups = []
    for status_val in backlog_statuses:
        items = [m for m in nya_items if m.status == status_val]
        if not items:
            continue
        items.sort(
            key=lambda m: (
                m.next_event is None,
                m.next_event.datetime if m.next_event else None,
            )
        )
        nya_status_groups.append({"status": status_val, "items": items})
    if nya_status_groups:
        groups.append(
            {
                "media_type": "not_yet_airing",
                "label": "Not Yet Airing",
                "status_groups": nya_status_groups,
            }
        )


def count_archive(user):
    """Count archive items using the same dedup as get_backlog."""
    count = 0
    for media_type in user.get_active_media_types():
        model = apps.get_model(app_label="app", model_name=media_type)
        statuses = (
            model.objects.filter(user=user)
            .annotate(
                row_number=Window(
                    expression=RowNumber(),
                    partition_by=[F("item")],
                    order_by=F("created_at").desc(),
                )
            )
            .filter(row_number=1)
            .values_list("status", flat=True)
        )
        count += sum(1 for s in statuses if s == Status.COMPLETED.value)
    return count


def _get_media_types_to_process(user, media_type_filter):
    """Determine which media types to process based on user settings."""
    if not media_type_filter:
        return user.get_active_media_types()

    active_types = user.get_active_media_types()
    filter_set = set(media_type_filter)
    if MediaTypes.TV.value in filter_set:
        filter_set.add(MediaTypes.SEASON.value)

    return [mt for mt in active_types if mt in filter_set]


def annotate_next_event(media_list):
    """Annotate next_event, not_yet_airing, is_ongoing, is_caught_up."""
    current_time = timezone.now()

    for media in media_list:
        all_events = getattr(media.item, "prefetched_events", [])

        future_events = sorted(
            [e for e in all_events if e.datetime > current_time],
            key=lambda e: e.datetime,
        )
        media.next_event = future_events[0] if future_events else None

        non_min_events = [e for e in all_events if not e.is_min_datetime]
        media.not_yet_airing = _is_not_yet_airing(
            media, all_events, non_min_events, current_time
        )
        media.is_ongoing = _is_ongoing(media, all_events)
        media.is_caught_up = _compute_is_caught_up(media)


def _is_not_yet_airing(media, all_events, non_min_events, current_time):
    if not all_events or media.progress != 0:
        return False
    if non_min_events:
        return all(e.datetime > current_time for e in non_min_events)
    return (
        all(e.is_min_datetime for e in all_events)
        and media.status == Status.PLANNING.value
    )


def _is_ongoing(media, all_events):
    if any(e.is_min_datetime for e in all_events):
        return True
    return (
        not all_events
        and media.max_progress is None
        and media.item.media_type in (MediaTypes.MANGA.value, MediaTypes.ANIME.value)
    )


def _compute_is_caught_up(media):
    if media.caught_up:
        return True

    has_event_target = (
        media.next_event
        and media.next_event.content_number is not None
        and media.progress is not None
    )
    if has_event_target:
        return media.progress >= media.next_event.content_number - 1

    has_ongoing_progress = (
        media.is_ongoing
        and media.max_progress is not None
        and media.progress is not None
    )
    if has_ongoing_progress:
        return media.progress >= media.max_progress

    return False


def _split_pinned(status_group):
    """Split a Planning status group into pinned and rest items."""
    items = status_group["items"]
    pinned = [m for m in items if m.is_pinned]
    rest = [m for m in items if not m.is_pinned]

    if not pinned:
        status_group["items"] = _collapse_seasons(rest)
        return

    pinned.sort(key=lambda m: m.pin_order)
    status_group["pinned_items"] = pinned
    status_group["items"] = _collapse_seasons(rest)


def _collapse_seasons(items):
    """Collapse seasons of the same show into the earliest unwatched."""
    show_groups = defaultdict(list)
    result = []

    for item in items:
        if item.item.media_type == MediaTypes.SEASON.value:
            key = (item.item.media_id, item.item.source)
            show_groups[key].append(item)
        else:
            result.append(item)

    for seasons in show_groups.values():
        seasons.sort(key=lambda s: s.item.season_number or 0)
        representative = seasons[0]
        representative.collapsed_seasons = seasons[1:]
        result.append(representative)

    return result


def _sort_in_progress_media(media_list, sort_by):
    """Sort in-progress media based on the sort criteria."""
    primary_sort_functions = {
        users.models.HomeSortChoices.UPCOMING: lambda x: (
            x.next_event is None,
            x.next_event.datetime if x.next_event else None,
        ),
        users.models.HomeSortChoices.RECENT: lambda x: (
            -timezone.datetime.timestamp(
                x.progressed_at if x.progressed_at is not None else x.created_at,
            )
        ),
        users.models.HomeSortChoices.COMPLETION: lambda x: (
            x.max_progress is None,
            -(
                x.progress / x.max_progress * 100
                if x.max_progress and x.max_progress > 0
                else 0
            ),
        ),
        users.models.HomeSortChoices.EPISODES_LEFT: lambda x: (
            x.max_progress is None,
            (x.max_progress - x.progress if x.max_progress else 0),
        ),
        users.models.HomeSortChoices.TITLE: lambda x: x.item.title.lower(),
    }

    primary_sort_function = primary_sort_functions[sort_by]

    return sorted(
        media_list,
        key=lambda x: (
            primary_sort_function(x),
            -timezone.datetime.timestamp(
                x.progressed_at if x.progressed_at is not None else x.created_at,
            ),
            x.item.title.lower(),
        ),
    )
