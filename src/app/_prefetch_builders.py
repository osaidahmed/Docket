from django.apps import apps
from django.db.models import Prefetch

import events


def _event_prefetch(queryset):
    return queryset.prefetch_related(
        Prefetch(
            "item__event_set",
            queryset=events.models.Event.objects.all(),
            to_attr="prefetched_events",
        ),
    )


def tv_prefetch(queryset):
    season_model = apps.get_model("app", "Season")
    episode_model = apps.get_model("app", "Episode")
    return queryset.prefetch_related(
        Prefetch("seasons", queryset=season_model.objects.select_related("item")),
        Prefetch(
            "seasons__episodes",
            queryset=episode_model.objects.select_related("item"),
        ),
    )


def season_prefetch(queryset):
    episode_model = apps.get_model("app", "Episode")
    return _event_prefetch(queryset).prefetch_related(
        Prefetch(
            "episodes",
            queryset=episode_model.objects.select_related("item"),
        ),
    )


def default_prefetch(queryset):
    return _event_prefetch(queryset)


def movie_progress_one(media_list, _current_datetime):
    for media in media_list:
        media.max_progress = 1


def tv_progress_released_episodes(media_list, current_datetime):
    from collections import defaultdict  # noqa: PLC0415

    from django.db.models import Q  # noqa: PLC0415

    from app._types import MediaTypes  # noqa: PLC0415

    if not media_list:
        return

    source_filter = Q()
    for tv in media_list:
        source_filter |= Q(
            item__media_id=tv.item.media_id,
            item__source=tv.item.source,
        )

    released_events = events.models.Event.objects.filter(
        source_filter,
        item__media_type=MediaTypes.SEASON.value,
        item__season_number__gt=0,
        datetime__lte=current_datetime,
        content_number__isnull=False,
    ).select_related("item")

    released_episodes = defaultdict(dict)
    for event in released_events:
        key = (event.item.media_id, event.item.source)
        sn = event.item.season_number
        ep = event.content_number
        released_episodes[key][sn] = max(
            ep,
            released_episodes[key].get(sn, 0),
        )

    for tv in media_list:
        tv_episodes = released_episodes.get((tv.item.media_id, tv.item.source), {})
        tv.max_progress = sum(tv_episodes.values()) if tv_episodes else 0


def event_based_progress(media_list, current_datetime):
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
