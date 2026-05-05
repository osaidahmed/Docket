from app import _prefetch_builders
from app._media_type_registry import MEDIA_TYPE_REGISTRY
from app._types import MediaTypes

MEDIA_TYPE_REGISTRY[
    MediaTypes.TV.value
].prefetch_builder = _prefetch_builders.tv_prefetch
MEDIA_TYPE_REGISTRY[
    MediaTypes.SEASON.value
].prefetch_builder = _prefetch_builders.season_prefetch

MEDIA_TYPE_REGISTRY[
    MediaTypes.MOVIE.value
].progress_annotator = _prefetch_builders.movie_progress_one
MEDIA_TYPE_REGISTRY[
    MediaTypes.TV.value
].progress_annotator = _prefetch_builders.tv_progress_released_episodes


def apply_prefetch_related(queryset, media_type):
    """Attach the appropriate prefetch_related calls for a given media type."""
    spec = MEDIA_TYPE_REGISTRY[media_type]
    builder = spec.prefetch_builder or _prefetch_builders.default_prefetch
    return builder(queryset)


def annotate_max_progress(media_list, media_type, current_datetime):
    """Annotate each media object in media_list with `.max_progress`."""
    spec = MEDIA_TYPE_REGISTRY[media_type]
    annotator = spec.progress_annotator or _prefetch_builders.event_based_progress
    annotator(media_list, current_datetime)
