import logging

from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import prefetch_related_objects
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from app import _media_sorting, config
from app.models import BasicMedia, MediaTypes, Status
from app.services import backlog, grouping
from app.services import recommendations as recs_service
from app.services.backlog import _ARCHIVE_DEFAULT_DIRS, BacklogOptions
from app.templatetags import app_tags
from users.models import (
    ArchiveSortChoices,
    HomeGroupChoices,
    HomeLayoutChoices,
    HomeSortChoices,
    MediaSortChoices,
    MediaStatusChoices,
)

logger = logging.getLogger(__name__)


def _resolve_home_params(request):
    """Parse preferences and build type chip query for the home page."""
    user = request.user
    layout = user.update_preference("home_layout", request.GET.get("layout"))
    group_by = user.update_preference("home_group", request.GET.get("group"))
    selected_types = user.update_home_type_filter(request.GET.get("type"))
    archive_open = request.GET.get("view") == "archive"
    shared_qs = f"layout={layout}&group={group_by}"

    if archive_open:
        archive_sort = user.update_preference("archive_sort", request.GET.get("sort"))
        archive_sort_dir = request.GET.get("sort_dir")
        archive_search = request.GET.get("search", "")
        sort_by = user.home_sort
        query_base = f"view=archive&sort={archive_sort}&{shared_qs}"
        if archive_sort_dir:
            query_base += f"&sort_dir={archive_sort_dir}"
        if archive_search:
            query_base += f"&search={archive_search}"
    else:
        sort_by = user.update_preference("home_sort", request.GET.get("sort"))
        archive_sort = user.archive_sort
        archive_sort_dir = None
        archive_search = None
        query_base = f"sort={sort_by}&{shared_qs}"

    selected_set = set(selected_types)
    type_chips = _get_type_filter_choices(user, selected_set, query_base)

    effective_archive_sort_dir = (
        archive_sort_dir
        if archive_sort_dir in ("asc", "desc")
        else _ARCHIVE_DEFAULT_DIRS.get(archive_sort, "desc")
    )

    return {
        "selected_types": selected_types,
        "selected_set": selected_set,
        "type_chips": type_chips,
        "archive_open": archive_open,
        "effective_archive_sort_dir": effective_archive_sort_dir,
        "options": BacklogOptions(
            sort_by=sort_by,
            media_type_filter=selected_types or None,
            group_by=group_by,
            archive_sort=archive_sort,
            archive_sort_dir=archive_sort_dir,
            archive_search=archive_search,
        ),
        "context_vars": {
            "current_sort": sort_by,
            "sort_choices": HomeSortChoices.choices,
            "current_layout": layout,
            "layout_choices": HomeLayoutChoices.choices,
            "current_group": group_by,
            "group_choices": HomeGroupChoices.choices,
            "archive_sort": archive_sort,
            "archive_sort_choices": ArchiveSortChoices.choices,
            "archive_search": archive_search or "",
        },
    }


@require_GET
def home(request):
    """Home page with unified backlog."""
    params = _resolve_home_params(request)
    backlog_data = backlog.get_backlog(request.user, params["options"])
    group_by = params["options"].group_by

    truncation = int(request.user.home_truncation)
    if truncation > 0 and group_by == "type":
        _apply_truncation(backlog_data["groups"], truncation)

    archive = backlog_data["archive"]
    if request.user.group_related_media:
        from app.services.backlog import (  # noqa: PLC0415
            _apply_grouping_to_backlog_items,
        )

        archive = _apply_grouping_to_backlog_items(archive, request.user)
    if not params["archive_open"]:
        archive = archive[:20]

    context = {
        "groups": backlog_data["groups"],
        "archive": archive,
        "archive_count": backlog_data["archive_count"],
        "archive_open": params["archive_open"],
        "selected_types": params["selected_set"],
        "selected_types_csv": ",".join(params["selected_types"]),
        "show_type_headers": len(params["selected_types"]) != 1,
        "type_filter_choices": params["type_chips"],
        "status_choices": Status.choices,
        "archive_sort_dir": params["effective_archive_sort_dir"],
        **params["context_vars"],
    }
    return render(request, "app/home.html", context)


_VIRTUAL_TYPES = {"rewatch", "not_yet_airing"}


def _apply_truncation(groups, truncation):
    """Apply truncation limits to backlog status groups."""
    for group in groups:
        if group["media_type"] not in _VIRTUAL_TYPES:
            _truncate_status_groups(group, truncation)


