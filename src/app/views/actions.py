import json
import logging
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST
from simple_history.utils import bulk_update_with_history

from app.forms import get_form_class
from app.helpers import get_media_model, resolve_item
from app.link_providers import tasks as link_tasks
from app.mixins import disable_fetch_releases
from app.models import BasicMedia, Status
from app.providers import services
from app.services import backlog, recent
from app.views._backlog_helpers import get_max_pin_order
from app.views._backlog_save import commit_backlog_form
from app.views._rewatch import (
    create_rewatch_instance,
    find_rewatch_instance,
    resolve_rewatch_item,
)

logger = logging.getLogger(__name__)


def _create_media_from_search(request, status, *, caught_up=False):
    """Create a new media instance from search results with the given status."""
    media_id = request.POST["media_id"]
    source = request.POST["source"]
    media_type = request.POST["media_type"]

    existing = (
        BasicMedia.objects.filter_media(request.user, media_id, media_type, source)
        .select_related("item")
        .first()
    )

    item_data = {"media_id": media_id, "source": source, "media_type": media_type}

    if existing:
        item_data["title"] = existing.item.title
        return _render_search_action(request, item_data, existing)

    item = resolve_item(media_id, source, media_type)

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

    model = get_media_model(media_type)
    instance = model.objects.create(
        item=item,
        user=request.user,
        status=status,
        caught_up=caught_up,
    )
    link_tasks.generate_link.delay(instance.pk, media_type)

    item_data["title"] = item.title
    return _render_search_action(request, item_data, instance)


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


@require_POST
def quick_rewatch(request):
    """Create a new Planning instance for rewatch of a completed/dropped item."""
    media_id = request.POST["media_id"]
    source = request.POST["source"]
    media_type = request.POST["media_type"]
    season_number = request.POST.get("season_number") or None
    source_context = request.POST.get("source_context", "search")

    item_data = {"media_id": media_id, "source": source, "media_type": media_type}

    active = [Status.IN_PROGRESS.value, Status.PLANNING.value, Status.PAUSED.value]
    existing_active = find_rewatch_instance(
        request.user,
        media_id,
        media_type,
        source,
        season_number,
        active,
    )
    if existing_active:
        item_data["title"] = existing_active.item.title
        return _render_search_action(request, item_data, existing_active)

    item = resolve_rewatch_item(media_id, source, media_type, season_number)
    instance = create_rewatch_instance(item, request.user, media_type)

    if source_context == "archive":
        response = render(
            request,
            "app/components/backlog_rewatch_confirmed.html",
            {"media": instance},
        )
        response["HX-Refresh"] = "true"
        return response

    completed_instance = find_rewatch_instance(
        request.user,
        media_id,
        media_type,
        source,
        season_number,
        [Status.COMPLETED.value, Status.DROPPED.value],
    )

    item_data["title"] = item.title
    return _render_search_action(
        request, item_data, completed_instance or instance, has_active=True
    )


def _render_search_action(request, item_data, media, *, has_active=False):
    """Render search_action.html with standard context."""
    context = {"item": item_data, "media": media}
    if has_active:
        context["has_active"] = True
    return render(request, "app/components/search_action.html", context)


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


@require_POST
def quick_complete(request):
    """Mark a backlog item as completed via HTMX."""
    media_type = request.POST["media_type"]
    instance_id = request.POST["instance_id"]
    source_context = request.POST.get("source_context")

    media = BasicMedia.objects.get_media(request.user, media_type, instance_id)
    media.status = Status.COMPLETED.value
    media.save()

    backlog.invalidate_archive_count(request.user)
    media = BasicMedia.objects.get_media_prefetch(request.user, media_type, instance_id)

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
    media_type = request.POST["media_type"]
    instance_id = request.POST["instance_id"]

    media = BasicMedia.objects.get_media(request.user, media_type, instance_id)
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

    media = BasicMedia.objects.get_media(request.user, media_type, instance_id)
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
    source_context = request.POST.get("source_context")

    media = BasicMedia.objects.get_media(request.user, media_type, instance_id)

    expected_target = ALLOWED_TRANSITIONS.get(media.status)
    if expected_target is None or expected_target != target_status:
        return HttpResponseBadRequest("Invalid status transition.")

    media.status = target_status
    if target_status == Status.IN_PROGRESS.value and not media.start_date:
        media.start_date = timezone.now().replace(second=0, microsecond=0)
    media.save()

    media = BasicMedia.objects.get_media_prefetch(request.user, media_type, instance_id)
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

    media = BasicMedia.objects.get_media_prefetch(request.user, media_type, instance_id)
    BasicMedia.objects.annotate_max_progress([media], media_type)
    backlog.annotate_next_event([media])

    if media.next_event and media.next_event.content_number is not None:
        media.progress = media.next_event.content_number - 1
    elif media.max_progress is not None:
        media.progress = media.max_progress
    else:
        metadata = services.get_media_metadata(
            media.item.media_type, media.item.media_id, media.item.source
        )
        if metadata["max_progress"]:
            media.progress = metadata["max_progress"]
        media.caught_up = True
        media._metadata = metadata
    media.save()

    media = BasicMedia.objects.get_media_prefetch(request.user, media_type, instance_id)
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


