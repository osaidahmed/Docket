from dataclasses import dataclass

from django.apps import apps
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from app import config, helpers
from app.models import MediaTypes
from app.providers import services
from app.services.recommendations import _add_title_variants, _matches_cross_media

TMDB_TYPES = {MediaTypes.MOVIE.value, MediaTypes.TV.value}


@dataclass
class ExploreContext:
    """Template context source for the explore_type view."""

    data: dict
    media_type: str
    categories: list
    category: str
    layout: str
    order: str
    extra_params: str
    hide_watched_anime: bool
    resolved_filters: list | None
    active_filters: dict
    expanded_filters: set
    year: int | None = None
    season_name: str | None = None

    def to_template_context(self) -> dict:
        """Render this context object into the dict the explore template expects."""
        ctx = {
            "data": self.data,
            "media_type": self.media_type,
            "categories": self.categories,
            "current_category": self.category,
            "layout": self.layout,
            "extra_params": self.extra_params,
            "hide_watched_anime": self.hide_watched_anime,
            "is_manga": self.media_type == MediaTypes.MANGA.value,
            "is_upcoming": config.is_upcoming_category(
                self.media_type,
                self.category,
                self.year,
                self.season_name,
            ),
            "filter_definitions": self.resolved_filters,
            "active_filters": self.active_filters,
            "has_active_filters": bool(self.active_filters),
            "expanded_filters": self.expanded_filters,
            "is_tmdb_type": self.media_type in TMDB_TYPES,
            "order": self.order,
        }
        if self.category == "seasonal" and self.media_type == MediaTypes.ANIME.value:
            year = self.year or 0
            ctx.update(
                {
                    "show_season_picker": True,
                    "year": self.year,
                    "prev_year": year - 1,
                    "next_year": year + 1,
                    "season": self.season_name,
                    "seasons": config.ANIME_SEASONS,
                }
            )
        return ctx


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


def _fetch_seasonal_anime(request, category, page):
    """Fetch seasonal anime browse data with year/season from request."""
    default_year, default_season = config.get_current_anime_season()
    year = int(request.GET.get("year", default_year))
    season_name = request.GET.get("season", default_season)
    data = services.browse(
        MediaTypes.ANIME.value, category, page, year=year, season=season_name
    )
    return data, year, season_name


def _fetch_browse_data(request, media_type, category, active_filters, page):
    """Fetch browse data, routing to the appropriate provider."""
    if active_filters:
        if media_type in TMDB_TYPES and not active_filters.get("sort_by"):
            active_filters["sort_by"] = "popularity"
        return services.browse_filtered(media_type, active_filters, page), None, None

    if category == "seasonal" and media_type == MediaTypes.ANIME.value:
        return _fetch_seasonal_anime(request, category, page)

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


def _annotate_tmdb_airing(data, media_type, category):
    """Mark TMDB results with is_ongoing based on airing category."""
    if media_type not in TMDB_TYPES or not data.get("results"):
        return
    is_airing = config.is_airing_category(category)
    for result in data["results"]:
        result.setdefault("is_ongoing", is_airing)


def _apply_hide_watched_anime(request, media_type, data):
    """Filter out manga matching user's watched anime if requested."""
    if media_type != MediaTypes.MANGA.value:
        return False
    if request.GET.get("hide_watched_anime") != "1":
        return False
    _filter_watched_anime(request, data)
    return True


@require_GET
def explore_type(request, media_type):
    """Browse media of a specific type by category, with optional filters."""
    categories = config.get_explore_categories(media_type)
    if categories is None:
        return redirect("explore")

    has_discover = config.get_discover_sections(media_type) is not None
    if request.GET.get("view") == "discover" and has_discover:
        from app.views.discover import render_discover  # noqa: PLC0415

        return render_discover(request, media_type)

    category = request.GET.get("category", categories[0]["slug"])
    page = int(request.GET.get("page", 1))
    layout = request.GET.get("layout", "list")
    order = request.GET.get("order", "desc")

    valid_slugs = {c["slug"] for c in categories}
    if category not in valid_slugs:
        category = categories[0]["slug"]

    filter_definitions = config.get_explore_filters(media_type)
    active_filters = _extract_active_filters(request, filter_definitions)

    if active_filters.get("sort_by"):
        active_filters["order"] = order

    resolved_filters = (
        _resolve_filter_options(filter_definitions) if filter_definitions else None
    )
    expanded_filters = _get_expanded_filters(resolved_filters, active_filters)

    data, year, season_name = _fetch_browse_data(
        request, media_type, category, active_filters, page
    )

    _annotate_tmdb_airing(data, media_type, category)
    hide_watched_anime = _apply_hide_watched_anime(request, media_type, data)

    if data.get("results"):
        data["results"] = helpers.enrich_items_with_user_data(
            request, data["results"], "explore"
        )

    extra_params = _build_extra_params(
        active_filters, year, season_name, hide_watched_anime
    )

    context = ExploreContext(
        data=data,
        media_type=media_type,
        categories=categories,
        category=category,
        layout=layout,
        order=order,
        extra_params=extra_params,
        hide_watched_anime=hide_watched_anime,
        resolved_filters=resolved_filters,
        active_filters=active_filters,
        expanded_filters=expanded_filters,
        year=year,
        season_name=season_name,
    ).to_template_context()

    context["has_discover"] = has_discover
    context["current_view"] = "browse"
    context["text_color"] = config.get_text_color(media_type)

    if request.headers.get("HX-Request"):
        return render(request, "app/explore_results.html", context)
    return render(request, "app/explore_type.html", context)


VISIBLE_CHIP_COUNT = 12


def _get_expanded_filters(resolved_filters, active_filters):
    """Return set of filter keys that should start with chips expanded."""
    if not resolved_filters or not active_filters:
        return set()
    expanded = set()
    for f in resolved_filters:
        if f.get("type") != "multi_select":
            continue
        selected = set(active_filters.get(f["key"], "").split(","))
        selected.discard("")
        if not selected:
            continue
        overflow_values = {
            o["value"]
            for i, o in enumerate(f.get("options", []))
            if i >= VISIBLE_CHIP_COUNT
        }
        if selected & overflow_values:
            expanded.add(f["key"])
    return expanded


def _dedup_options(raw_options):
    """Deduplicate provider options by ID, preserving order."""
    seen_ids = set()
    options = []
    for opt in raw_options:
        opt_id = str(opt["id"])
        if opt_id not in seen_ids:
            seen_ids.add(opt_id)
            options.append({"value": opt_id, "label": opt["name"]})
    return options


def _sort_by_priority(options, priority_ids):
    """Sort options so priority IDs appear first in the given order."""
    if not priority_ids:
        return options
    priority_set = {str(pid) for pid in priority_ids}
    priority_order = {str(pid): i for i, pid in enumerate(priority_ids)}
    prioritized = sorted(
        [o for o in options if o["value"] in priority_set],
        key=lambda o: priority_order[o["value"]],
    )
    rest = [o for o in options if o["value"] not in priority_set]
    return prioritized + rest


def _resolve_filter_options(filter_definitions):
    """Resolve provider-sourced options for filter definitions."""
    resolved = []
    for f in filter_definitions:
        f_copy = {**f}
        if f.get("options_source") == "provider" and "provider_key" in f:
            raw_options = services.get_filter_options(f["provider_key"])
            options = _dedup_options(raw_options)
            f_copy["options"] = _sort_by_priority(options, f.get("priority_ids"))
        resolved.append(f_copy)
    return resolved
