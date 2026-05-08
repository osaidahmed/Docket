import json
import logging

from django.apps import apps

from app._types import MediaTypes
from users.models import (
    DateFormatChoices,
    HomeTruncationChoices,
    QuickWatchDateChoices,
    TimeFormatChoices,
)

logger = logging.getLogger(__name__)


def _validated(post_data, key, choices, default):
    value = post_data.get(key, default)
    valid = {c[0] for c in choices}
    return value if value in valid else default


def update_preferences_from_post(user, post_data, all_types):
    """Apply a POSTed preferences form to ``user`` and persist the changes."""
    user.clickable_media_cards = "clickable_media_cards" in post_data
    user.quick_watch_date = _validated(
        post_data,
        "quick_watch_date",
        QuickWatchDateChoices.choices,
        QuickWatchDateChoices.CURRENT_DATE,
    )
    user.home_truncation = _validated(
        post_data,
        "home_truncation",
        HomeTruncationChoices.choices,
        HomeTruncationChoices.ALL,
    )
    user.progress_bar = "progress_bar" in post_data
    user.hide_completed_recommendations = "hide_completed_recommendations" in post_data
    user.hide_zero_rating = "hide_zero_rating" in post_data
    user.group_related_media = "group_related_media" in post_data

    color_scheme = post_data.get("color_scheme", "charcoal")
    valid_schemes = {c[0] for c in user.COLOR_SCHEME_CHOICES}
    if color_scheme in valid_schemes:
        user.color_scheme = color_scheme

    user.date_format = _validated(
        post_data,
        "date_format",
        DateFormatChoices.choices,
        DateFormatChoices.ISO,
    )
    user.time_format = _validated(
        post_data,
        "time_format",
        TimeFormatChoices.choices,
        TimeFormatChoices.HOUR_24,
    )

    valid_types = set(MediaTypes.values)
    media_types_checked = [
        t for t in post_data.getlist("media_types_checkboxes") if t in valid_types
    ]
    for media_type in all_types:
        pref = user.get_or_create_media_pref(media_type)
        pref.enabled = media_type in media_types_checked
        pref.save(update_fields=["enabled"])

    _load_json_pref(user, "media_type_order", post_data.get("media_type_order", ""))
    _load_json_pref(user, "link_preferences", post_data.get("link_preferences", ""))

    user.save()


def _load_json_pref(user, attr, raw_value):
    if not raw_value:
        return
    try:
        setattr(user, attr, json.loads(raw_value))
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Invalid JSON for preference %s: %s", attr, exc)


def queue_link_backfill(user):
    """Queue Generate Link for every existing entry without a link.

    Iterates the user's media for each media type that has a configured
    provider or template and queues the Celery task. The task itself
    short-circuits when an instance already has a link, so re-saving prefs
    is safe (and re-attempts any prior misses).
    """
    from app.link_providers import tasks as link_tasks  # noqa: PLC0415

    prefs = user.link_preferences or {}
    valid_types = set(MediaTypes.values)
    for media_type, cfg in prefs.items():
        if media_type not in valid_types:
            continue
        if not (cfg.get("provider") or cfg.get("template")):
            continue
        model = apps.get_model("app", media_type)
        for pk in model.objects.filter(user=user, link="").values_list(
            "pk",
            flat=True,
        ):
            link_tasks.generate_link.delay(pk, media_type)
