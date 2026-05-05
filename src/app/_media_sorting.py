from django.apps import apps
from django.db import models

from app._types import MediaTypes

_DEFAULT_SORT_DIRS = {
    "score": "desc",
    "title": "asc",
    "progress": "desc",
    "status": "asc",
    "start_date": "asc",
    "end_date": "desc",
}


def default_sort_dir(sort_filter):
    """Return the default sort direction for a sort field."""
    return _DEFAULT_SORT_DIRS.get(sort_filter, "desc")


_TV_SORT_FIELDS = {
    "start_date": (
        "calculated_start_date",
        models.Min,
        "seasons__episodes__end_date",
    ),
    "end_date": ("calculated_end_date", models.Max, "seasons__episodes__end_date"),
    "progress": ("calculated_progress", models.Count, "seasons__episodes"),
}

_SEASON_SORT_FIELDS = {
    "start_date": ("calculated_start_date", models.Min, "episodes__end_date"),
    "end_date": ("calculated_end_date", models.Max, "episodes__end_date"),
    "progress": (
        "calculated_progress",
        models.Max,
        "episodes__item__episode_number",
    ),
}


def sort_media_list(queryset, sort_filter, media_type=None, sort_dir=None):
    """SQL-sort a queryset using sort annotations for calculated fields."""
    if sort_dir not in ("asc", "desc"):
        sort_dir = _DEFAULT_SORT_DIRS.get(sort_filter, "desc")

    if media_type == MediaTypes.TV.value:
        return _sort_related_media_list(
            queryset,
            sort_filter,
            sort_dir,
            _TV_SORT_FIELDS,
            ep_filter=models.Q(seasons__item__season_number__gt=0),
        )
    if media_type == MediaTypes.SEASON.value:
        return _sort_related_media_list(
            queryset,
            sort_filter,
            sort_dir,
            _SEASON_SORT_FIELDS,
        )
    return _sort_generic_media_list(queryset, sort_filter, sort_dir)


def _sort_related_media_list(
    queryset, sort_filter, sort_dir, sort_fields, ep_filter=None
):
    """Sort TV/Season media list using annotated aggregates."""
    if sort_filter not in sort_fields:
        return _sort_generic_media_list(queryset, sort_filter, sort_dir)

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


def _sort_generic_media_list(queryset, sort_filter, sort_dir="desc"):
    """Apply generic sorting logic for all media types."""
    item_model = apps.get_model("app", "Item")
    ascending = sort_dir == "asc"
    title_order = models.functions.Lower("item__title")

    if sort_filter == "title":
        return queryset.order_by(title_order if ascending else title_order.desc())

    if sort_filter in ("start_date", "end_date"):
        order = (
            models.F(sort_filter).asc(nulls_last=True)
            if ascending
            else models.F(sort_filter).desc(nulls_last=True)
        )
        return queryset.order_by(order, title_order)

    item_fields = [f.name for f in item_model._meta.fields]
    field_ref = f"item__{sort_filter}" if sort_filter in item_fields else sort_filter

    order = (
        models.F(field_ref).asc(nulls_last=True)
        if ascending
        else models.F(field_ref).desc(nulls_last=True)
    )
    return queryset.order_by(order, title_order)
