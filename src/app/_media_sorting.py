from app import _sort_resolvers
from app._media_type_registry import MEDIA_TYPE_REGISTRY
from app._types import MediaTypes

MEDIA_TYPE_REGISTRY[MediaTypes.TV.value].sort_resolver = _sort_resolvers.tv_sort
MEDIA_TYPE_REGISTRY[MediaTypes.SEASON.value].sort_resolver = _sort_resolvers.season_sort


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


def sort_media_list(queryset, sort_filter, media_type=None, sort_dir=None):
    """SQL-sort a queryset using sort annotations for calculated fields."""
    if sort_dir not in ("asc", "desc"):
        sort_dir = _DEFAULT_SORT_DIRS.get(sort_filter, "desc")

    spec = MEDIA_TYPE_REGISTRY.get(media_type) if media_type else None
    resolver = (spec.sort_resolver if spec else None) or _sort_resolvers.generic_sort
    return resolver(queryset, sort_filter, sort_dir)