@require_POST
def backlog_save(request):
    """Save inline edits from backlog card."""
    media_type = request.POST["media_type"]
    instance_id = request.POST["instance_id"]
    source_context = request.POST.get("source_context")

    media = BasicMedia.objects.get_media(request.user, media_type, instance_id)
    pre_save = (media.status, media.is_rewatch, media.is_pinned)
    form = get_form_class(media_type)(request.POST, instance=media)
    if not form.is_valid():
        return _render_backlog_form_errors(request, media, source_context, form.errors)

    rewatch_cancelled, state_changed = commit_backlog_form(
        request,
        media,
        media_type,
        form,
        pre_save,
    )
    if rewatch_cancelled or media.status == Status.DROPPED.value:
        return _build_dropped_response(request, rewatch_cancelled, source_context)
    return _render_backlog_save_response(
        request,
        media_type,
        instance_id,
        source_context,
        state_changed,
    )


def _build_dropped_response(request, rewatch_cancelled, source_context):
    """Render the dropped/cancelled backlog response, refreshing where needed."""
    response = render(request, "app/components/backlog_dropped.html")
    if rewatch_cancelled or source_context == "medialist":
        response["HX-Refresh"] = "true"
    return response


def _render_backlog_save_response(
    request, media_type, instance_id, source_context, state_changed
):
    """Render the appropriate response template after a backlog save."""
    media = BasicMedia.objects.get_media_prefetch(request.user, media_type, instance_id)
    ctx = {"media": media, "status_choices": Status.choices}

    if source_context == "archive":
        response = render(request, "app/components/backlog_card_archived.html", ctx)
    elif source_context == "medialist":
        response = _render_medialist_card(request, media)
    elif media.status == Status.COMPLETED.value:
        ctx["archive_count"] = backlog.count_archive(request.user)
        return render(request, "app/components/backlog_completed.html", ctx)
    else:
        if not state_changed:
            backlog.annotate_next_event([media])
        response = render(request, "app/components/backlog_card.html", ctx)

    if state_changed:
        response["HX-Refresh"] = "true"
    return response


def _render_backlog_form_errors(request, media, source_context, errors):
    """Render card with form errors after invalid backlog save."""
    if source_context == "medialist":
        return render(
            request,
            "app/components/media_list_card.html",
            {
                "media": media,
                "edit_status_choices": Status.choices,
                "form_errors": errors,
                "show_edit": True,
            },
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
            "form_errors": errors,
            "show_edit": True,
        },
    )


MAX_SCORE = 10


def _bulk_status(items, value):
    """Change status on multiple items, preserving model hooks."""
    if value not in dict(Status.choices):
        return HttpResponseBadRequest("Invalid status.")
    now = timezone.now().replace(second=0, microsecond=0)
    with transaction.atomic(), disable_fetch_releases():
        for item in items:
            item.status = value
            if _should_set_start_date(item, value):
                item.start_date = now
            item.save()
    return None


def _should_set_start_date(item, status):
    """Whether marking IN_PROGRESS should auto-set start_date on this item."""
    if status != Status.IN_PROGRESS.value:
        return False
    if item.start_date:
        return False
    cls_attr = getattr(type(item), "start_date", None)
    return cls_attr is not None and not isinstance(cls_attr, property)


def _bulk_score(items, model, value):
    """Set score on multiple items via bulk update."""
    try:
        score_val = Decimal(value) if value else None
    except (InvalidOperation, ValueError):
        return HttpResponseBadRequest("Invalid score.")
    if score_val is not None and not (0 <= score_val <= MAX_SCORE):
        return HttpResponseBadRequest("Score must be between 0 and 10.")
    for item in items:
        item.score = score_val
    bulk_update_with_history(items, model, fields=["score"])
    return None


_BULK_ACTIONS = {"status", "score", "delete"}


@require_POST
def bulk_action(request):
    """Apply a bulk action to multiple media items."""
    media_type = request.POST["media_type"]
    instance_ids = [x for x in request.POST.get("instance_ids", "").split(",") if x]
    action = request.POST["action"]
    value = request.POST.get("value", "")

    if not instance_ids or action not in _BULK_ACTIONS:
        return HttpResponseBadRequest("Invalid request.")

    model = get_media_model(media_type)
    items = list(model.objects.filter(id__in=instance_ids, user=request.user))
    if not items:
        return HttpResponseBadRequest("No valid items found.")

    error = _dispatch_bulk_action(
        action,
        items,
        model,
        value,
        request.user,
        instance_ids,
    )
    if error:
        return error

    if action in ("status", "delete"):
        backlog.invalidate_archive_count(request.user)

    logger.info("Bulk %s on %d %s items.", action, len(items), media_type)
    response = HttpResponse("")
    response["HX-Refresh"] = "true"
    return response


def _dispatch_bulk_action(action, items, model, value, user, instance_ids):
    """Apply the named bulk action to items; return error response or None."""
    if action == "status":
        return _bulk_status(items, value)
    if action == "score":
        return _bulk_score(items, model, value)
    model.objects.filter(id__in=instance_ids, user=user).delete()
    return None


@require_POST
def toggle_pin(request):
    """Toggle pin status of a Planning item via HTMX."""
    media_type = request.POST["media_type"]
    instance_id = request.POST["instance_id"]

    media = BasicMedia.objects.get_media(request.user, media_type, instance_id)

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
        model = get_media_model(entry["media_type"])
        model.objects.filter(id=entry["id"], user=request.user).update(pin_order=i)

    return HttpResponse(status=204)
