import json
from pathlib import Path

from django import template
from django.conf import settings
from django.urls import reverse
from django.utils import formats, timezone
from django.utils.dateparse import parse_date
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from unidecode import unidecode

from app import config
from app.models import MediaTypes, Sources, Status

register = template.Library()


@register.simple_tag
def get_static_file_mtime(file_path):
    """Return the last modification time of a static file for cache busting."""
    full_path = Path(settings.STATIC_ROOT) / file_path
    try:
        mtime = int(full_path.stat().st_mtime)
    except OSError:
        # If file doesn't exist or can't be accessed
        return ""
    else:
        return f"?{mtime}"


@register.filter
def no_underscore(arg1):
    """Return the title case of the string."""
    return arg1.replace("_", " ")


@register.filter
def slug(arg1):
    """Return the slug of the string.

    Sometimes slugify removes all characters from a string, so we need to
    urlencode the special characters first.
    e.g Anime: 31687
    """
    cleaned = template.defaultfilters.slugify(arg1)
    if cleaned == "":
        cleaned = template.defaultfilters.slugify(
            template.defaultfilters.urlencode(unidecode(arg1)),
        )
        if cleaned == "":
            cleaned = template.defaultfilters.urlencode(unidecode(arg1))

            if cleaned == "":
                cleaned = template.defaultfilters.urlencode(arg1)

    return cleaned


@register.filter
def date_format(datetime, user):
    """Format a datetime using user's preferred date format (date only, no time).

    Args:
        datetime: The datetime object to format
        user: User object to get preferred date format
    """
    if not datetime:
        return None
    local_dt = timezone.localtime(datetime)
    return formats.date_format(local_dt, user.date_format)


@register.filter
def iso_date_format(value, user):
    """Format an ISO date string (YYYY-MM-DD) using user's preferred date format.

    If value is not a valid ISO date string, returns the original value.
    """
    if isinstance(value, str):
        date_obj = parse_date(value)
        if date_obj:
            return formats.date_format(date_obj, user.date_format)

    return value


@register.filter
def time_format(datetime, user):
    """Format a datetime using user's preferred time format (time only, no date)."""
    if not datetime:
        return None
    local_dt = timezone.localtime(datetime)
    return formats.time_format(local_dt, user.time_format)


@register.filter
def datetime_format(datetime, user):
    """Format a datetime using user's preferred formats.

    Includes time only if TRACK_TIME setting is enabled.

    Args:
        datetime: The datetime object to format
        user: User object to get preferred date/time format
    """
    if not datetime:
        return None
    local_dt = timezone.localtime(datetime)
    formatted_date = formats.date_format(local_dt, user.date_format)

    if settings.TRACK_TIME:
        formatted_time = formats.time_format(local_dt, user.time_format)
        return f"{formatted_date} {formatted_time}"
    return formatted_date


@register.filter
def is_list(arg1):
    """Return True if the object is a list."""
    return isinstance(arg1, list)


@register.filter
def source_readable(source):
    """Return the readable source name."""
    return Sources(source).label


@register.filter
def media_type_readable(media_type):
    """Return the readable media type."""
    return MediaTypes(media_type).label


@register.filter
def media_type_readable_plural(media_type):
    """Return the readable media type in plural form."""
    return config.get_plural_label(media_type)


@register.filter
def media_status_readable(media_status):
    """Return the readable media status."""
    return Status(media_status).label


@register.filter
def default_source(media_type):
    """Return the default source for the media type."""
    return config.get_default_source_name(media_type).label


@register.filter
def media_past_verb(media_type):
    """Return the past tense verb for the given media type."""
    return config.get_verb(media_type, past_tense=True)


@register.filter
def media_verb_ing(media_type):
    """Return the present participle of the verb for the media type."""
    verb = config.get_verb(media_type, past_tense=False)
    if verb.endswith("e"):
        return verb[:-1] + "ing"
    return verb + "ing"


@register.filter
def has_caught_up(media_type):
    """Return True if the media type supports the caught-up concept."""
    return config.supports_caught_up(media_type)


@register.filter
def sample_search(media_type):
    """Return a sample search URL for the given media type using GET parameters."""
    return config.get_sample_search_url(media_type)


@register.filter
def short_unit(media_type):
    """Return the short unit for the media type."""
    return config.get_unit(media_type, short=True)


@register.filter
def long_unit(media_type):
    """Return the long unit for the media type."""
    return config.get_unit(media_type, short=False)


@register.filter
def sources(media_type):
    """Template filter to get source options for a media type."""
    return config.get_sources(media_type)


@register.simple_tag
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
    return mark_safe(json.dumps(types))


