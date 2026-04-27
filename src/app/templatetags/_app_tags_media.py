"""Media-config lookups, URL building, and UI components for `app_tags`."""

import json

from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from app import config
from app.models import MediaTypes, Sources, Status
from app.templatetags._app_tags_format import slug


def source_readable(source):
    """Return the readable source name."""
    return Sources(source).label


def media_type_readable(media_type):
    """Return the readable media type."""
    return MediaTypes(media_type).label


def media_type_readable_plural(media_type):
    """Return the readable media type in plural form."""
    return config.get_plural_label(media_type)


def media_status_readable(media_status):
    """Return the readable media status."""
    return Status(media_status).label


def default_source(media_type):
    """Return the default source for the media type."""
    return config.get_default_source_name(media_type).label


def media_past_verb(media_type):
    """Return the past tense verb for the given media type."""
    return config.get_verb(media_type, past_tense=True)


def media_verb_ing(media_type):
    """Return the present participle of the verb for the media type."""
    verb = config.get_verb(media_type, past_tense=False)
    if verb.endswith("e"):
        return verb[:-1] + "ing"
    return verb + "ing"


def has_caught_up(media_type):
    """Return True if the media type supports the caught-up concept."""
    return config.supports_caught_up(media_type)


def sample_search(media_type):
    """Return a sample search URL for the given media type using GET parameters."""
    return config.get_sample_search_url(media_type)


def short_unit(media_type):
    """Return the short unit for the media type."""
    return config.get_unit(media_type, short=True)


def long_unit(media_type):
    """Return the long unit for the media type."""
    return config.get_unit(media_type, short=False)


def sources(media_type):
    """Template filter to get source options for a media type."""
    return config.get_sources(media_type)


def media_color(media_type):
    """Return the color associated with the media type."""
    return config.get_text_color(media_type)


def status_color(status):
    """Return the color associated with the status."""
    return config.get_status_text_color(status)


def status_background_color(status):
    """Return the background color associated with the status."""
    return config.get_status_background_color(status)


def repeat_label(media_type):
    """Return the repeat verb for a media type (Rewatch, Reread, or Replay)."""
    verb = config.get_verb(media_type, past_tense=False)
    return f"Re{verb}"


def has_repeat(media_type):
    """Return whether a media type supports repeat tracking."""
    return config.supports_repeat(media_type)


def show_media_score(rating, user):
    """Return True if the rating should be shown given user's hide-zero preference."""
    return rating is not None and (not user.hide_zero_rating or rating > 0)


def get_search_media_types(user):
    """Return available media types for search based on user preferences."""
    enabled_types = user.get_enabled_media_types()

    types = [{"display": "All", "value": "all"}]
    types.extend(
        {
            "display": media_type_readable_plural(media_type),
            "value": media_type,
        }
        for media_type in enabled_types
    )
    return mark_safe(json.dumps(types))  # noqa: S308 — types is server-controlled


def get_sidebar_media_types(user):
    """Return available media types for sidebar navigation based on user preferences."""
    enabled_types = user.get_enabled_media_types()
    return [
        {
            "media_type": media_type,
            "display_name": media_type_readable_plural(media_type),
        }
        for media_type in enabled_types
    ]


def _media_attr(media, key, is_dict=None):
    """Get an attribute from either a dict or model object."""
    if is_dict is None:
        is_dict = isinstance(media, dict)
    if is_dict:
        return media.get(key)
    return getattr(media, key, None)


def media_url(media):
    """Return the media URL for both metadata and model object cases."""
    is_dict = isinstance(media, dict)
    media_type = _media_attr(media, "media_type", is_dict)
    source = _media_attr(media, "source", is_dict)
    media_id = _media_attr(media, "media_id", is_dict)
    title = _media_attr(media, "title", is_dict) or "-"

    if media_type in [MediaTypes.SEASON.value, MediaTypes.EPISODE.value]:
        return reverse(
            "season_details",
            kwargs={
                "source": source,
                "media_id": media_id,
                "title": slug(title),
                "season_number": _media_attr(media, "season_number", is_dict),
            },
        )

    return reverse(
        "media_details",
        kwargs={
            "source": source,
            "media_type": media_type,
            "media_id": media_id,
            "title": slug(title),
        },
    )


def media_view_url(view_name, media):
    """Return the modal URL for both metadata and model object cases."""
    is_dict = isinstance(media, dict)
    kwargs = {
        "source": _media_attr(media, "source", is_dict),
        "media_type": _media_attr(media, "media_type", is_dict),
        "media_id": _media_attr(media, "media_id", is_dict),
    }
    for key in ("season_number", "episode_number"):
        val = _media_attr(media, key, is_dict)
        if val is not None:
            kwargs[key] = val
    return reverse(view_name, kwargs=kwargs)


def component_id(component_type, media, instance_id=None):
    """Return the component ID for both metadata and model object cases."""
    is_dict = isinstance(media, dict)
    parts = [
        component_type,
        str(_media_attr(media, "media_type", is_dict)),
        str(_media_attr(media, "media_id", is_dict)),
    ]
    for key in ("season_number", "episode_number"):
        val = _media_attr(media, key, is_dict)
        if val is not None:
            parts.append(str(val))
    if instance_id:
        parts.append(str(instance_id))
    return "-".join(parts)


def unicode_icon(name):
    """Return the Unicode icon for the media type."""
    return config.get_unicode_icon(name)


def icon(name, is_active, extra_classes="w-5 h-5"):
    """Return the SVG icon for the given name."""
    base_svg = """<svg xmlns="http://www.w3.org/2000/svg"
                      width="24"
                      height="24"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      class="{active_class}{extra_classes}">
                      {content}
                 </svg>"""

    content = config.get_svg_icon(name)
    active_class = "text-indigo-400 " if is_active else ""

    svg = base_svg.format(
        content=content,
        active_class=active_class,
        extra_classes=extra_classes,
    )

    return format_html(svg)


_TAGS = (
    "get_search_media_types",
    "get_sidebar_media_types",
    "media_view_url",
    "component_id",
    "unicode_icon",
    "icon",
)
_FILTERS = (
    "source_readable",
    "media_type_readable",
    "media_type_readable_plural",
    "media_status_readable",
    "default_source",
    "media_past_verb",
    "media_verb_ing",
    "has_caught_up",
    "sample_search",
    "short_unit",
    "long_unit",
    "sources",
    "media_color",
    "status_color",
    "status_background_color",
    "repeat_label",
    "has_repeat",
    "show_media_score",
    "media_url",
)
