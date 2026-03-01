import logging

from django.apps import apps
from django.http import HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from app.forms import get_form_class
from app.models import BasicMedia, Item, Status
from app.providers import services
from app.services import backlog, recent

logger = logging.getLogger(__name__)


def _create_media_from_search(request, status):
    """Create a new media instance from search results with the given status."""
    media_id = request.POST["media_id"]
    source = request.POST["source"]
    media_type = request.POST["media_type"]

    existing = (
        BasicMedia.objects.filter_media(
            request.user,
            media_id,
            media_type,
            source,
        )
        .select_related("item")
        .first()
    )

    if existing:
        return render(
            request,
            "app/components/search_action.html",
            {
                "item": {
                    "media_id": media_id,
                    "source": source,
                    "media_type": media_type,
                    "title": existing.item.title,
                },
                "media": existing,
            },
        )

    try:
        item = Item.objects.get(
            media_id=media_id,
            source=source,
            media_type=media_type,
        )
    except Item.DoesNotExist:
        metadata = services.get_media_metadata(media_type, media_id, source)
        item, _ = Item.objects.get_or_create(
            media_id=media_id,
            source=source,
            media_type=media_type,
            defaults={
                "title": metadata["title"],
                "english_title": metadata.get("english_title", ""),
                "image": metadata["image"],
                "synopsis": metadata.get("synopsis", ""),
            },
        )

    recent.track_view(
        request.user.id,
        {
            "media_type": media_type,
            "media_id": media_id,
            "source": source,
            "title": item.title,
            "english_title": item.english_title,
            "image": item.image,
        },
    )

    model = apps.get_model(app_label="app", model_name=media_type)
    instance = model.objects.create(
        item=item,
        user=request.user,
        status=status,
    )

    return render(
        request,
        "app/components/search_action.html",
        {
            "item": {
                "media_id": media_id,
                "source": source,
                "media_type": media_type,
                "title": item.title,
            },
            "media": instance,
        },
    )


@require_POST
def quick_add(request):
    """Add media to backlog with Planning status via HTMX."""
    return _create_media_from_search(request, Status.PLANNING.value)


@require_POST
def quick_archive(request):
    """Add media as Completed via HTMX."""
    return _create_media_from_search(request, Status.COMPLETED.value)


@require_POST
def quick_rewatch(request):
    """Create a new Planning instance for rewatch of a completed/dropped item."""
    media_id = request.POST["media_id"]
    source = request.POST["source"]
    media_type = request.POST["media_type"]
    season_number = request.POST.get("season_number") or None
    source_context = request.POST.get("source_context", "search")

    active_statuses = [
        Status.IN_PROGRESS.value,
        Status.PLANNING.value,
        Status.PAUSED.value,
    ]

    active_qs = (
        BasicMedia.objects.filter_media(
            request.user,
            media_id,
            media_type,
            source,
            season_number=season_number,
        )
        .filter(status__in=active_statuses)
        .select_related("item")
    )

    existing_active = active_qs.first()
    if existing_active:
        return render(
            request,
            "app/components/search_action.html",
            {
                "item": {
                    "media_id": media_id,
                    "source": source,
                    "media_type": media_type,
                    "title": existing_active.item.title,
                },
                "media": existing_active,
            },
        )

    item_kwargs = {
        "media_id": media_id,
        "source": source,
        "media_type": media_type,
    }
    if season_number:
        item_kwargs["season_number"] = season_number
    item = Item.objects.get(**item_kwargs)

    model = apps.get_model(app_label="app", model_name=media_type)
    instance = model.objects.create(
        item=item,
        user=request.user,
        status=Status.PLANNING.value,
        is_rewatch=True,
    )

    if source_context == "archive":
        response = render(
            request,
            "app/components/backlog_rewatch_confirmed.html",
            {"media": instance},
        )
        response["HX-Refresh"] = "true"
        return response

    completed_instance = (
        BasicMedia.objects.filter_media(
            request.user,
            media_id,
            media_type,
            source,
            season_number=season_number,
        )
        .filter(
            status__in=[Status.COMPLETED.value, Status.DROPPED.value],
        )
        .select_related("item")
        .first()
    )

    return render(
        request,
        "app/components/search_action.html",
        {
            "item": {
                "media_id": media_id,
                "source": source,
                "media_type": media_type,
                "title": item.title,
            },
            "media": completed_instance or instance,
            "has_active": True,
        },
    )


@require_POST
def quick_complete(request):
    """Mark a backlog item as completed via HTMX."""
    media_type = request.POST["media_type"]
    instance_id = request.POST["instance_id"]

    media = BasicMedia.objects.get_media(
        request.user,
        media_type,
        instance_id,
    )
    media.status = Status.COMPLETED.value
    media.save()

    media = BasicMedia.objects.get_media_prefetch(
        request.user,
        media_type,
        instance_id,
    )

    archive_count = backlog.count_archive(request.user)

    return render(
        request,
        "app/components/backlog_completed.html",
        {
            "media": media,
            "archive_count": archive_count,
            "status_choices": Status.choices,
        },
    )


@require_POST
def quick_drop(request):
    """Drop a backlog item via HTMX."""
    media_type = request.POST["media_type"]
    instance_id = request.POST["instance_id"]

    media = BasicMedia.objects.get_media(
        request.user,
        media_type,
        instance_id,
    )
    media.status = Status.DROPPED.value
    media.save()

    return render(
        request,
        "app/components/backlog_dropped.html",
    )


