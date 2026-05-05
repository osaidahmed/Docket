from collections import defaultdict

from django.apps import apps
from django.db.models import Prefetch

import events
from app._types import MediaTypes


def apply_prefetch_related(queryset, media_type):
    """Attach the appropriate prefetch_related calls for a given media type."""
    season_model = apps.get_model("app", "Season")
    episode_model = apps.get_model("app", "Episode")

    if media_type == MediaTypes.TV.value:
        return queryset.prefetch_related(
            Prefetch("seasons", queryset=season_model.objects.select_related("item")),
            Prefetch(
                "seasons__episodes",
                queryset=episode_model.objects.select_related("item"),
            ),
        )

    base = queryset.prefetch_related(
        Prefetch(
            "item__event_set",
            queryset=events.models.Event.objects.all(),
            to_attr="prefetched_events",
        ),
    )

    if media_type == MediaTypes.SEASON.value:
        return base.prefetch_related(
            Prefetch(
                "episodes",
                queryset=episode_model.objects.select_related("item"),
            ),
        )

    return base


def annotate_max_progress(media_list, media_type, current_datetime):
    """Annotate each media object in media_list with `.max_progress`."""
    if media_type == MediaTypes.MOVIE.value:
        for media in media_list:
            media.max_progress = 1
        return
    if media_type == MediaTypes.TV.value:
        _annotate_tv_released_episodes(media_list, current_datetime)
        return
    _annotate_event_based(media_list, current_datetime)


def _annotate_event_based(media_list, current_datetime):
    max_progress = {}
    item_ids = [media.item.id for media in media_list]

    events_data = events.models.Event.objects.filter(
        item_id__in=item_ids,
        datetime__lte=current_datetime,
    ).values("item_id", "content_number")

    for event in events_data:
        item_id = event["item_id"]
        content_number = event["content_number"]
        if content_number is not None:
            current_max = max_progress.get(item_id, 0)
            max_progress[item_id] = max(current_max, content_number)

    for media in media_list:
        media.max_progress = max_progress.get(media.item.id)


def _annotate_tv_released_episodes(tv_list, current_datetime):
    if not tv_list:
        return
    released_events = events.models.Event.objects.filter(
        item__media_id__in=[tv.item.media_id for tv in tv_list],
        item__source=tv_list[0].item.source,
        item__media_type=MediaTypes.SEASON.value,
        item__season_number__gt=0,
        datetime__lte=current_datetime,
        content_number__isnull=False,
    ).select_related("item")

    released_episodes = defaultdict(dict)
    for event in released_events:
        media_id = event.item.media_id
        sn = event.item.season_number
        ep = event.content_number
        released_episodes[media_id][sn] = max(
            ep, released_episodes[media_id].get(sn, 0)
        )

    for tv in tv_list:
        tv_episodes = released_episodes.get(tv.item.media_id, {})
        tv.max_progress = sum(tv_episodes.values()) if tv_episodes else 0
