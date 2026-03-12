import json
import logging

from django.apps import apps
from django.db.models import Max
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from app.models import BasicMedia, Item, Status
from app.providers import services
from app.services import backlog, recent

logger = logging.getLogger(__name__)


def _find_or_create_item(media_id, source, media_type):
    """Look up an existing Item or fetch metadata and create one."""
    try:
        return Item.objects.get(
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
        return item


def _create_media_from_search(request, status, *, caught_up=False):
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
        return _render_search_action(
            request,
            media_id,
            source,
            media_type,
            existing.item.title,
            existing,
        )

    item = _find_or_create_item(media_id, source, media_type)

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
        caught_up=caught_up,
    )

    return _render_search_action(
        request,
        media_id,
        source,
        media_type,
        item.title,
        instance,
    )


def _render_search_action(
    request, media_id, source, media_type, title, media, **extra_context
):
    """Render the search_action.html template with standard context."""
    context = {
        "item": {
            "media_id": media_id,
            "source": source,
            "media_type": media_type,
            "title": title,
        },
        "media": media,
        **extra_context,
    }
    return render(request, "app/components/search_action.html", context)


@require_POST
def quick_add(request):
    """Add media to backlog with Planning status via HTMX."""
    return _create_media_from_search(request, Status.PLANNING.value)


@require_POST
def quick_archive(request):
    """Add media as Completed via HTMX."""
    return _create_media_from_search(request, Status.COMPLETED.value)


@require_POST
def quick_catch_up_add(request):
    """Add media as In Progress + Caught Up via HTMX."""
    return _create_media_from_search(request, Status.IN_PROGRESS.value, caught_up=True)


def _render_medialist_card(request, media):
    """Render a media list card for medialist context responses."""
    BasicMedia.objects.annotate_max_progress(
        [media],
        media.item.media_type,
    )
    backlog.annotate_next_event([media])
    return render(
        request,
        "app/components/media_list_card.html",
        {
            "media": media,
            "edit_status_choices": Status.choices,
        },
    )


def _get_media_instance(request, media_type, instance_id):
    """Get a media instance for the current user."""
    return BasicMedia.objects.get_media(
        request.user,
        media_type,
        instance_id,
    )


@require_POST
def quick_complete(request):
    """Mark a backlog item as completed via HTMX."""
    media_type = request.POST["media_type"]
    instance_id = request.POST["instance_id"]
    source_context = request.POST.get("source_context")

    media = _get_media_instance(request, media_type, instance_id)
    media.status = Status.COMPLETED.value
    media.save()

    media = BasicMedia.objects.get_media_prefetch(
        request.user,
        media_type,
        instance_id,
    )

    if source_context == "medialist":
        response = _render_medialist_card(request, media)
        response["HX-Refresh"] = "true"
        return response

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
    media = _get_media_instance(
        request, request.POST["media_type"], request.POST["instance_id"]
    )
    media.status = Status.DROPPED.value
    media.save()

    return render(request, "app/components/backlog_dropped.html")


@require_POST
def quick_untrack(request):
    """Untrack (delete) a dropped media item via HTMX."""
    media = _get_media_instance(
        request, request.POST["media_type"], request.POST["instance_id"]
    )
    media.delete()
    logger.info("%s untracked successfully.", media)

    return render(request, "app/components/backlog_untracked.html")


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
    source_context = request.POST.get("source_context")

    media = _get_media_instance(request, media_type, instance_id)

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

    if source_context == "medialist":
        response = _render_medialist_card(request, media)
        response["HX-Refresh"] = "true"
        return response

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
    source_context = request.POST.get("source_context")

    media = BasicMedia.objects.get_media_prefetch(
        request.user,
        media_type,
        instance_id,
    )
    BasicMedia.objects.annotate_max_progress([media], media_type)
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
        metadata = services.get_media_metadata(
            media.item.media_type,
            media.item.media_id,
            media.item.source,
        )
        if metadata["max_progress"]:
            media.progress = metadata["max_progress"]
        media.caught_up = True
        media.save()
        media = BasicMedia.objects.get_media_prefetch(
            request.user,
            media_type,
            instance_id,
        )
        backlog.annotate_next_event([media])

    if source_context == "medialist":
        response = _render_medialist_card(request, media)
        response["HX-Refresh"] = "true"
        return response

    return render(
        request,
        "app/components/backlog_card.html",
        {"media": media, "status_choices": Status.choices},
    )


