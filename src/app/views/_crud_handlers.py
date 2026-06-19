"""CRUD-flow helpers."""

from app import helpers
from app.models import BasicMedia, Item, MediaTypes, Season, Sources, Status
from app.providers import services


def resolve_or_build_media_instance(
    user,
    media_type,
    media_id,
    source,
    season_number,
    instance_id,
):
    """Fetch the existing media instance or build a fresh unsaved one."""
    if instance_id:
        return BasicMedia.objects.get_media(user, media_type, instance_id)

    metadata = services.get_media_metadata(
        media_type,
        media_id,
        source,
        [season_number],
    )
    item, _ = Item.objects.get_or_create(
        media_id=media_id,
        source=source,
        media_type=media_type,
        season_number=season_number,
        defaults=helpers.item_defaults_from_metadata(metadata),
    )
    model = helpers.get_media_model(media_type)
    return model(item=item, user=user)


def resolve_or_create_episode_season(user, media_id, source, season_number):
    """Look up or create the Season row that an episode_save should attach to."""
    try:
        return Season.objects.get(
            item__media_id=media_id,
            item__source=source,
            item__season_number=season_number,
            item__episode_number=None,
            user=user,
        )
    except Season.DoesNotExist:
        tv_with_seasons_metadata = services.get_media_metadata(
            "tv_with_seasons",
            media_id,
            source,
            [season_number],
        )
        season_metadata = tv_with_seasons_metadata[f"season/{season_number}"]
        item, _ = Item.objects.get_or_create(
            media_id=media_id,
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            season_number=season_number,
            defaults={
                "title": tv_with_seasons_metadata["title"],
                "image": season_metadata["image"],
            },
        )
        return Season.objects.create(
            item=item,
            user=user,
            score=None,
            status=Status.IN_PROGRESS.value,
            notes="",
        )
