import logging
import re
from urllib.parse import urlparse

from django.apps import apps
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST

from app.models import BasicMedia, Item, MediaTypes, Status
from app.providers import services

logger = logging.getLogger(__name__)

_MIN_QUERY_LENGTH = 2


def _extract_query_from_url(url):
    """Extract a search query from a URL's path slug."""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None

    path = parsed.path.rstrip("/")
    if not path:
        return None

    slug = path.split("/")[-1]
    slug = re.sub(r"[-._]\d+$", "", slug)
    query = slug.replace("-", " ").replace("_", " ")
    query = re.sub(r"\s+", " ", query).strip()
    return query if len(query) >= _MIN_QUERY_LENGTH else None


def _process_link(request, url, media_type):
    """Process a single URL: extract query, search, create or skip."""
    url = url.strip()
    query = _extract_query_from_url(url)
    if not query:
        return {
            "url": url,
            "status": "failed",
            "reason": "Could not extract title from URL",
        }

    try:
        data = services.search(media_type, query, page=1)
    except Exception:
        logger.exception("API search failed for query '%s'", query)
        return {
            "url": url,
            "query": query,
            "status": "failed",
            "reason": "API search failed",
        }

    results = data.get("results", [])
    if not results:
        return {
            "url": url,
            "query": query,
            "status": "failed",
            "reason": "No results found",
        }

    best = results[0]
    media_id = str(best["media_id"])
    source = best["source"]

    existing = (
        BasicMedia.objects.filter_media(request.user, media_id, media_type, source)
        .select_related("item")
        .first()
    )

    if existing:
        link_updated = False
        if not existing.link and url:
            existing.link = url
            existing.save(update_fields=["link"])
            link_updated = True
        return {
            "url": url,
            "query": query,
            "status": "already_tracked",
            "title": existing.item.title,
            "image": existing.item.image,
            "link_updated": link_updated,
        }

    try:
        item = Item.objects.get(media_id=media_id, source=source, media_type=media_type)
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

    model = apps.get_model(app_label="app", model_name=media_type)
    model.objects.create(
        item=item,
        user=request.user,
        status=Status.PLANNING.value,
        link=url,
    )

    return {
        "url": url,
        "query": query,
        "status": "added",
        "title": item.title,
        "image": item.image,
    }


def _get_media_type_choices(user):
    """Return media type choices for the dropdown, filtered by user preferences."""
    enabled_types = user.get_enabled_media_types()
    return [
        {"value": mt, "label": MediaTypes(mt).label}
        for mt in enabled_types
        if mt not in (MediaTypes.SEASON.value, MediaTypes.EPISODE.value)
    ]


@require_GET
def add_by_link(request):
    """Render the add-by-link form page."""
    return render(
        request,
        "app/add_by_link.html",
        {"media_types": _get_media_type_choices(request.user)},
    )


@require_POST
def add_by_link_process(request):
    """Process pasted links and add matching media to the backlog."""
    media_type = request.POST.get("media_type", "")
    links_text = request.POST.get("links", "")

    media_types = _get_media_type_choices(request.user)
    valid_types = {mt["value"] for mt in media_types}

    if media_type not in valid_types:
        return render(
            request,
            "app/add_by_link.html",
            {"media_types": media_types, "error": "Invalid media type."},
        )

    urls = [line.strip() for line in links_text.splitlines() if line.strip()]
    if not urls:
        return render(
            request,
            "app/add_by_link.html",
            {"media_types": media_types, "error": "No links provided."},
        )

    results = [_process_link(request, url, media_type) for url in urls]

    added = [r for r in results if r["status"] == "added"]
    already_tracked = [r for r in results if r["status"] == "already_tracked"]
    failed = [r for r in results if r["status"] == "failed"]

    return render(
        request,
        "app/add_by_link.html",
        {
            "media_types": media_types,
            "selected_type": media_type,
            "results": results,
            "added": added,
            "already_tracked": already_tracked,
            "failed": failed,
            "added_count": len(added),
            "tracked_count": len(already_tracked),
            "failed_count": len(failed),
        },
    )