def _truncate_status_groups(group, truncation):
    """Mark status groups that exceed the truncation limit."""
    for sg in group["status_groups"]:
        if len(sg["items"]) > truncation:
            sg["truncated_at"] = truncation
            sg["media_type"] = group["media_type"]


def _get_type_filter_choices(user, selected, query_base):
    """Build type filter chip URLs for the home page."""
    home_url = reverse("home")
    choices = []
    for mt in user.get_enabled_media_types():
        if mt == MediaTypes.SEASON.value:
            continue
        toggled = selected - {mt} if mt in selected else selected | {mt}
        type_param = ",".join(toggled) if toggled else "all"
        url = f"{home_url}?{query_base}&type={type_param}"
        choices.append(
            {
                "value": mt,
                "label": config.get_plural_label(mt),
                "toggle_url": url,
            }
        )
    return choices


@require_POST
def progress_edit(request, media_type, instance_id):
    """Increase or decrease the progress of a media item from home page."""
    operation = request.POST["operation"]

    media = BasicMedia.objects.get_media_prefetch(
        request.user,
        media_type,
        instance_id,
    )

    if operation == "increase":
        media.increase_progress()
    elif operation == "decrease":
        media.decrease_progress()

    if media_type == MediaTypes.SEASON.value:
        media.refresh_from_db()
        prefetch_related_objects([media], "episodes")

    return render(
        request,
        "app/components/progress_changer.html",
        {"media": media},
    )


def _split_pinned_from_queryset(queryset, status_filter):
    """Separate pinned Planning items from the main queryset."""
    if status_filter != Status.PLANNING.value:
        return queryset, []
    pinned = list(queryset.filter(pin_order__isnull=False).order_by("pin_order"))
    rest = queryset.filter(pin_order__isnull=True)
    return rest, pinned


def _annotate_media_list(page_items, pinned_list, media_type):
    """Annotate max_progress and next_event on page items and pinned list."""
    BasicMedia.objects.annotate_max_progress(page_items, media_type)
    if pinned_list:
        BasicMedia.objects.annotate_max_progress(pinned_list, media_type)
    if media_type != MediaTypes.TV.value:
        backlog.annotate_next_event(page_items)
        if pinned_list:
            backlog.annotate_next_event(pinned_list)


_LAYOUT_CLASSES = {
    "grid": ".media-grid",
    "table": "tbody",
}

_HTMX_TEMPLATES = {
    "grid": "app/components/media_grid_items.html",
    "table": "app/components/media_table_items.html",
}


def _parse_medialist_params(request, media_type):
    """Parse and persist media list query parameters."""
    layout = request.user.update_preference(
        f"{media_type}_layout",
        request.GET.get("layout"),
    )
    sort_filter = request.user.update_preference(
        f"{media_type}_sort",
        request.GET.get("sort"),
    )
    status_param = request.GET.get("status")
    status_filter = (
        status_param
        if request.GET.get("temp") and status_param
        else request.user.update_preference(f"{media_type}_status", status_param)
    )
    if not status_filter:
        status_filter = MediaStatusChoices.ALL

    return {
        "layout": layout,
        "sort_filter": sort_filter,
        "status_filter": status_filter,
        "search": request.GET.get("search", ""),
        "sort_dir": request.GET.get("sort_dir"),
        "page": request.GET.get("page", 1),
    }


@require_GET
def media_list(request, media_type):
    """Return the media list page."""
    params = _parse_medialist_params(request, media_type)
    layout = params["layout"]
    status_filter = params["status_filter"]
    page = params["page"]

    media_queryset = BasicMedia.objects.get_media_list(
        user=request.user,
        media_type=media_type,
        status_filter=status_filter,
        sort_filter=params["sort_filter"],
        search=params["search"],
        sort_dir=params["sort_dir"],
    )
    media_queryset, pinned_list = _split_pinned_from_queryset(
        media_queryset,
        status_filter,
    )

    is_grouped = _should_group(request.user, media_type)
    media_page = _paginate_medialist(media_queryset, page, media_type, is_grouped)
    _annotate_media_list(media_page.object_list, pinned_list, media_type)

    redirect_response = _medialist_htmx_redirect(
        request,
        page,
        pinned_list,
        status_filter,
        media_type,
    )
    if redirect_response is not None:
        return redirect_response

    context = _build_medialist_context(
        request,
        media_type,
        params,
        media_page,
        pinned_list,
        is_grouped,
    )
    return render(request, _get_medialist_template(request, layout), context)