@require_POST
def quick_untrack(request):
    """Untrack (delete) a dropped media item via HTMX."""
    media_type = request.POST["media_type"]
    instance_id = request.POST["instance_id"]

    media = BasicMedia.objects.get_media(
        request.user,
        media_type,
        instance_id,
    )
    media.delete()
    logger.info("%s untracked successfully.", media)

    return render(
        request,
        "app/components/backlog_untracked.html",
    )


ALLOWED_TRANSITIONS = {
    Status.PLANNING.value: Status.IN_PROGRESS.value,
    Status.PAUSED.value: Status.PLANNING.value,
}


@require_POST
def quick_status_transition(request):
    """Transition a backlog item to the next logical status via HTMX."""
    media_type = request.POST["media_type"]
    instance_id = request.POST["instance_id"]
    target_status = request.POST["target_status"]

    media = BasicMedia.objects.get_media(
        request.user,
        media_type,
        instance_id,
    )

    expected_target = ALLOWED_TRANSITIONS.get(media.status)
    if expected_target is None or expected_target != target_status:
        return HttpResponseBadRequest("Invalid status transition.")

    media.status = target_status
    if target_status == Status.IN_PROGRESS.value and not media.start_date:
        media.start_date = timezone.now().replace(second=0, microsecond=0)
    media.save()

    media = BasicMedia.objects.get_media_prefetch(
        request.user,
        media_type,
        instance_id,
    )
    backlog.annotate_next_event([media])

    response = render(
        request,
        "app/components/backlog_card.html",
        {"media": media, "status_choices": Status.choices},
    )
    response["HX-Refresh"] = "true"
    return response


@require_POST
def quick_catch_up(request):
    """Update progress to the latest aired episode."""
    media_type = request.POST["media_type"]
    instance_id = request.POST["instance_id"]

    media = BasicMedia.objects.get_media_prefetch(
        request.user,
        media_type,
        instance_id,
    )
    backlog.annotate_next_event([media])

    if media.next_event and media.next_event.content_number is not None:
        media.progress = media.next_event.content_number - 1
        media.save()
        media = BasicMedia.objects.get_media_prefetch(
            request.user,
            media_type,
            instance_id,
        )
        backlog.annotate_next_event([media])
    elif media.max_progress is not None:
        media.progress = media.max_progress
        media.save()
        media = BasicMedia.objects.get_media_prefetch(
            request.user,
            media_type,
            instance_id,
        )
        backlog.annotate_next_event([media])
    else:
        media.caught_up = True
        media.save()
        media = BasicMedia.objects.get_media_prefetch(
            request.user,
            media_type,
            instance_id,
        )
        backlog.annotate_next_event([media])

    return render(
        request,
        "app/components/backlog_card.html",
        {"media": media, "status_choices": Status.choices},
    )


@require_POST
def backlog_save(request):
    """Save inline edits from backlog card."""
    media_type = request.POST["media_type"]
    instance_id = request.POST["instance_id"]
    source_context = request.POST.get("source_context")

    media = BasicMedia.objects.get_media(
        request.user,
        media_type,
        instance_id,
    )

    old_status = media.status
    old_is_rewatch = media.is_rewatch
    form_class = get_form_class(media_type)
    form = form_class(request.POST, instance=media)

    if form.is_valid():
        form.save()
        logger.info("%s updated from backlog.", form.instance)
        rewatch_changed = media.is_rewatch != old_is_rewatch

        rewatch_cancelled = (
            old_is_rewatch
            and not media.is_rewatch
            and media.status == Status.PLANNING.value
            and BasicMedia.objects.filter_media(
                request.user,
                media.item.media_id,
                media_type,
                media.item.source,
            )
            .filter(
                status__in=[Status.COMPLETED.value, Status.DROPPED.value],
            )
            .exists()
        )
        if rewatch_cancelled:
            media.delete()

        if rewatch_cancelled or media.status == Status.DROPPED.value:
            response = render(
                request,
                "app/components/backlog_dropped.html",
            )
            if rewatch_cancelled or source_context == "medialist":
                response["HX-Refresh"] = "true"
            return response

        if source_context == "archive":
            if media.status == old_status:
                media = BasicMedia.objects.get_media_prefetch(
                    request.user,
                    media_type,
                    instance_id,
                )
            response = render(
                request,
                "app/components/backlog_card_archived.html",
                {"media": media, "status_choices": Status.choices},
            )
            if media.status != old_status or rewatch_changed:
                response["HX-Refresh"] = "true"
            return response

        if media.status == Status.COMPLETED.value:
            media = BasicMedia.objects.get_media_prefetch(
                request.user,
                media_type,
                instance_id,
            )
            archive_count = backlog.count_archive(request.user)
            return render(
                request,
                "app/components/backlog_completed.html",
                {
                    "media": media,
                    "archive_count": archive_count,
                    "status_choices": Status.choices,
                },
            )

        if media.status != old_status or rewatch_changed:
            response = render(
                request,
                "app/components/backlog_card.html",
                {"media": media, "status_choices": Status.choices},
            )
            response["HX-Refresh"] = "true"
            return response

        media = BasicMedia.objects.get_media_prefetch(
            request.user,
            media_type,
            instance_id,
        )
        backlog.annotate_next_event([media])
        return render(
            request,
            "app/components/backlog_card.html",
            {"media": media, "status_choices": Status.choices},
        )

    card_template = (
        "app/components/backlog_card_archived.html"
        if source_context == "archive"
        else "app/components/backlog_card.html"
    )
    return render(
        request,
        card_template,
        {
            "media": media,
            "status_choices": Status.choices,
            "form_errors": form.errors,
            "show_edit": True,
        },
    )
