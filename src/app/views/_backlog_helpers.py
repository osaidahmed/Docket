"""Helpers shared between actions and backlog-save flows."""

from app.helpers import get_media_model
from app.models import BasicMedia, Status


def get_max_pin_order(user):
    """Return the highest pin_order across all active media types for the user."""
    from django.db import connection  # noqa: PLC0415

    media_types = user.get_active_media_types()
    if not media_types:
        return None

    parts = []
    params = []
    for mt in media_types:
        model = get_media_model(mt)
        table = model._meta.db_table
        parts.append(
            f"SELECT MAX(pin_order) AS max_pin FROM {table}"  # noqa: S608
            " WHERE user_id = %s AND pin_order IS NOT NULL",
        )
        params.append(user.id)

    query = f"SELECT MAX(max_pin) FROM ({' UNION ALL '.join(parts)}) sub"  # noqa: S608
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        return cursor.fetchone()[0]


def update_pin_order(user, media, old_is_pinned, is_pinned_submitted):
    """Update pin_order after a backlog save."""
    if is_pinned_submitted == old_is_pinned:
        return
    if is_pinned_submitted:
        max_order = get_max_pin_order(user)
        media.pin_order = 0 if max_order is None else max_order + 1
    else:
        media.pin_order = None
    media.save(update_fields=["pin_order"])


def check_rewatch_cancelled(user, media, media_type, old_is_rewatch):
    """Check if a rewatch was cancelled (unmarked while in Planning)."""
    return (
        old_is_rewatch
        and not media.is_rewatch
        and media.status == Status.PLANNING.value
        and BasicMedia.objects.filter_media(
            user, media.item.media_id, media_type, media.item.source
        )
        .filter(status__in=[Status.COMPLETED.value, Status.DROPPED.value])
        .exists()
    )
