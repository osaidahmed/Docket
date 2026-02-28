import logging

from django.core.paginator import Paginator
from django.db.models import prefetch_related_objects
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from app import config
from app.models import BasicMedia, MediaTypes, Status
from app.services import backlog
from app.templatetags import app_tags
from users.models import HomeSortChoices, MediaSortChoices, MediaStatusChoices

logger = logging.getLogger(__name__)


@require_GET
def home(request):
    """Home page with unified backlog."""
    sort_by = request.user.update_preference("home_sort", request.GET.get("sort"))
    selected_types = request.user.update_home_type_filter(
        request.GET.get("type"),
    )

    backlog_data = backlog.get_backlog(
        request.user,
        sort_by,
        selected_types or None,
    )

    truncation = int(request.user.home_truncation)
    if truncation > 0:
        virtual_types = {"rewatch", "not_yet_airing"}
        for group in backlog_data["groups"]:
            if group["media_type"] in virtual_types:
                continue
            for sg in group["status_groups"]:
                if len(sg["items"]) > truncation:
                    sg["items"] = sg["items"][:truncation]
                    sg["truncated"] = True
                    sg["media_type"] = group["media_type"]

    archive_open = request.GET.get("view") == "archive"
    archive = backlog_data["archive"]
    if not archive_open:
        archive = archive[:20]

    selected_set = set(selected_types)
    type_chips = _get_type_filter_choices(
        request.user,
        selected_set,
        sort_by,
        archive_open,
    )

    context = {
        "groups": backlog_data["groups"],
        "archive": archive,
        "archive_count": backlog_data["archive_count"],
        "archive_open": archive_open,
        "current_sort": sort_by,
        "sort_choices": HomeSortChoices.choices,
        "selected_types": selected_set,
        "selected_types_csv": ",".join(selected_types),
        "show_type_headers": len(selected_types) != 1,
        "type_filter_choices": type_chips,
        "status_choices": Status.choices,
    }
    return render(request, "app/home.html", context)


def _get_type_filter_choices(user, selected, sort_by, archive_open):
    home_url = reverse("home")
    choices = []
    for mt in user.get_enabled_media_types():
        if mt == MediaTypes.SEASON.value:
            continue
        toggled = selected - {mt} if mt in selected else selected | {mt}
        type_param = ",".join(toggled) if toggled else "all"
        if archive_open:
            url = f"{home_url}?view=archive&type={type_param}"
        else:
            url = f"{home_url}?sort={sort_by}&type={type_param}"
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


@require_GET
def media_list(request, media_type):
    """Return the media list page."""
    layout = request.user.update_preference(
        f"{media_type}_layout",
        request.GET.get("layout"),
    )
    sort_filter = request.user.update_preference(
        f"{media_type}_sort",
        request.GET.get("sort"),
    )
    status_filter = request.user.update_preference(
        f"{media_type}_status",
        request.GET.get("status"),
    )
    search_query = request.GET.get("search", "")
    page = request.GET.get("page", 1)

    if not status_filter:
        status_filter = MediaStatusChoices.ALL

    media_queryset = BasicMedia.objects.get_media_list(
        user=request.user,
        media_type=media_type,
        status_filter=status_filter,
        sort_filter=sort_filter,
        search=search_query,
    )

    items_per_page = 32
    paginator = Paginator(media_queryset, items_per_page)
    media_page = paginator.get_page(page)

    BasicMedia.objects.annotate_max_progress(
        media_page.object_list,
        media_type,
    )

    context = {
        "media_type": media_type,
        "media_type_plural": app_tags.media_type_readable_plural(media_type).lower(),
        "media_list": media_page,
        "current_layout": layout,
        "layout_class": ".media-grid" if layout == "grid" else "tbody",
        "current_sort": sort_filter,
        "current_status": status_filter,
        "sort_choices": MediaSortChoices.choices,
        "status_choices": MediaStatusChoices.choices,
    }

    if request.headers.get("HX-Request"):
        if request.headers.get("HX-Target") == "empty_list":
            response = HttpResponse()
            response["HX-Redirect"] = reverse("medialist", args=[media_type])
            return response
        if layout == "grid":
            template_name = "app/components/media_grid_items.html"
        else:
            template_name = "app/components/media_table_items.html"
    else:
        template_name = "app/media_list.html"

    return render(request, template_name, context)
