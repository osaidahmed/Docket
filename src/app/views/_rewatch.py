"""Rewatch-flow helpers."""

from app.helpers import get_media_model
from app.link_providers import tasks as link_tasks
from app.models import BasicMedia, Item, Status


def find_rewatch_instance(
    user,
    media_id,
    media_type,
    source,
    season_number,
    statuses,
):
    """Find the first rewatch-relevant instance matching the given statuses."""
    return (
        BasicMedia.objects.filter_media(
            user,
            media_id,
            media_type,
            source,
            season_number=season_number,
        )
        .filter(status__in=statuses)
        .select_related("item")
        .first()
    )


def resolve_rewatch_item(media_id, source, media_type, season_number):
    """Look up the Item row a rewatch instance should attach to."""
    kwargs = {"media_id": media_id, "source": source, "media_type": media_type}
    if season_number:
        kwargs["season_number"] = season_number
    return Item.objects.get(**kwargs)


def create_rewatch_instance(item, user, media_type):
    """Create the new PLANNING/is_rewatch instance and queue link-generation."""
    model = get_media_model(media_type)
    instance = model.objects.create(
        item=item,
        user=user,
        status=Status.PLANNING.value,
        is_rewatch=True,
    )
    link_tasks.generate_link.delay(instance.pk, media_type)
    return instance
