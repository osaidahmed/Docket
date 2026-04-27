"""String/date/time formatting helpers for the `app_tags` template library."""

from pathlib import Path

from django import template
from django.conf import settings
from django.utils import formats, timezone
from django.utils.dateparse import parse_date
from unidecode import unidecode


def get_static_file_mtime(file_path):
    """Return the last modification time of a static file for cache busting."""
    full_path = Path(settings.STATIC_ROOT) / file_path
    try:
        mtime = int(full_path.stat().st_mtime)
    except OSError:
        return ""
    else:
        return f"?{mtime}"


def no_underscore(arg1):
    """Return the title case of the string."""
    return arg1.replace("_", " ")


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


def _user_format(value, user, format_attr, format_fn):
    """Format a datetime through the user's preferred date or time format."""
    if not value:
        return None
    return format_fn(timezone.localtime(value), getattr(user, format_attr))


def date_format(datetime, user):
    """Format a datetime using user's preferred date format (date only, no time)."""
    return _user_format(datetime, user, "date_format", formats.date_format)


def iso_date_format(value, user):
    """Format an ISO date string (YYYY-MM-DD) using user's preferred date format.

    If value is not a valid ISO date string, returns the original value.
    """
    if isinstance(value, str):
        date_obj = parse_date(value)
        if date_obj:
            return formats.date_format(date_obj, user.date_format)

    return value


def time_format(datetime, user):
    """Format a datetime using user's preferred time format (time only, no date)."""
    return _user_format(datetime, user, "time_format", formats.time_format)


def datetime_format(datetime, user):
    """Format a datetime using user's preferred formats.

    Includes time only if TRACK_TIME setting is enabled.
    """
    if not datetime:
        return None
    local_dt = timezone.localtime(datetime)
    formatted_date = formats.date_format(local_dt, user.date_format)

    if settings.TRACK_TIME:
        formatted_time = formats.time_format(local_dt, user.time_format)
        return f"{formatted_date} {formatted_time}"
    return formatted_date


def natural_day(datetime, user):
    """Format date with natural language (Today, Tomorrow, etc.)."""
    today = timezone.localdate()

    local_dt = timezone.localtime(datetime)
    datetime_date = local_dt.date()

    diff = datetime_date - today
    days = diff.days

    if days == 0:
        return "Today"
    if days == 1:
        return "Tomorrow"

    return datetime_format(datetime, user)


def timestamp_to_time(timestamp):
    """Convert a Unix timestamp to a local time string (HH:MM)."""
    if not timestamp:
        return ""
    from datetime import UTC, datetime  # noqa: PLC0415

    dt = datetime.fromtimestamp(int(timestamp), tz=UTC)
    return dt.strftime("%H:%M")


_TAGS = ("get_static_file_mtime",)
_FILTERS = (
    "no_underscore",
    "slug",
    "date_format",
    "iso_date_format",
    "time_format",
    "datetime_format",
    "natural_day",
    "timestamp_to_time",
)
