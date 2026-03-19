from urllib.parse import parse_qsl, urlencode, urlparse

from django.apps import apps
from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.utils.encoding import iri_to_uri
from django.utils.http import url_has_allowed_host_and_scheme

from app.models import BasicMedia, MediaTypes, Status

VALID_MEDIA_TYPES = frozenset(MediaTypes.values)


def get_media_model(media_type):
    """Return the Django model for a validated media type, or raise Http404."""
    from django.http import Http404  # noqa: PLC0415

    if media_type not in VALID_MEDIA_TYPES:
        msg = f"Invalid media type: {media_type}"
        raise Http404(msg)
    return apps.get_model(app_label="app", model_name=media_type)


def minutes_to_hhmm(total_minutes):
    """Convert total minutes to HH:MM format."""
    hours = int(total_minutes / 60)
    minutes = int(total_minutes % 60)
    if hours == 0:
        return f"{minutes}min"
    return f"{hours}h {minutes:02d}min"


def redirect_back(request):
    """Redirect to the previous page, removing the 'page' parameter if present."""
    if url_has_allowed_host_and_scheme(request.GET.get("next"), None):
        next_url = request.GET["next"]

        # Parse the URL
        parsed_url = urlparse(next_url)

        # Get the query parameters and remove params we don't want
        query_params = dict(parse_qsl(parsed_url.query, keep_blank_values=True))
        query_params.pop("page", None)
        query_params.pop("load_media_type", None)

        # Reconstruct the URL
        new_query = urlencode(query_params)
        new_parts = list(parsed_url)
        new_parts[4] = new_query  # index 4 is the query part

        # Convert back to a URL string
        clean_url = iri_to_uri(parsed_url._replace(query=new_query).geturl())

        return HttpResponseRedirect(clean_url)

    return redirect("home")


def form_error_messages(form, request):
    """Display form errors as messages."""
    for field, errors in form.errors.items():
        for error in errors:
            messages.error(
                request,
                f"{field.replace('_', ' ').title()}: {error}",
            )


def format_search_response(
    page, per_page, total_results, results, *, total_exact=True, max_pages=None
):
    """Format the search response for pagination."""
    total_pages = total_results // per_page + 1
    if max_pages is not None:
        total_pages = min(total_pages, max_pages)
    return {
        "page": page,
        "total_results": total_results,
        "total_pages": total_pages,
        "total_exact": total_exact,
        "results": results,
    }


def _media_key(item, is_season):
    if is_season:
        return (item.media_id, item.source, item.season_number)
    return (item.media_id, item.source)


def _item_key(item, is_season):
    if is_season:
        return (str(item["media_id"]), item["source"], item.get("season_number"))
    return (str(item["media_id"]), item["source"])


def enrich_items_with_user_data(request, items, section_name):
    """Enrich a list of items with user tracking data."""
    if not items:
        return []

    media_lookup, has_active_lookup, is_season = _build_media_lookup(
        items, request.user
    )
    return _apply_enrichment(
        items, media_lookup, has_active_lookup, is_season, request, section_name
    )


def _build_media_lookup(items, user):
    media_type = items[0]["media_type"]
    source = items[0]["source"]
    is_season = media_type == MediaTypes.SEASON.value

    q_objects = Q()
    for item in items:
        filter_params = {
            "item__media_id": item["media_id"],
            "item__media_type": media_type,
            "item__source": source,
        }
        if is_season:
            filter_params["item__season_number"] = item.get("season_number")
        q_objects |= Q(**filter_params)

    q_objects &= Q(user=user)

    model = apps.get_model(app_label="app", model_name=media_type)
    media_queryset = model.objects.filter(q_objects).select_related("item")
    media_queryset = BasicMedia.objects._apply_prefetch_related(
        media_queryset, media_type
    )
    BasicMedia.objects.annotate_max_progress(media_queryset, media_type)

    active_statuses = {
        Status.IN_PROGRESS.value,
        Status.PLANNING.value,
        Status.PAUSED.value,
    }
    media_lookup = {}
    has_active_lookup = {}
    for media in media_queryset:
        key = _media_key(media.item, is_season)
        if _should_replace(media_lookup.get(key), media, active_statuses):
            media_lookup[key] = media
        if media.status in active_statuses:
            has_active_lookup[key] = True

    return media_lookup, has_active_lookup, is_season


def _should_replace(existing, candidate, active_statuses):
    if existing is None:
        return True
    if candidate.status == Status.COMPLETED.value:
        return existing.status != Status.COMPLETED.value
    return (
        candidate.status not in active_statuses and existing.status in active_statuses
    )


def _apply_enrichment(
    items, media_lookup, has_active_lookup, is_season, request, section_name
):
    hide_completed = (
        request.user.hide_completed_recommendations
        and section_name == "recommendations"
    )
    enriched_items = []
    for item in items:
        key = _item_key(item, is_season)
        media_item = media_lookup.get(key)
        if (
            hide_completed
            and media_item
            and media_item.status == Status.COMPLETED.value
        ):
            continue
        enriched_items.append(
            {
                "item": item,
                "media": media_item,
                "has_active": has_active_lookup.get(key, False),
            }
        )
    return enriched_items
