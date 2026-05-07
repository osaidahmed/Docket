import json
from dataclasses import dataclass

from django.apps import apps
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from app import config, helpers
from app._types import is_anime_media, is_manga_media
from app.models import MediaTypes
from app.providers import services
from app.services.recommendations import _add_title_variants, _matches_cross_media

TMDB_TYPES = {MediaTypes.MOVIE.value, MediaTypes.TV.value}


def _chip_expanded_json(expanded_filters):
    """JSON for Alpine's chipExpanded state — keys mapped to true."""
    return json.dumps(dict.fromkeys(expanded_filters or [], True))


def _multi_select_values_json(filter_definitions, active_filters):
    """JSON for Alpine's multiSelectValues state — multi-select key to list."""
    if not filter_definitions:
        return "{}"
    values = {}
    for f in filter_definitions:
        if f.get("type") != "multi_select":
            continue
        raw = (active_filters or {}).get(f["key"], "")
        values[f["key"]] = [v for v in raw.split(",") if v]
    return json.dumps(values)


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

    def to_template_context(self, **extras) -> dict:
        """Render this context object into the dict the explore template expects."""
        ctx = {
            "data": self.data,
            "media_type": self.media_type,
            "categories": self.categories,
            "current_category": self.category,
            "layout": self.layout,
            "extra_params": self.extra_params,
            "hide_watched_anime": self.hide_watched_anime,
            "is_manga": is_manga_media(self.media_type),
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
            "chip_expanded_json": _chip_expanded_json(self.expanded_filters),
            "multi_select_values_json": _multi_select_values_json(
                self.resolved_filters,
                self.active_filters,
            ),
            "is_tmdb_type": self.media_type in TMDB_TYPES,
            "order": self.order,
        }
        if self.category == "seasonal" and is_anime_media(self.media_type):
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
        ctx.update(extras)
        return ctx


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

    if category == "seasonal" and is_anime_media(media_type):
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
def explore_type_redirect(request, media_type):
    """Redirect legacy /explore/<type> bookmarks to the medialist Browse tab."""
    tab = "discover" if request.GET.get("view") == "discover" else "browse"
    qs = request.GET.copy()
    qs.pop("view", None)
    qs["tab"] = tab
    base = reverse("medialist", args=[media_type])
    return redirect(f"{base}?{qs.urlencode()}")


@require_GET
def explore_section_redirect(request, media_type, section_key):  # noqa: ARG001
    """Redirect legacy /explore/<type>/section/<key> to the Discover tab."""
    base = reverse("medialist", args=[media_type])
    return redirect(f"{base}?tab=discover")


@require_GET
def medialist_browse_tab(request, media_type):
    """HTMX endpoint serving the Browse or Discover tab partial for medialist."""
    if request.GET.get("tab") == "discover":
        if config.get_discover_sections(media_type) is None:
            return redirect(reverse("medialist", args=[media_type]))
        from app.views.discover import render_discover  # noqa: PLC0415

        return render_discover(request, media_type)

    if config.get_explore_categories(media_type) is None:
        return redirect(reverse("medialist", args=[media_type]))

    return _render_browse_partial(request, media_type)


def _render_browse_partial(request, media_type):
    """Build the Browse-tab context and render the partial template."""
    categories = config.get_explore_categories(media_type)
    params = _parse_explore_params(request, categories)
    filter_definitions = config.get_explore_filters(media_type)
    active_filters = _extract_active_filters(request, filter_definitions)
    if active_filters.get("sort_by"):
        active_filters["order"] = params["order"]
    resolved_filters = (
        _resolve_filter_options(filter_definitions) if filter_definitions else None
    )
    expanded_filters = _get_expanded_filters(resolved_filters, active_filters)

    data, year, season_name = _fetch_browse_data(
        request,
        media_type,
        params["category"],
        active_filters,
        params["page"],
    )
    _annotate_tmdb_airing(data, media_type, params["category"])
    hide_watched_anime = _apply_hide_watched_anime(request, media_type, data)
    if data.get("results"):
        data["results"] = helpers.enrich_items_with_user_data(
            request,
            data["results"],
            "explore",
        )

    context = ExploreContext(
        data=data,
        media_type=media_type,
        categories=categories,
        category=params["category"],
        layout=params["layout"],
        order=params["order"],
        extra_params=_build_extra_params(
            active_filters,
            year,
            season_name,
            hide_watched_anime,
        ),
        hide_watched_anime=hide_watched_anime,
        resolved_filters=resolved_filters,
        active_filters=active_filters,
        expanded_filters=expanded_filters,
        year=year,
        season_name=season_name,
    ).to_template_context(
        has_discover=config.get_discover_sections(media_type) is not None,
        current_view="browse",
        text_color=config.get_text_color(media_type),
    )
    return render(request, "app/partials/medialist_browse_tab.html", context)


def _parse_explore_params(request, categories):
    """Extract category/page/layout/order GET params, defaulting to first category."""
    category = request.GET.get("category", categories[0]["slug"])
    if category not in {c["slug"] for c in categories}:
        category = categories[0]["slug"]
    return {
        "category": category,
        "page": int(request.GET.get("page", 1)),
        "layout": request.GET.get("layout", "list"),
        "order": request.GET.get("order", "desc"),
    }


VISIBLE_CHIP_COUNT = 12


def _get_expanded_filters(resolved_filters, active_filters):
    """Return set of filter keys that should start with chips expanded."""
    if not resolved_filters or not active_filters:
        return set()
    return {
        f["key"]
        for f in resolved_filters
        if _filter_has_overflow_selection(f, active_filters)
    }


def _filter_has_overflow_selection(filter_def, active_filters):
    """Whether any selected option for this filter falls in the overflow chips."""
    if filter_def.get("type") != "multi_select":
        return False
    selected = set(active_filters.get(filter_def["key"], "").split(","))
    selected.discard("")
    if not selected:
        return False
    overflow_values = {
        o["value"]
        for i, o in enumerate(filter_def.get("options", []))
        if i >= VISIBLE_CHIP_COUNT
    }
    return bool(selected & overflow_values)


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
