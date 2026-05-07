"""News aggregator view: pure cache reads, warmed by Celery beat."""

from django.core.cache import cache
from django.shortcuts import render
from django.views.decorators.http import require_GET

from app._news_config import (
    get_news_sources,
    supports_per_item_news,
)
from app.models import MediaTypes
from app.news_tasks import selection_cache_key
from app.providers.news_per_item import cache_key as item_cache_key
from app.providers.news_rss import get_industry_articles


@require_GET
def news(request):
    """Render the news aggregator page from cached articles."""
    enabled = request.user.get_enabled_media_types()
    industry_lanes = _build_industry_lanes(enabled)
    library_lanes = _build_library_lanes(enabled)
    return render(
        request,
        "app/news.html",
        {
            "industry_lanes": industry_lanes,
            "library_lanes": library_lanes,
            "all_empty": not industry_lanes and not library_lanes,
        },
    )


def _build_industry_lanes(enabled_types):
    """Build cross-type lanes of cached industry RSS articles. Empty lanes skipped."""
    lanes = []
    for mt in enabled_types:
        if not get_news_sources(mt):
            continue
        articles = get_industry_articles(mt)
        if not articles:
            continue
        lanes.append(
            {
                "media_type": mt,
                "label": MediaTypes(mt).label,
                "articles": articles,
                "empty": False,
            }
        )
    return lanes


def _build_library_lanes(enabled_types):
    """Build per-type lanes of cached news for spotlighted tracked items."""
    lanes = []
    for mt in enabled_types:
        lane = _library_lane_for(mt)
        if lane is not None:
            lanes.append(lane)
    return lanes


def _library_lane_for(media_type):
    """Return a single library-news lane dict, or None if unsupported/empty."""
    if not supports_per_item_news(media_type):
        return None
    selection = cache.get(selection_cache_key(media_type)) or []
    articles = []
    for media_id in selection:
        articles.extend(cache.get(item_cache_key(media_type, media_id)) or [])
    if not selection and not articles:
        return None
    return {
        "media_type": media_type,
        "label": MediaTypes(media_type).label,
        "articles": articles,
        "empty": not articles,
    }
