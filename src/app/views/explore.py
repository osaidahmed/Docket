from django.apps import apps
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from app import config, helpers
from app.models import MediaTypes
from app.providers import services
from app.services.recommendations import _add_title_variants, _matches_cross_media

TMDB_TYPES = {MediaTypes.MOVIE.value, MediaTypes.TV.value}


@require_GET
def explore(request):
    """Landing page for browsing media by category."""
    enabled_types = request.user.get_enabled_media_types()
    explorable_types = set(config.get_explorable_types())
    explorable = [
        {
            "media_type": mt,
            "label": MediaTypes(mt).label,
            "categories": config.get_explore_categories(mt),
        }
        for mt in enabled_types
        if mt in explorable_types
    ]
    return render(request, "app/explore.html", {"explorable_types": explorable})


def _extract_active_filters(request, filter_definitions):
    """Extract active filter values from the request query string."""
    if not filter_definitions:
        return {}
    return {
        f["key"]: value
        for f in filter_definitions
        if (value := request.GET.get(f["key"], ""))
    }


def _fetch_browse_data(request, media_type, category, active_filters, page):
    """Fetch browse data, routing to the appropriate provider."""
    if media_type in TMDB_TYPES:
        if not active_filters.get("sort_by"):
            active_filters["sort_by"] = "popularity.desc"
        return services.browse_filtered(media_type, active_filters, page), None, None

    if active_filters:
        return services.browse_filtered(media_type, active_filters, page), None, None

    if category == "seasonal" and media_type == MediaTypes.ANIME.value:
        default_year, default_season = config.get_current_anime_season()
        year = int(request.GET.get("year", default_year))
        season_name = request.GET.get("season", default_season)
        data = services.browse(
            media_type, category, page, year=year, season=season_name
        )
        return data, year, season_name

    return services.browse(media_type, category, page), None, None


def _build_extra_params(active_filters, year, season_name, hide_watched_anime):
    """Build the extra query params string for pagination links."""
    extra_params = ""
    if active_filters:
        for key, value in active_filters.items():
            extra_params += f"&{key}={value}"
    elif year is not None:
        extra_params = f"&year={year}&season={season_name}"
    if hide_watched_anime:
        extra_params += "&hide_watched_anime=1"
    return extra_params


def _filter_watched_anime(request, data):
    """Filter manga results that match user's watched anime titles."""
    if not data.get("results"):
        return
    cross_media_titles = set()
    anime_model = apps.get_model(app_label="app", model_name=MediaTypes.ANIME.value)
    anime_items = anime_model.objects.filter(user=request.user).select_related("item")
    for m in anime_items:
        _add_title_variants(cross_media_titles, m.item.title)
        if m.item.english_title:
            _add_title_variants(cross_media_titles, m.item.english_title)
    data["results"] = [
        r
        for r in data["results"]
        if not _matches_cross_media(
            r.get("title", "").strip().lower(), cross_media_titles
        )
    ]


@require_GET
def explore_type(request, media_type):
    """Browse media of a specific type by category, with optional filters."""
    categories = config.get_explore_categories(media_type)
    if categories is None:
        return redirect("explore")

    category = request.GET.get("category", categories[0]["slug"])
    page = int(request.GET.get("page", 1))
    layout = request.GET.get("layout", "list")

    valid_slugs = {c["slug"] for c in categories}
    if category not in valid_slugs:
        category = categories[0]["slug"]

    filter_definitions = config.get_explore_filters(media_type)
    active_filters = _extract_active_filters(request, filter_definitions)
    has_active_filters = bool(active_filters)

    resolved_filters = (
        _resolve_filter_options(filter_definitions) if filter_definitions else None
    )

    data, year, season_name = _fetch_browse_data(
        request, media_type, category, active_filters, page
    )

    if media_type in TMDB_TYPES and data.get("results"):
        is_airing = config.is_airing_category(category)
        for result in data["results"]:
            result.setdefault("is_ongoing", is_airing)

    hide_watched_anime = (
        media_type == MediaTypes.MANGA.value
        and request.GET.get("hide_watched_anime") == "1"
    )
    if hide_watched_anime:
        _filter_watched_anime(request, data)

    if data.get("results"):
        data["results"] = helpers.enrich_items_with_user_data(
            request, data["results"], "explore"
        )

    extra_params = _build_extra_params(
        active_filters, year, season_name, hide_watched_anime
    )

    context = {
        "data": data,
        "media_type": media_type,
        "categories": categories,
        "current_category": category,
        "layout": layout,
        "extra_params": extra_params,
        "hide_watched_anime": hide_watched_anime,
        "is_manga": media_type == MediaTypes.MANGA.value,
        "is_upcoming": config.is_upcoming_category(
            media_type, category, year, season_name
        ),
        "filter_definitions": resolved_filters,
        "active_filters": active_filters,
        "has_active_filters": has_active_filters,
        "is_tmdb_type": media_type in TMDB_TYPES,
    }

    if category == "seasonal" and media_type == MediaTypes.ANIME.value:
        context.update(
            {
                "show_season_picker": True,
                "year": year,
                "prev_year": year - 1,
                "next_year": year + 1,
                "season": season_name,
                "seasons": config.ANIME_SEASONS,
            }
        )

    if request.headers.get("HX-Request"):
        return render(request, "app/explore_results.html", context)
    return render(request, "app/explore_type.html", context)


def _resolve_filter_options(filter_definitions):
    """Resolve provider-sourced options for filter definitions."""
    resolved = []
    for f in filter_definitions:
        f_copy = {**f}
        if f.get("options_source") == "provider" and "provider_key" in f:
            raw_options = services.get_filter_options(f["provider_key"])
            f_copy["options"] = [
                {"value": str(opt["id"]), "label": opt["name"]} for opt in raw_options
            ]
        resolved.append(f_copy)
    return resolved
