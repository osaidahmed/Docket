"""Per-media-type behavior registry.

Closed-set dispatch table for everything that varies by media_type.
Behavior hooks are optional; callers fall through to documented defaults
when a hook is None.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

from app._media_type_config import MEDIA_TYPE_CONFIG


@dataclass
class MediaTypeSpec:
    """Static config plus behavior hooks for one media_type."""

    media_type: str
    config: dict = field(default_factory=dict)

    prefetch_builder: Callable | None = None
    progress_annotator: Callable | None = None
    sort_resolver: Callable | None = None
    user_filter_builder: Callable | None = None
    parent_filter_builder: Callable | None = None
    calendar_processor: Callable | None = None
    notification_key_builder: Callable | None = None
    import_kwargs_builder: Callable | None = None
    webhook_dispatcher: Callable | None = None


MEDIA_TYPE_REGISTRY: dict[str, MediaTypeSpec] = {
    media_type: MediaTypeSpec(media_type=media_type, config=cfg)
    for media_type, cfg in MEDIA_TYPE_CONFIG.items()
}


def get_spec(media_type: str) -> MediaTypeSpec:
    return MEDIA_TYPE_REGISTRY[media_type]
