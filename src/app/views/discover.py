from django.shortcuts import render
from django.views.decorators.http import require_GET

from app import config, helpers
from app.providers import services


def render_discover(request, media_type):
    """Render discover content for a media type (called from explore_type)."""
    sections_config = config.get_discover_sections(media_type)
    sections_data = services.discover_sections(media_type)
    sections = _build_sections(request, sections_config, sections_data)

    return render(
        request,
        "app/explore_type.html",
        {
            "media_type": media_type,
            "sections": sections,
            "text_color": config.get_text_color(media_type),
            "stats_color": config.get_stats_color(media_type),
            "has_discover": True,
            "current_view": "discover",
        },
    )


@require_GET
def explore_section(request, media_type, section_key):
    """HTMX endpoint: load more items for a discover section."""
    page = int(request.GET.get("page", 2))

    sections_config = config.get_discover_sections(media_type)
    if not sections_config:
        return render(request, "app/partials/discover_grid_items.html", {"items": []})

    section_cfg = next(
        (s for s in sections_config if s["key"] == section_key), None
    )
    if not section_cfg:
        return render(request, "app/partials/discover_grid_items.html", {"items": []})

    data = services.discover_section_page(media_type, section_cfg, page)
    items = data.get("results", []) if isinstance(data, dict) else []
    items = items[: section_cfg["limit"]]

    if items:
        items = helpers.enrich_items_with_user_data(request, items, "discover")

    has_next_page = _has_next(data)

    return render(
        request,
        "app/partials/discover_grid_items.html",
        {
            "items": items,
            "media_type": media_type,
            "section_key": section_key,
            "next_page": page + 1,
            "has_next_page": has_next_page,
            "text_color": config.get_text_color(media_type),
        },
    )


def _build_sections(request, sections_config, sections_data):
    """Build template-ready sections with enriched items."""
    sections = []
    for cfg in sections_config:
        data = sections_data.get(cfg["key"])
        if data is None:
            continue

        section = {
            "key": cfg["key"],
            "label": cfg["label"],
            "type": cfg["type"],
        }

        if cfg["type"] == "schedule_list":
            section["days"] = data
        else:
            items = data.get("results", []) if isinstance(data, dict) else []
            items = items[: cfg["limit"]]
            if items:
                items = helpers.enrich_items_with_user_data(
                    request, items, "discover"
                )
            section["items"] = items
            section["has_next_page"] = _has_next(data)
            section["next_page"] = 2

        sections.append(section)
    return sections


def _has_next(data):
    """Check if there is a next page from either explicit flag or pagination."""
    if not isinstance(data, dict):
        return False
    if "has_next_page" in data:
        return data["has_next_page"]
    page = data.get("page", 1)
    total_pages = data.get("total_pages", 1)
    return page < total_pages
