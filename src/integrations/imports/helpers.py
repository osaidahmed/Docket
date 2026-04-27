import base64
import datetime
import hashlib
import json
import logging
from collections import defaultdict

from cryptography.fernet import Fernet
from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from simple_history.utils import bulk_create_with_history

import app
from app.models import MediaTypes

logger = logging.getLogger(__name__)


class MediaImportError(Exception):
    """Custom exception for import errors."""


class MediaImportUnexpectedError(Exception):
    """Custom exception for unexpected import errors."""


def get_existing_media(user):
    """Get all existing media for the user to check against during import."""
    excluded_types = [MediaTypes.SEASON.value, MediaTypes.EPISODE.value]
    valid_types = [value for value in MediaTypes.values if value not in excluded_types]
    existing = defaultdict(lambda: defaultdict(dict))

    for media_type in valid_types:
        media_model = apps.get_model(app_label="app", model_name=media_type)

        for media in media_model.objects.filter(user=user).select_related("item"):
            existing[media_type][media.item.source][media.item.media_id] = media

    counts = [
        f"{media_type}: {sum(len(source_dict) for source_dict in media_dict.values())}"
        for media_type, media_dict in existing.items()
    ]
    logger.debug("Existing media for user %s: %s", user.username, ", ".join(counts))
    return existing


def should_process_media(existing_media, to_delete, media_type, source, media_id, mode):
    """Determine if a media item should be processed based on mode."""
    exists = media_id in existing_media[media_type][source]

    if mode == "new" and exists:
        # In "new" mode, skip if media already exists
        logger.debug(
            "Skipping existing %s: %s (mode: new)",
            media_type,
            media_id,
        )
        return False

    if mode == "overwrite" and exists:
        # In "overwrite" mode, add to the deletion list
        logger.debug(
            "Adding existing %s to deletion list: %s (mode: overwrite)",
            media_type,
            media_id,
        )
        to_delete[media_type][source].add(media_id)

    return True


def cleanup_existing_media(to_delete, user):
    """Delete existing media if in overwrite mode."""
    for media_type, sources in to_delete.items():
        if not sources:
            continue

        model = apps.get_model(app_label="app", model_name=media_type)
        total_deleted = 0

        for source, media_ids in sources.items():
            if not media_ids:
                continue

            deleted_count, _ = model.objects.filter(
                item__media_id__in=media_ids,
                item__source=source,
                user=user,
            ).delete()
            total_deleted += deleted_count

        if total_deleted > 0:
            logger.info(
                "Deleted %s %s objects for user %s in overwrite mode",
                total_deleted,
                media_type,
                user,
            )


def _reference_config(kind):
    """Return the (model, related_attr, key_fn) tuple for a parent-ref kind."""
    if kind == "season":
        return (
            app.models.TV,
            "related_tv",
            lambda s: s.item.media_id,
        )
    return (
        app.models.Season,
        "related_season",
        lambda e: (e.item.media_id, e.item.season_number),
    )


def update_references(items, kind, user):
    """Re-point items' related-FK to existing DB instances after a bulk-skip.

    `kind` selects between "season" (rewires `related_tv` to existing TV rows)
    and "episode" (rewires `related_season` to existing Season rows). When
    bulk_create skips existing parents, child items still reference unsaved
    parents; this rewires them so the next bulk_create can persist children
    without ValueError.
    """
    model, related_attr, key_fn = _reference_config(kind)
    media_ids = {
        key_fn(item)[0] if isinstance(key_fn(item), tuple) else key_fn(item)
        for item in items
    }
    existing = {
        key_fn(obj): obj
        for obj in model.objects.filter(user=user, item__media_id__in=media_ids)
    }
    for item in items:
        key = key_fn(item)
        if key in existing:
            setattr(item, related_attr, existing[key])
            logger.debug("Updated new %s with existing %s", item, existing[key])


def bulk_create_media(bulk_media_list, user):
    """Bulk create all media objects."""
    for media_type, bulk_media in bulk_media_list.items():
        if not bulk_media:
            continue

        model = apps.get_model(app_label="app", model_name=media_type)

        logger.info("Bulk importing %s", media_type)

        # Update references for seasons and episodes
        if media_type == MediaTypes.SEASON.value:
            logger.info("Updating references for season to existing TV shows")
            update_references(bulk_media, "season", user)
        elif media_type == MediaTypes.EPISODE.value:
            logger.info(
                "Updating references for episodes to existing TV seasons",
            )
            update_references(bulk_media, "episode", user)

        bulk_create_with_history(
            bulk_media,
            model,
            batch_size=500,
            default_user=user,
        )


def create_import_schedule(
    username,
    request,
    mode,
    frequency,
    import_time,
    source,
    token=None,
):
    """Create an import schedule."""
    try:
        import_time = (
            datetime.datetime.strptime(import_time, "%H:%M")
            .astimezone(
                timezone.get_default_timezone(),
            )
            .time()
        )
    except ValueError:
        messages.error(request, "Invalid import time.")
        return

    task_name = f"Import from {source} for {username} at {import_time} {frequency}"
    if PeriodicTask.objects.filter(name=task_name).exists():
        messages.error(
            request,
            "The same import task is already scheduled.",
        )
        return

    crontab, _ = CrontabSchedule.objects.get_or_create(
        hour=import_time.hour,
        minute=import_time.minute,
        day_of_week="*" if frequency == "daily" else "*/2",
        timezone=timezone.get_default_timezone(),
    )

    kwargs = {
        "username": username,
        "user_id": request.user.id,
        "mode": mode,
    }

    if token:
        kwargs["token"] = token

    # Create new periodic task
    PeriodicTask.objects.create(
        name=task_name,
        task=f"Import from {source}",
        crontab=crontab,
        kwargs=json.dumps(kwargs),
        start_time=timezone.now(),
    )
    messages.success(request, f"{source} import task scheduled.")


def join_with_commas_and(items):
    """Join a list of items with commas and 'and'."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def fernet():
    """Derive a stable 32-byte key from Django's SECRET_KEY.

    Uses SHA-256 then urlsafe_b64encode to satisfy Fernet.
    """
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(value):
    """Return url-safe encrypted string."""
    return fernet().encrypt(value.encode()).decode()


def decrypt(token):
    """Decrypt value that was encrypted with `encrypt`."""
    return fernet().decrypt(token.encode()).decode()
