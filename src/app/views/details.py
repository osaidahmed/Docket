import logging

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from app import helpers
from app.models import BasicMedia, Item, MediaTypes, Sources
from app.providers import manual, services, tmdb
from app.services import recent

logger = logging.getLogger(__name__)


@require_GET
def media_details(request, source, media_type, media_id, title):  # noqa: ARG001 title for URL
    """Return the details page for a media item."""
    media_metadata = services.get_media_metadata(media_type, media_id, source)

    recent.track_view(
        request.user.id,
        {
            "media_type": media_type,
            "media_id": media_id,
            "source": source,
            "title": media_metadata["title"],
            "english_title": media_metadata.get("english_title", ""),
            "image": media_metadata.get("image", ""),
        },
    )

    user_medias = BasicMedia.objects.filter_media_prefetch(
        request.user,
        media_id,
        media_type,
        source,
    )
    current_instance = user_medias[0] if user_medias else None

    if media_metadata.get("related"):
        for section_name, related_items in media_metadata["related"].items():
            if related_items:
                media_metadata["related"][section_name] = (
                    helpers.enrich_items_with_user_data(
                        request, related_items, section_name
                    )
                )

    context = {
        "media": media_metadata,
        "media_type": media_type,
        "user_medias": user_medias,
        "current_instance": current_instance,
    }
    return render(request, "app/media_details.html", context)


@require_GET
def season_details(request, source, media_id, title, season_number):  # noqa: ARG001 For URL
    """Return the details page for a season."""
    tv_with_seasons_metadata = services.get_media_metadata(
        "tv_with_seasons",
        media_id,
        source,
        [season_number],
    )
    season_metadata = tv_with_seasons_metadata[f"season/{season_number}"]

    user_medias = BasicMedia.objects.filter_media_prefetch(
        request.user,
        media_id,
        MediaTypes.SEASON.value,
        source,
        season_number=season_number,
    )

    current_instance = user_medias[0] if user_medias else None
    episodes_in_db = current_instance.episodes.all() if current_instance else []

    if source == Sources.MANUAL.value:
        season_metadata["episodes"] = manual.process_episodes(
            season_metadata,
            episodes_in_db,
        )
    else:
        season_metadata["episodes"] = tmdb.process_episodes(
            season_metadata,
            episodes_in_db,
        )

    if season_metadata.get("related"):
        for section_name, related_items in season_metadata["related"].items():
            if related_items:
                season_metadata["related"][section_name] = (
                    helpers.enrich_items_with_user_data(
                        request,
                        related_items,
                        section_name,
                    )
                )

    context = {
        "media": season_metadata,
        "tv": tv_with_seasons_metadata,
        "media_type": MediaTypes.SEASON.value,
        "user_medias": user_medias,
        "current_instance": current_instance,
    }
    return render(request, "app/media_details.html", context)


@require_POST
def update_media_score(request, media_type, instance_id):
    """Update the user's score for a media item."""
    media = BasicMedia.objects.get_media(
        request.user,
        media_type,
        instance_id,
    )

    score = float(request.POST.get("score"))
    media.score = score
    media.save()
    logger.info(
        "%s score updated to %s",
        media,
        score,
    )

    return JsonResponse(
        {
            "success": True,
            "score": score,
        },
    )


@require_POST
def sync_metadata(request, source, media_type, media_id, season_number=None):
    """Refresh the metadata for a media item."""
    if source == Sources.MANUAL.value:
        msg = "Manual items cannot be synced."
        messages.error(request, msg)
        return HttpResponse(
            msg,
            status=400,
            headers={"HX-Redirect": request.POST.get("next", "/")},
        )

    cache_key = f"{source}_{media_type}_{media_id}"
    if media_type == MediaTypes.SEASON.value:
        cache_key += f"_{season_number}"

    ttl = cache.ttl(cache_key)
    logger.debug("%s - Cache TTL for: %s", cache_key, ttl)

    if ttl is not None and ttl > (settings.CACHE_TIMEOUT - 3):
        msg = "The data was recently synced, please wait a few seconds."
        messages.error(request, msg)
        logger.error(msg)
    else:
        deleted = cache.delete(cache_key)
        logger.debug("%s - Old cache deleted: %s", cache_key, deleted)

        metadata = services.get_media_metadata(
            media_type,
            media_id,
            source,
            [season_number],
        )
        item, _ = Item.objects.update_or_create(
            media_id=media_id,
            source=source,
            media_type=media_type,
            season_number=season_number,
            defaults={
                "title": metadata["title"],
                "english_title": metadata.get("english_title", ""),
                "image": metadata["image"],
                "synopsis": metadata.get("synopsis", ""),
            },
        )
        title = metadata["title"]
        if season_number:
            title += f" - Season {season_number}"

        if media_type == MediaTypes.SEASON.value:
            metadata["episodes"] = tmdb.process_episodes(
                metadata,
                [],
            )

            existing_episodes = {
                ep.episode_number: ep
                for ep in Item.objects.filter(
                    source=source,
                    media_type=MediaTypes.EPISODE.value,
                    media_id=media_id,
                    season_number=season_number,
                )
            }

            episodes_to_update = []
            episode_count = 0

            for episode_data in metadata["episodes"]:
                episode_number = episode_data["episode_number"]
                if episode_number in existing_episodes:
                    episode_item = existing_episodes[episode_number]
                    episode_item.title = metadata["title"]
                    episode_item.image = episode_data["image"]
                    episodes_to_update.append(episode_item)
                    episode_count += 1

            logger.info(
                "Found %s existing episodes to update for %s",
                episode_count,
                title,
            )

            if episodes_to_update:
                updated_count = Item.objects.bulk_update(
                    episodes_to_update,
                    ["title", "image"],
                    batch_size=100,
                )
                logger.info(
                    "Successfully updated %s episodes for %s",
                    updated_count,
                    title,
                )

        item.fetch_releases(delay=False)

        msg = f"{title} was synced to {Sources(source).label} successfully."
        messages.success(request, msg)

    if request.headers.get("HX-Request"):
        return HttpResponse(
            status=204,
            headers={
                "HX-Redirect": request.POST["next"],
            },
        )
    return helpers.redirect_back(request)
