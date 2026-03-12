from collections import defaultdict

from django.apps import apps
from django.db import models
from django.db.models import Count, F, Prefetch, Q, Window
from django.db.models.functions import RowNumber
from django.utils import timezone

import events
import users


class MediaManager(models.Manager):
    """Custom manager for media models."""

    def get_historical_models(self):
        """Return list of historical model names."""
        from app.models import MediaTypes  # noqa: PLC0415

        return [f"historical{media_type}" for media_type in MediaTypes.values]

    def get_media_list(
        self, user, media_type, status_filter, sort_filter, search=None, sort_dir=None
    ):
        """Get media list based on filters, sorting and search."""
        model = apps.get_model(app_label="app", model_name=media_type)
        queryset = model.objects.filter(user=user.id)

        if isinstance(status_filter, list):
            queryset = queryset.filter(status__in=status_filter)
        elif status_filter != users.models.MediaStatusChoices.ALL:
            queryset = queryset.filter(status=status_filter)

        if search:
            queryset = queryset.filter(
                Q(item__title__icontains=search)
                | Q(item__english_title__icontains=search)
            )

        queryset = queryset.annotate(
            repeats=Window(
                expression=Count("id"),
                partition_by=[F("item")],
            ),
            row_number=Window(
                expression=RowNumber(),
                partition_by=[F("item")],
                order_by=F("created_at").desc(),
            ),
        ).filter(row_number=1)

        queryset = queryset.select_related("item")
        queryset = self._apply_prefetch_related(queryset, media_type)

        if sort_filter:
            return self._sort_media_list(queryset, sort_filter, media_type, sort_dir)
        return queryset

    def _apply_prefetch_related(self, queryset, media_type):
        """Apply appropriate prefetch_related based on media type."""
        from app.models import MediaTypes  # noqa: PLC0415

        Season = apps.get_model("app", "Season")
        Episode = apps.get_model("app", "Episode")

        if media_type == MediaTypes.TV.value:
            return queryset.prefetch_related(
                Prefetch(
                    "seasons",
                    queryset=Season.objects.select_related("item"),
                ),
                Prefetch(
                    "seasons__episodes",
                    queryset=Episode.objects.select_related("item"),
                ),
            )

        base_queryset = queryset.prefetch_related(
            Prefetch(
                "item__event_set",
                queryset=events.models.Event.objects.all(),
                to_attr="prefetched_events",
            ),
        )

        if media_type == MediaTypes.SEASON.value:
            return base_queryset.prefetch_related(
                Prefetch(
                    "episodes",
                    queryset=Episode.objects.select_related("item"),
                ),
            )

        return base_queryset

    _DEFAULT_SORT_DIRS = {
        "score": "desc",
        "title": "asc",
        "progress": "desc",
        "status": "asc",
        "start_date": "asc",
        "end_date": "desc",
    }

    def _sort_media_list(self, queryset, sort_filter, media_type=None, sort_dir=None):
        """Sort media list using SQL sorting with annotations for calculated fields."""
        from app.models import MediaTypes  # noqa: PLC0415

        if sort_dir not in ("asc", "desc"):
            sort_dir = self._DEFAULT_SORT_DIRS.get(sort_filter, "desc")

        if media_type == MediaTypes.TV.value:
            return self._sort_related_media_list(
                queryset, sort_filter, sort_dir, self._TV_SORT_FIELDS,
                ep_filter=models.Q(seasons__item__season_number__gt=0),
            )
        if media_type == MediaTypes.SEASON.value:
            return self._sort_related_media_list(
                queryset, sort_filter, sort_dir, self._SEASON_SORT_FIELDS,
            )

        return self._sort_generic_media_list(queryset, sort_filter, sort_dir)

    _TV_SORT_FIELDS = {
        "start_date": ("calculated_start_date", models.Min, "seasons__episodes__end_date"),
        "end_date": ("calculated_end_date", models.Max, "seasons__episodes__end_date"),
        "progress": ("calculated_progress", models.Count, "seasons__episodes"),
    }
    _SEASON_SORT_FIELDS = {
        "start_date": ("calculated_start_date", models.Min, "episodes__end_date"),
        "end_date": ("calculated_end_date", models.Max, "episodes__end_date"),
        "progress": ("calculated_progress", models.Max, "episodes__item__episode_number"),
    }

    def _sort_related_media_list(self, queryset, sort_filter, sort_dir, sort_fields, ep_filter=None):
        """Sort TV or Season media list using annotated fields."""
        if sort_filter not in sort_fields:
            return self._sort_generic_media_list(queryset, sort_filter, sort_dir)

        ascending = sort_dir == "asc"
        title_order = models.functions.Lower("item__title")
        ann_name, agg_func, field_path = sort_fields[sort_filter]

        agg_kwargs = {"filter": ep_filter} if ep_filter else {}
        queryset = queryset.annotate(**{ann_name: agg_func(field_path, **agg_kwargs)})

        if sort_filter == "progress":
            order = ann_name if ascending else f"-{ann_name}"
        else:
            order = (
                models.F(ann_name).asc(nulls_last=True)
                if ascending
                else models.F(ann_name).desc(nulls_last=True)
            )
        return queryset.order_by(order, title_order)

    def _sort_generic_media_list(self, queryset, sort_filter, sort_dir="desc"):
        """Apply generic sorting logic for all media types."""
        Item = apps.get_model("app", "Item")
        ascending = sort_dir == "asc"
        title_order = models.functions.Lower("item__title")

        if sort_filter == "title":
            return queryset.order_by(
                title_order if ascending else title_order.desc(),
            )

        if sort_filter in ("start_date", "end_date"):
            order = (
                models.F(sort_filter).asc(nulls_last=True)
                if ascending
                else models.F(sort_filter).desc(nulls_last=True)
            )
            return queryset.order_by(order, title_order)

        item_fields = [f.name for f in Item._meta.fields]
        field_ref = (
            f"item__{sort_filter}" if sort_filter in item_fields else sort_filter
        )

        order = (
            models.F(field_ref).asc(nulls_last=True)
            if ascending
            else models.F(field_ref).desc(nulls_last=True)
        )
        return queryset.order_by(order, title_order)

    def annotate_max_progress(self, media_list, media_type):
        """Annotate max_progress for all media items."""
        from app.models import MediaTypes  # noqa: PLC0415

        current_datetime = timezone.now()

        if media_type == MediaTypes.MOVIE.value:
            for media in media_list:
                media.max_progress = 1
        elif media_type == MediaTypes.TV.value:
            self._annotate_tv_released_episodes(media_list, current_datetime)
        else:
            self._annotate_event_based_max_progress(media_list, current_datetime)

    def _annotate_event_based_max_progress(self, media_list, current_datetime):
        """Annotate max_progress from events for non-movie, non-TV media."""
        max_progress_dict = {}
        item_ids = [media.item.id for media in media_list]

        events_data = events.models.Event.objects.filter(
            item_id__in=item_ids,
            datetime__lte=current_datetime,
        ).values("item_id", "content_number")

        for event in events_data:
            item_id = event["item_id"]
            content_number = event["content_number"]
            if content_number is not None:
                current_max = max_progress_dict.get(item_id, 0)
                max_progress_dict[item_id] = max(current_max, content_number)

        for media in media_list:
            media.max_progress = max_progress_dict.get(media.item.id)

    def _annotate_tv_released_episodes(self, tv_list, current_datetime):
        """Annotate TV shows with the number of released episodes."""
        from app.models import MediaTypes  # noqa: PLC0415

        released_events = events.models.Event.objects.filter(
            item__media_id__in=[tv.item.media_id for tv in tv_list],
            item__source=tv_list[0].item.source if tv_list else None,
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

    def _build_item_filter(self, media_type, item_ids, user, status_filter):
        """Build filter kwargs for a media type query."""
        from app.models import MediaTypes  # noqa: PLC0415

        is_episode = media_type == MediaTypes.EPISODE.value
        prefix = "related_season__" if is_episode else ""
        filter_kwargs = {"item__in": item_ids, f"{prefix}user": user}
        if status_filter:
            filter_kwargs[f"{prefix}status"] = status_filter
        return filter_kwargs

    def fetch_media_for_items(self, media_types, item_ids, user, status_filter=None):
        """Fetch media objects for given items, optionally filtering by status."""
        media_by_item_id = {}

        for media_type in media_types:
            model = apps.get_model("app", media_type)
            filter_kwargs = self._build_item_filter(media_type, item_ids, user, status_filter)
            queryset = model.objects.filter(**filter_kwargs).select_related("item")
            queryset = self._apply_prefetch_related(queryset, media_type)
            self.annotate_max_progress(queryset, media_type)

            for entry in queryset:
                media_by_item_id.setdefault(entry.item_id, entry)

        return media_by_item_id

    def get_media(self, user, media_type, instance_id):
        """Get user media object given the media type and item."""
        model = apps.get_model(app_label="app", model_name=media_type)
        params = self._get_media_params(user, media_type, instance_id)
        return model.objects.get(**params)

    def get_media_prefetch(self, user, media_type, instance_id):
        """Get user media object with prefetch_related applied."""
        model = apps.get_model(app_label="app", model_name=media_type)
        params = self._get_media_params(user, media_type, instance_id)

        queryset = model.objects.filter(**params)
        queryset = self._apply_prefetch_related(queryset, media_type)
        self.annotate_max_progress(queryset, media_type)

        return queryset[0]

    def _get_media_params(self, user, media_type, instance_id):
        """Get the common filter parameters for media queries."""
        from app.models import MediaTypes  # noqa: PLC0415

        params = {"id": instance_id}

        if media_type == MediaTypes.EPISODE.value:
            params["related_season__user"] = user
        else:
            params["user"] = user

        return params

    def filter_media(
        self, user, media_id, media_type, source,
        season_number=None, episode_number=None,
    ):
        """Filter media objects based on parameters."""
        model = apps.get_model(app_label="app", model_name=media_type)
        params = self._filter_media_params(
            media_type, media_id, source, user, season_number, episode_number,
        )
        return model.objects.filter(**params)

    def filter_media_prefetch(
        self, user, media_id, media_type, source,
        season_number=None, episode_number=None,
    ):
        """Filter user media object with prefetch_related applied."""
        queryset = self.filter_media(
            user, media_id, media_type, source, season_number, episode_number,
        )
        queryset = self._apply_prefetch_related(queryset, media_type)
        self.annotate_max_progress(queryset, media_type)
        return queryset

    def _filter_media_params(
        self, media_type, media_id, source, user,
        season_number=None, episode_number=None,
    ):
        """Get the common filter parameters for media queries."""
        from app.models import MediaTypes  # noqa: PLC0415

        params = {
            "item__media_type": media_type,
            "item__source": source,
            "item__media_id": media_id,
        }

        if media_type == MediaTypes.SEASON.value:
            params["item__season_number"] = season_number
            params["user"] = user
        elif media_type == MediaTypes.EPISODE.value:
            params["item__season_number"] = season_number
            params["item__episode_number"] = episode_number
            params["related_season__user"] = user
        else:
            params["user"] = user

        return params
