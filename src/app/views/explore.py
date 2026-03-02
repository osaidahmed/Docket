from django.apps import apps
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET

from app import config, helpers
from app.models import MediaTypes
from app.providers import services
from app.services.recommendations import _add_title_variants, _matches_cross_media


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


@require_GET
def explore_type(request, media_type):
    """Browse media of a specific type by category."""
    categories = config.get_explore_categories(media_type)
    if categories is None:
        return redirect("explore")

    category = request.GET.get("category", categories[0]["slug"])
    page = int(request.GET.get("page", 1))
    layout = request.GET.get("layout", "list")

    valid_slugs = {c["slug"] for c in categories}
    if category not in valid_slugs:
        category = categories[0]["slug"]

    extra_params = ""
    if category == "seasonal" and media_type == MediaTypes.ANIME.value:
        default_year, default_season = config.get_current_anime_season()
        year = int(request.GET.get("year", default_year))
        season_name = request.GET.get("season", default_season)
        data = services.browse(
            media_type, category, page, year=year, season=season_name
        )
        extra_params = f"&year={year}&season={season_name}"
    else:
        data = services.browse(media_type, category, page)
        year = None
        season_name = None

    hide_watched_anime = (
        media_type == MediaTypes.MANGA.value
        and request.GET.get("hide_watched_anime") == "1"
    )

    if hide_watched_anime and data.get("results"):
        cross_media_titles = set()
        anime_model = apps.get_model(app_label="app", model_name=MediaTypes.ANIME.value)
        anime_items = anime_model.objects.filter(
            user=request.user
        ).select_related("item")
        for m in anime_items:
            _add_title_variants(cross_media_titles, m.item.title)
            if m.item.english_title:
                _add_title_variants(cross_media_titles, m.item.english_title)
        data["results"] = [
            r for r in data["results"]
            if not _matches_cross_media(
                r.get("title", "").strip().lower(), cross_media_titles
            )
        ]

    if data.get("results"):
        data["results"] = helpers.enrich_items_with_user_data(
            request, data["results"], "explore"
        )

    if hide_watched_anime:
        extra_params += "&hide_watched_anime=1"

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