def _paginate_medialist(media_queryset, page, media_type, is_grouped):
    """Apply grouping (when enabled) and paginate the media list."""
    if is_grouped:
        grouped = grouping.group_media_list(list(media_queryset), media_type)
        paginator = Paginator(grouped, 32)
    else:
        paginator = Paginator(media_queryset, 32)
    return paginator.get_page(page)


def _medialist_htmx_redirect(request, page, pinned_list, status_filter, media_type):
    """Return an HX-Redirect HttpResponse if one is required, else None."""
    if not request.headers.get("HX-Request"):
        return None
    if request.headers.get("HX-Target") == "empty_list":
        response = HttpResponse()
        response["HX-Redirect"] = reverse("medialist", args=[media_type])
        return response
    if int(page) <= 1 and (pinned_list or status_filter == Status.PLANNING.value):
        response = HttpResponse()
        response["HX-Redirect"] = request.get_full_path()
        return response
    return None


def _build_medialist_context(
    request,
    media_type,
    params,
    media_page,
    pinned_list,
    is_grouped,
):
    """Build the template context for the media-list page."""
    sort_filter = params["sort_filter"]
    effective_sort_dir = (
        params["sort_dir"]
        if params["sort_dir"] in ("asc", "desc")
        else _media_sorting.default_sort_dir(sort_filter)
    )
    export_cfg = request.user.export_txt_config or {}
    return {
        "media_type": media_type,
        "media_type_plural": app_tags.media_type_readable_plural(media_type).lower(),
        "media_list": media_page,
        "current_layout": params["layout"],
        "layout_class": _LAYOUT_CLASSES.get(params["layout"], "#media-cards-list"),
        "current_sort": sort_filter,
        "current_sort_dir": effective_sort_dir,
        "current_status": params["status_filter"],
        "sort_choices": MediaSortChoices.choices,
        "status_choices": MediaStatusChoices.choices,
        "export_txt_template": export_cfg.get(
            "template",
            "{title} - {score} ({status})",
        ),
        "export_txt_separator": export_cfg.get("separator", "\\n"),
        "edit_status_choices": Status.choices,
        "supports_recommendations": config.supports_recommendations(media_type),
        "pinned_list": pinned_list,
        "active_tab": request.GET.get("tab", "collection"),
        "is_grouped": is_grouped,
    }


def _should_group(user, media_type):
    return user.group_related_media and media_type in (
        MediaTypes.SEASON.value,
        MediaTypes.ANIME.value,
    )


@require_POST
def toggle_grouping(request):
    """Toggle the group_related_media preference."""
    request.user.group_related_media = not request.user.group_related_media
    request.user.save(update_fields=["group_related_media"])
    referer = request.META.get("HTTP_REFERER", "/")
    return HttpResponse(status=204, headers={"HX-Redirect": referer})


def _get_medialist_template(request, layout):
    """Determine the template for media_list."""
    if not request.headers.get("HX-Request"):
        return "app/media_list.html"
    return _HTMX_TEMPLATES.get(layout, "app/components/media_cards_items.html")


@require_GET
def recommendations_section(request, media_type):
    """Return the recommendations section for a media type."""
    if not config.supports_recommendations(media_type):
        return HttpResponse("")

    user_id = request.user.id
    cache_key = recs_service.get_cache_key(user_id, media_type)
    result = cache.get(cache_key)

    if result is not None:
        return _render_recommendations(request, result, media_type)

    progress = recs_service.get_progress(user_id, media_type)
    if progress is None:
        from app.tasks import compute_recommendations_task  # noqa: PLC0415

        progress = {"current": 0, "total": 0}
        cache.set(
            recs_service.get_progress_key(user_id, media_type),
            progress,
            recs_service.PROGRESS_TIMEOUT,
        )
        compute_recommendations_task.delay(user_id, media_type)

    pct = (
        round(progress["current"] / progress["total"] * 100)
        if progress["total"] > 0
        else 0
    )
    return render(
        request,
        "app/components/recommendations_progress.html",
        {
            "media_type": media_type,
            "progress_current": progress["current"],
            "progress_total": progress["total"],
            "progress_pct": pct,
        },
    )


def _render_recommendations(request, result, media_type):
    return render(
        request,
        "app/components/recommendations_section.html",
        {
            "active_recs": result["active"],
            "full_recs": result["full"],
            "genre_sections": result.get("genres", []),
            "media_type": media_type,
        },
    )
