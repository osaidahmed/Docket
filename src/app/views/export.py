import logging

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from app import config
from app.models import BasicMedia
from app.services import export as export_service
from app.templatetags import app_tags
from users.models import MediaStatusChoices

logger = logging.getLogger(__name__)


def _get_filtered_media(user, media_type, search_query=None):
    """Return the full filtered media list (unpaginated, with max_progress)."""
    sort_filter = getattr(user, f"{media_type}_sort")
    status_filter = getattr(user, f"{media_type}_status") or MediaStatusChoices.ALL

    queryset = BasicMedia.objects.get_media_list(
        user=user,
        media_type=media_type,
        status_filter=status_filter,
        sort_filter=sort_filter,
        search=search_query or None,
    )
    media_list = list(queryset)
    BasicMedia.objects.annotate_max_progress(media_list, media_type)
    return media_list


@require_GET
def export_media(request, media_type):
    """Export filtered media list as CSV, JSON, or Markdown."""
    fmt = request.GET.get("format", "csv")
    if fmt not in ("csv", "json", "md"):
        return HttpResponse("Invalid format", status=400)

    search_query = request.GET.get("search", "")
    media_list = _get_filtered_media(request.user, media_type, search_query)
    rows = export_service.serialize_media_list(media_list, media_type)

    plural_label = config.get_plural_label(media_type).lower()
    now = timezone.localtime().strftime("%Y-%m-%d")

    if fmt == "csv":
        content = export_service.format_csv(rows)
        response = HttpResponse(content, content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="{plural_label}_{now}.csv"'
        )
    elif fmt == "json":
        content = export_service.format_json(rows)
        response = HttpResponse(content, content_type="application/json")
        response["Content-Disposition"] = (
            f'attachment; filename="{plural_label}_{now}.json"'
        )
    else:
        heading = f"# {config.get_plural_label(media_type)}\n\n"
        content = heading + export_service.format_markdown(rows)
        response = HttpResponse(content, content_type="text/markdown")
        response["Content-Disposition"] = (
            f'attachment; filename="{plural_label}_{now}.md"'
        )

    logger.info(
        "User %s exported %d %s as %s",
        request.user.username,
        len(rows),
        plural_label,
        fmt,
    )
    return response


@require_POST
def export_media_txt(request, media_type):
    """Export filtered media list as TXT with user-defined template."""
    search_query = request.POST.get("search", "")
    template = request.POST.get("template", "{title}")
    separator = request.POST.get("separator", "\\n")

    separator = separator.replace("\\n", "\n").replace("\\t", "\t")

    request.user.export_txt_config = {
        "template": template,
        "separator": request.POST.get("separator", "\\n"),
    }
    request.user.save(update_fields=["export_txt_config"])

    media_list = _get_filtered_media(request.user, media_type, search_query)
    rows = export_service.serialize_media_list(media_list, media_type)
    content = export_service.format_txt(rows, template, separator)

    plural_label = config.get_plural_label(media_type).lower()
    now = timezone.localtime().strftime("%Y-%m-%d")
    response = HttpResponse(content, content_type="text/plain")
    response["Content-Disposition"] = f'attachment; filename="{plural_label}_{now}.txt"'

    logger.info(
        "User %s exported %d %s as TXT",
        request.user.username,
        len(rows),
        plural_label,
    )
    return response


@require_GET
def print_media(request, media_type):
    """Render a print-friendly view of all matching media items."""
    search_query = request.GET.get("search", "")
    media_list = _get_filtered_media(request.user, media_type, search_query)

    status_filter = (
        getattr(request.user, f"{media_type}_status") or MediaStatusChoices.ALL
    )

    context = {
        "media_type": media_type,
        "media_type_plural": app_tags.media_type_readable_plural(media_type),
        "media_list": media_list,
        "total_count": len(media_list),
        "current_status": status_filter,
    }

    return render(request, "app/print_media.html", context)
