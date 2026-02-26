import logging

from django.apps import apps
from django.db.models import Q
from django.shortcuts import render
from django.urls import reverse
from django.utils.text import slugify
from django.views.decorators.http import require_GET

from app import config, helpers
from app.models import TV, MediaTypes, Season, Sources
from app.providers import services
from app.services import recent

logger = logging.getLogger(__name__)

SUGGEST_LOCAL_MIN_QUERY = 2
SUGGEST_API_MIN_QUERY = 3
SUGGEST_MAX_RESULTS = 5


@require_GET
def media_search(request):
    """Return the media search page."""
    media_type = request.GET.get("media_type", "all")
    query = request.GET["q"].strip()
    layout = request.GET.get("layout", "list")

    if not query:
        if media_type == "all":
            return render(
                request,
                "app/search_unified.html",
                {
                    "grouped_results": [],
                    "media_type": "all",
                    "query": "",
                    "layout": layout,
                },
            )
        return render(
            request,
            "app/search.html",
            {
                "data": {"results": []},
                "source": config.get_default_source_name(media_type).value,
                "media_type": media_type,
                "layout": layout,
            },
        )

    if media_type == "all":
        enabled_types = request.user.get_enabled_media_types()
        grouped_results = services.search_all(query, enabled_types)

        for group in grouped_results:
            group["results"] = helpers.enrich_items_with_user_data(
                request, group["results"], "search"
            )

        context = {
            "grouped_results": grouped_results,
            "media_type": "all",
            "query": query,
            "layout": layout,
        }
        return render(request, "app/search_unified.html", context)

    media_type = request.user.update_preference(
        "last_search_type",
        media_type,
    )
    page = int(request.GET.get("page", 1))

    source = request.GET.get(
        "source",
        config.get_default_source_name(media_type).value,
    )

    data = services.search(media_type, query, page, source)

    if data.get("results"):
        data["results"] = helpers.enrich_items_with_user_data(
            request, data["results"], "search"
        )

    context = {
        "data": data,
        "source": source,
        "media_type": media_type,
        "layout": layout,
    }

    return render(request, "app/search.html", context)


@require_GET
def search_parent_tv(request):
    """Return the search results for parent TV shows."""
    query = request.GET.get("q", "").strip()

    if len(query) <= 1:
        return render(request, "app/components/search_parent_tv.html")

    logger.debug(
        "%s - Searching for TV shows with query: %s",
        request.user.username,
        query,
    )

    parent_tvs = TV.objects.filter(
        Q(item__title__icontains=query) | Q(item__english_title__icontains=query),
        user=request.user,
        item__source=Sources.MANUAL.value,
        item__media_type=MediaTypes.TV.value,
    )[:5]

    return render(
        request,
        "app/components/search_parent_tv.html",
        {"results": parent_tvs, "query": query},
    )


@require_GET
def search_parent_season(request):
    """Return the search results for parent seasons."""
    query = request.GET.get("q", "").strip()

    if len(query) <= 1:
        return render(request, "app/components/search_parent_tv.html")

    logger.debug(
        "%s - Searching for seasons with query: %s",
        request.user.username,
        query,
    )

    parent_seasons = Season.objects.filter(
        Q(item__title__icontains=query) | Q(item__english_title__icontains=query),
        user=request.user,
        item__source=Sources.MANUAL.value,
        item__media_type=MediaTypes.SEASON.value,
    )[:5]

    return render(
        request,
        "app/components/search_parent_season.html",
        {"results": parent_seasons, "query": query},
    )


@require_GET
def search_suggest_local(request):
    """Return local DB suggestions for the search dropdown."""
    query = request.GET.get("q", "").strip()

    if len(query) < SUGGEST_LOCAL_MIN_QUERY:
        return render(request, "app/components/search_suggest_local.html")

    enabled_types = request.user.get_enabled_media_types()
    searchable_types = [
        mt
        for mt in enabled_types
        if mt not in (MediaTypes.SEASON.value, MediaTypes.EPISODE.value)
    ]

    items_with_media = []
    for media_type in searchable_types:
        model = apps.get_model(app_label="app", model_name=media_type)
        qs = model.objects.filter(
            Q(item__title__icontains=query) | Q(item__english_title__icontains=query),
            user=request.user,
        ).select_related("item")[:SUGGEST_MAX_RESULTS]

        items_with_media.extend(
            {
                "title": media.item.title,
                "english_title": media.item.english_title,
                "image": media.item.image,
                "media_type": media.item.media_type,
                "media_id": media.item.media_id,
                "source": media.item.source,
                "status": media.status,
            }
            for media in qs
        )

    query_lower = query.lower()
    prefix = [
        r
        for r in items_with_media
        if r["title"].lower().startswith(query_lower)
        or (r["english_title"] and r["english_title"].lower().startswith(query_lower))
    ]
    contains = [r for r in items_with_media if r not in prefix]
    results = (prefix + contains)[:SUGGEST_MAX_RESULTS]

    return render(
        request,
        "app/components/search_suggest_local.html",
        {"results": results, "query": query},
    )


@require_GET
def search_suggest_api(request):
    """Return API search suggestions for the search dropdown."""
    query = request.GET.get("q", "").strip()

    if len(query) < SUGGEST_API_MIN_QUERY:
        return render(request, "app/components/search_suggest_api.html")

    enabled_types = request.user.get_enabled_media_types()

    local_keys = set()
    local_keys_param = request.GET.get("local_keys", "")
    for pair in local_keys_param.split(","):
        if ":" in pair:
            media_id, source = pair.split(":", 1)
            local_keys.add((media_id, source))

    results = services.search_suggest_api(query, enabled_types, local_keys=local_keys)[
        :5
    ]

    return render(
        request,
        "app/components/search_suggest_api.html",
        {"results": results, "query": query},
    )


@require_GET
def search_suggest_recent(request):
    """Return recently viewed items for the search dropdown on focus."""
    media_type = request.GET.get("type", "all")
    media_type_filter = None if media_type == "all" else media_type

    results = recent.get_recent(
        request.user.id,
        media_type_filter=media_type_filter,
        limit=SUGGEST_MAX_RESULTS,
    )

    for result in results:
        result["url"] = reverse(
            "media_details",
            kwargs={
                "source": result["source"],
                "media_type": result["media_type"],
                "media_id": result["media_id"],
                "title": slugify(result["title"]) or "-",
            },
        )

    return render(
        request,
        "app/components/search_suggest_local.html",
        {"results": results, "section_title": "Recently Viewed"},
    )
