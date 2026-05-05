from django.urls import reverse
from django.utils.http import urlencode

from app._explore_config import (  # noqa: F401  (re-exports for external callers)
    get_current_anime_season,
    get_explore_categories,
    get_explore_filters,
    has_explore_filters,
    is_airing_category,
    is_announced_media,
    is_upcoming_category,
)
from app._media_type_config import (  # noqa: F401  (re-exports for external callers)
    AIRING_CATEGORIES,
    ANIME_SEASONS,
    ANNOUNCED_STATUSES,
    DISCOVER_SECTIONS,
    MEDIA_TYPE_CONFIG,
    MONTH_TO_SEASON,
    SEASON_START_MONTH,
    STATUS_CONFIG,
)
from app._media_type_registry import MEDIA_TYPE_REGISTRY
from app._types import MediaTypes, is_season_media


def _types_with_config_key(key):
    return [mt for mt, spec in MEDIA_TYPE_REGISTRY.items() if key in spec.config]


def get_explorable_types():
    """Return media type values that support explore/browse."""
    return _types_with_config_key("explore_categories")


def get_searchable_types():
    """Return media type values that have a sample_query (i.e., are searchable)."""
    return _types_with_config_key("sample_query")


def get_config(media_type):
    """Get the full config dictionary for a media type."""
    spec = MEDIA_TYPE_REGISTRY.get(media_type)
    return spec.config if spec else None


def get_property(media_type, prop_name):
    """Get a specific property for a media type."""
    config = get_config(media_type)
    try:
        return config[prop_name]
    except KeyError:
        msg = f"Property '{prop_name}' not found for media type '{media_type}'."
        raise KeyError(msg) from None


def get_sources(media_type):
    """Get the list of sources for a media type."""
    return get_property(media_type, "sources")


def get_default_source_name(media_type):
    """Get the human-readable default source name."""
    return get_property(media_type, "default_source")


def get_sample_query(media_type):
    """Get the sample search query."""
    return get_property(media_type, "sample_query")


def get_sample_search_url(media_type):
    """Get the full sample search URL."""
    if is_season_media(media_type):
        media_type = MediaTypes.TV.value

    query = get_sample_query(media_type)

    base_url = reverse("search")
    query_params = {"media_type": media_type, "q": query}
    return f"{base_url}?{urlencode(query_params)}"


def get_unicode_icon(media_type):
    """Get the unicode icon."""
    return get_property(media_type, "unicode_icon")


def get_verb(media_type, past_tense):
    """Get the verb (present or past tense)."""
    verbs = get_property(media_type, "verb")
    return verbs[1] if past_tense else verbs[0]


def get_text_color(media_type):
    """Get the text color class."""
    return get_property(media_type, "text_color")


def get_stats_color(media_type):
    """Get the stats color."""
    return get_property(media_type, "stats_color")


def get_svg_icon(media_type):
    """Get the SVG path data."""
    return get_property(media_type, "svg_icon")


def get_date_key(media_type):
    """Get the primary date key used for fetching release/start dates."""
    return get_property(media_type, "date_key")


def get_unit(media_type, short):
    """Get the unit of measurement (e.g., episode, chapter)."""
    cfg = get_config(media_type)
    unit = cfg.get("unit")
    if not unit:
        return ""
    return unit[0] if short else unit[1]


def get_plural_label(media_type):
    """Get the plural label, falling back to singular + 's'."""
    cfg = get_config(media_type)
    return cfg.get("plural_label", f"{MediaTypes(media_type).label}s")


def supports_repeat(media_type):
    """Return whether the media type supports repeat/rewatch tracking."""
    cfg = get_config(media_type)
    return cfg.get("supports_repeat", True)


def supports_caught_up(media_type):
    """Return whether the media type supports caught-up tracking."""
    cfg = get_config(media_type)
    return cfg.get("supports_caught_up", True)


def supports_recommendations(media_type):
    """Return whether the media type has provider-backed recommendations."""
    cfg = get_config(media_type)
    return cfg.get("supports_recommendations", False)


def get_status_config(status):
    """Get the full config dictionary for a status."""
    return STATUS_CONFIG.get(status)


def get_status_property(status, prop_name):
    """Get a specific property for a status."""
    config = get_status_config(status)
    if config is None:
        msg = f"Status '{status}' not found in configuration."
        raise KeyError(msg)
    try:
        return config[prop_name]
    except KeyError:
        msg = f"Property '{prop_name}' not found for status '{status}'."
        raise KeyError(msg) from None


def get_status_text_color(status):
    """Get the text color class for a status."""
    return get_status_property(status, "text_color")


def get_status_stats_color(status):
    """Get the stats color for a status."""
    return get_status_property(status, "stats_color")


def get_status_background_color(status):
    """Get the background color for a status."""
    return get_status_property(status, "background_color")


def get_discover_sections(media_type):
    """Get the discover page section config for a media type."""
    return DISCOVER_SECTIONS.get(media_type)


def get_discoverable_types():
    """Return the list of media types that have discover pages."""
    return list(DISCOVER_SECTIONS.keys())