@register.simple_tag
def get_sidebar_media_types(user):
    """Return available media types for sidebar navigation based on user preferences."""
    enabled_types = user.get_enabled_media_types()

    # Format the types for sidebar
    return [
        {
            "media_type": media_type,
            "display_name": media_type_readable_plural(media_type),
        }
        for media_type in enabled_types
    ]


@register.filter
def media_color(media_type):
    """Return the color associated with the media type."""
    return config.get_text_color(media_type)


@register.filter
def status_color(status):
    """Return the color associated with the status."""
    return config.get_status_text_color(status)


@register.filter
def status_background_color(status):
    """Return the background color associated with the status."""
    return config.get_status_background_color(status)


@register.filter
def repeat_label(media_type):
    """Return the repeat verb for a media type (Rewatch, Reread, or Replay)."""
    verb = config.get_verb(media_type, past_tense=False)
    return f"Re{verb}"


@register.filter
def has_repeat(media_type):
    """Return whether a media type supports repeat tracking."""
    return config.supports_repeat(media_type)


@register.filter
def natural_day(datetime, user):
    """Format date with natural language (Today, Tomorrow, etc.)."""
    today = timezone.localdate()

    local_dt = timezone.localtime(datetime)
    datetime_date = local_dt.date()

    # Calculate the difference in days
    diff = datetime_date - today
    days = diff.days

    if days == 0:
        return "Today"
    if days == 1:
        return "Tomorrow"

    # For dates further away
    return datetime_format(datetime, user)


def _media_attr(media, key, is_dict=None):
    """Get an attribute from either a dict or model object."""
    if is_dict is None:
        is_dict = isinstance(media, dict)
    if is_dict:
        return media.get(key)
    return getattr(media, key, None)


@register.filter
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


@register.simple_tag
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


@register.simple_tag
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


@register.simple_tag
def unicode_icon(name):
    """Return the Unicode icon for the media type."""
    return config.get_unicode_icon(name)


@register.simple_tag
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


@register.filter
def str_equals(value, arg):
    """Return True if the string value is equal to the argument."""
    return str(value) == str(arg)


@register.filter
def startswith(value, arg):
    """Return True if the string value starts with the argument."""
    return str(value).startswith(str(arg))


@register.filter
def get_range(value):
    """Return a range from 1 to the given value."""
    return range(1, int(value) + 1)


@register.simple_tag
def get_pagination_range(current_page, total_pages, window, total_exact=True):  # noqa: FBT002
    """
    Return a list of page numbers to display in pagination.

    Args:
        current_page: The current page number
        total_pages: Total number of pages
        window: Number of pages to show before and after current page
        total_exact: Whether total_pages is an exact count or an estimate

    Returns:
        A list of page numbers and None values (for ellipses)
    """
    # Django templates resolve missing dict keys to "" — treat as True
    if total_exact == "":
        total_exact = True

    second_page = 2

    if not total_exact:
        result = [1]
        left_boundary = max(second_page, current_page - window)
        right_boundary = current_page + window

        if left_boundary > second_page:
            result.append(None)
        result.extend(range(left_boundary, right_boundary + 1))
        result.append(None)  # trailing ellipsis = more pages exist
        return result

    if total_pages <= 5 + window * 2:
        return list(range(1, total_pages + 1))

    left_boundary = max(second_page, current_page - window)
    right_boundary = min(total_pages - 1, current_page + window)

    result = [1]

    if left_boundary > second_page:
        result.append(None)

    result.extend(range(left_boundary, right_boundary + 1))

    if right_boundary < total_pages - 1:
        result.append(None)

    if total_pages not in result:
        result.append(total_pages)

    return result


@register.filter
def show_media_score(rating, user):
    """
    Return if we should show the rating of a media.

    Args:
        rating: the rating value of the media
        user: the user to check preferences for

    Returns:
        True if we should show the media score
    """
    return rating is not None and (not user.hide_zero_rating or rating > 0)


@register.filter
def get_item(dictionary, key):
    """Look up a key in a dictionary."""
    if isinstance(dictionary, dict):
        return dictionary.get(key, "")
    return ""


@register.filter
def csv_contains(csv_string, value):
    """Check if a value is in a comma-separated string."""
    if not csv_string:
        return False
    return str(value) in str(csv_string).split(",")


@register.filter
def timestamp_to_time(timestamp):
    """Convert a Unix timestamp to a local time string (HH:MM)."""
    if not timestamp:
        return ""
    from datetime import UTC, datetime  # noqa: PLC0415

    dt = datetime.fromtimestamp(int(timestamp), tz=UTC)
    return dt.strftime("%H:%M")