def _setup_rewatch_instance(request, item, media_type):
    """Create a new Planning rewatch instance and return it."""
    model = apps.get_model(app_label="app", model_name=media_type)
    return model.objects.create(
        item=item,
        user=request.user,
        status=Status.PLANNING.value,
        is_rewatch=True,
    )


def _render_rewatch_search_response(request, item, instance, search_params):
    """Find the completed/dropped instance and render the search action card."""
    completed_instance = (
        BasicMedia.objects.filter_media(
            request.user,
            search_params["media_id"],
            search_params["media_type"],
            search_params["source"],
            season_number=search_params["season_number"],
        )
        .filter(
            status__in=[Status.COMPLETED.value, Status.DROPPED.value],
        )
        .select_related("item")
        .first()
    )

    return _render_search_action(
        request,
        search_params["media_id"],
        search_params["source"],
        search_params["media_type"],
        item.title,
        completed_instance or instance,
        has_active=True,
    )


@require_POST
def quick_rewatch(request):
    """Create a new Planning instance for rewatch of a completed/dropped item."""
    search_params = {
        "media_id": request.POST["media_id"],
        "source": request.POST["source"],
        "media_type": request.POST["media_type"],
        "season_number": request.POST.get("season_number") or None,
    }
    source_context = request.POST.get("source_context", "search")

    active_statuses = [
        Status.IN_PROGRESS.value,
        Status.PLANNING.value,
        Status.PAUSED.value,
    ]

    active_qs = (
        BasicMedia.objects.filter_media(
            request.user,
            search_params["media_id"],
            search_params["media_type"],
            search_params["source"],
            season_number=search_params["season_number"],
        )
        .filter(status__in=active_statuses)
        .select_related("item")
    )

    existing_active = active_qs.first()
    if existing_active:
        return _render_search_action(
            request,
            search_params["media_id"],
            search_params["source"],
            search_params["media_type"],
            existing_active.item.title,
            existing_active,
        )

    item_kwargs = {
        "media_id": search_params["media_id"],
        "source": search_params["source"],
        "media_type": search_params["media_type"],
    }
    if search_params["season_number"]:
        item_kwargs["season_number"] = search_params["season_number"]
    item = Item.objects.get(**item_kwargs)

    instance = _setup_rewatch_instance(request, item, search_params["media_type"])

    if source_context == "archive":
        response = render(
            request,
            "app/components/backlog_rewatch_confirmed.html",
            {"media": instance},
        )
        response["HX-Refresh"] = "true"
        return response

    return _render_rewatch_search_response(request, item, instance, search_params)


def get_max_pin_order(user):
    """Get the highest pin_order across all media types for a user."""
    orders = []
    for media_type in user.get_active_media_types():
        model = apps.get_model(app_label="app", model_name=media_type)
        val = model.objects.filter(user=user, pin_order__isnull=False).aggregate(
            Max("pin_order")
        )["pin_order__max"]
        if val is not None:
            orders.append(val)
    return max(orders) if orders else None


@require_POST
def toggle_pin(request):
    """Toggle pin status of a Planning item via HTMX."""
    media = _get_media_instance(
        request, request.POST["media_type"], request.POST["instance_id"]
    )

    if media.is_pinned:
        media.pin_order = None
    else:
        max_order = get_max_pin_order(request.user)
        media.pin_order = 0 if max_order is None else max_order + 1

    media.save(update_fields=["pin_order"])

    response = HttpResponse("")
    response["HX-Refresh"] = "true"
    return response


@require_POST
def save_pin_order(request):
    """Persist the drag-and-drop order of pinned items."""
    ordered_ids = json.loads(request.body)

    for i, entry in enumerate(ordered_ids):
        model = apps.get_model(app_label="app", model_name=entry["media_type"])
        model.objects.filter(id=entry["id"], user=request.user).update(pin_order=i)

    return HttpResponse(status=204)
