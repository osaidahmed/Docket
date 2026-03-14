import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from django.core.cache import cache

from app import helpers
from app.models import MediaTypes, Sources
from app.providers import services

_ONGOING_ANIME_STATUSES = frozenset({"currently_airing"})


def _is_ongoing(node, media_type):
    """Determine if a browse/search item is ongoing.

    For manga, mirrors the backlog logic: unknown chapter count = ongoing.
    For anime, uses the API airing status.
    """
    if media_type == MediaTypes.MANGA.value:
        return not node.get("num_chapters")
    return node.get("status") in _ONGOING_ANIME_STATUSES


logger = logging.getLogger(__name__)
base_url = "https://api.myanimelist.net/v2"
base_fields = "title,alternative_titles,main_picture,media_type,start_date,end_date,synopsis,status,genres,mean,num_scoring_users,recommendations{node{alternative_titles}}"  # noqa: E501


def handle_error(error):
    """Handle MAL API errors."""
    error_resp = error.response
    status_code = error_resp.status_code

    if status_code == requests.codes.forbidden:
        raise services.ProviderAPIError(
            Sources.MAL.value,
            error,
            "API key is missing",
        )

    error_json = _parse_error_json(error)
    if status_code == requests.codes.bad_request and error_json:
        return _handle_bad_request(error, error_json)

    raise services.ProviderAPIError(Sources.MAL.value, error)


def _parse_error_json(error):
    try:
        return error.response.json()
    except requests.exceptions.JSONDecodeError as json_error:
        logger.exception("Failed to decode JSON response")
        raise services.ProviderAPIError(Sources.MAL.value, error) from json_error


def _handle_bad_request(error, error_json):
    error_message = error_json.get("message")
    if error_message == "Invalid client id":
        raise services.ProviderAPIError(
            Sources.MAL.value,
            error,
            "Invalid API key",
        )
    if error_message == "invalid q":
        return {"data": []}
    raise services.ProviderAPIError(Sources.MAL.value, error)


def _mal_request(url, params):
    """Make a MAL API request with error handling."""
    if settings.MAL_NSFW:
        params["nsfw"] = "true"
    try:
        return services.api_request(
            Sources.MAL.value,
            "GET",
            url,
            params=params,
            headers={"X-MAL-CLIENT-ID": settings.MAL_API},
        )
    except requests.exceptions.HTTPError as error:
        return handle_error(error)


def _build_media_result(node, media_type):
    """Build a standard media result dict from a MAL node."""
    return {
        "media_id": node["id"],
        "source": Sources.MAL.value,
        "media_type": media_type,
        "title": node["title"],
        "english_title": get_english_title(node),
        "image": get_image_url(node),
        "synopsis": node.get("synopsis", ""),
        "is_ongoing": _is_ongoing(node, media_type),
    }


def search(media_type, query, page):
    """Search for media on MyAnimeList."""
    cache_key = f"search_{Sources.MAL.value}_{media_type}_{query}_{page}"
    data = cache.get(cache_key)

    if data is None:
        response = _mal_request(
            f"{base_url}/{media_type}",
            {
                "q": query,
                "fields": "media_type,synopsis,alternative_titles,status,num_chapters",
                "limit": settings.PER_PAGE,
            },
        )

        results = [
            _build_media_result(entry["node"], media_type) for entry in response["data"]
        ]

        data = helpers.format_search_response(page, 100, len(results), results)
        cache.set(cache_key, data)

    return data


def _paginate_response(response, page, offset, results):
    """Build paginated search response from MAL API response."""
    has_next = "next" in response.get("paging", {})
    if has_next:
        total_results = max(offset + settings.PER_PAGE * 5, len(results))
        total_exact = False
    else:
        total_results = offset + len(results)
        total_exact = True
    return helpers.format_search_response(
        page,
        settings.PER_PAGE,
        total_results,
        results,
        total_exact=total_exact,
    )


def browse(media_type, category, page):
    """Browse ranked media on MyAnimeList."""
    cache_key = f"browse_{Sources.MAL.value}_{media_type}_{category}_{page}"
    data = cache.get(cache_key)

    if data is None:
        offset = (page - 1) * settings.PER_PAGE
        response = _mal_request(
            f"{base_url}/{media_type}/ranking",
            {
                "ranking_type": category,
                "fields": "media_type,synopsis,alternative_titles,status,num_chapters",
                "limit": settings.PER_PAGE,
                "offset": offset,
            },
        )

        results = [
            _build_media_result(entry["node"], media_type) for entry in response["data"]
        ]
        data = _paginate_response(response, page, offset, results)
        cache.set(cache_key, data)

    return data


def browse_seasonal(year, season, page):
    """Browse seasonal anime on MyAnimeList."""
    cache_key = f"browse_{Sources.MAL.value}_anime_seasonal_{year}_{season}_{page}"
    data = cache.get(cache_key)

    if data is None:
        offset = (page - 1) * settings.PER_PAGE
        response = _mal_request(
            f"{base_url}/anime/season/{year}/{season}",
            {
                "fields": "media_type,synopsis,alternative_titles,status",
                "sort": "anime_num_list_users",
                "limit": settings.PER_PAGE,
                "offset": offset,
            },
        )

        results = [
            _build_media_result(entry["node"], MediaTypes.ANIME.value)
            for entry in response["data"]
        ]
        data = _paginate_response(response, page, offset, results)
        cache.set(cache_key, data)

    return data


def _needs_relationship_refetch(data):
    """Check if cached data is stale (missing relation_type on related anime)."""
    related = data.get("related", {}).get("related_anime", [])
    return related and any("relation_type" not in r for r in related)


def anime(media_id):
    """Return the metadata for the selected anime from MyAnimeList."""
    cache_key = f"{Sources.MAL.value}_{MediaTypes.ANIME.value}_{media_id}"
    data = cache.get(cache_key)

    if data is not None and _needs_relationship_refetch(data):
        data = None

    if data is None:
        response = _mal_request(
            f"{base_url}/anime/{media_id}",
            {
                "fields": f"{base_fields},num_episodes,average_episode_duration,studios,start_season,broadcast,source,related_anime{{node{{alternative_titles}}}}",  # noqa: E501
            },
        )

        num_episodes = get_number_of_episodes(response)
        data = _build_metadata_base(response, media_id, MediaTypes.ANIME.value)
        data["max_progress"] = num_episodes
        data["is_ongoing"] = response.get("status") in (
            "currently_airing",
            "not_yet_aired",
        )
        data["details"].update(
            {
                "episodes": num_episodes,
                "runtime": get_runtime(response),
                "studios": get_studios(response),
                "season": get_season(response),
                "broadcast": get_broadcast(response),
                "source": get_source(response),
            }
        )
        related_anime = get_related(
            response.get("related_anime"),
            MediaTypes.ANIME.value,
        )
        data["related"] = {
            "related_anime": related_anime,
            "recommendations": get_related(
                response.get("recommendations"),
                MediaTypes.ANIME.value,
            ),
        }
        _save_anime_relationships(media_id, related_anime)
        cache.set(cache_key, data)

    return data


def manga(media_id):
    """Return the metadata for the selected manga from MyAnimeList."""
    cache_key = f"{Sources.MAL.value}_{MediaTypes.MANGA.value}_{media_id}"
    data = cache.get(cache_key)

    if data is None:
        response = _mal_request(
            f"{base_url}/manga/{media_id}",
            {
                "fields": f"{base_fields},num_chapters,related_manga{{node{{alternative_titles}}}}",  # noqa: E501
            },
        )

        num_chapters = get_number_of_episodes(response)
        data = _build_metadata_base(response, media_id, MediaTypes.MANGA.value)
        data["max_progress"] = num_chapters
        data["details"]["number_of_chapters"] = num_chapters
        data["related"] = {
            "related_manga": get_related(
                response.get("related_manga"),
                MediaTypes.MANGA.value,
            ),
            "recommendations": get_related(
                response.get("recommendations"),
                MediaTypes.MANGA.value,
            ),
        }
        cache.set(cache_key, data)

    return data


def _build_metadata_base(response, media_id, media_type):
    """Build shared metadata dict for anime/manga."""
    slug = "anime" if media_type == MediaTypes.ANIME.value else "manga"
    return {
        "media_id": media_id,
        "source": Sources.MAL.value,
        "source_url": f"https://myanimelist.net/{slug}/{media_id}",
        "media_type": media_type,
        "title": response["title"],
        "english_title": get_english_title(response),
        "image": get_image_url(response),
        "synopsis": get_synopsis(response),
        "genres": get_genres(response),
        "score": get_score(response),
        "score_count": get_score_count(response),
        "details": {
            "format": get_format(response),
            "start_date": response.get("start_date"),
            "end_date": response.get("end_date"),
            "status": get_readable_status(response),
        },
    }


def get_format(response):
    """Return the original type of the media."""
    media_format = response["media_type"]

    # MAL return tv in metadata for anime
    if media_format == "tv":
        return "Anime"
    if media_format in ("ova", "ona"):
        return media_format.upper()
    return media_format.replace("_", " ").title()


def get_image_url(response):
    """Return the image URL for the media."""
    # when no picture, main_picture is not present in the response
    # e.g anime: 38869
    try:
        return response["main_picture"]["large"]
    except KeyError:
        return settings.IMG_NONE


def get_readable_status(response):
    """Return the status in human-readable format."""
    # Map status to human-readable values
    status_map = {
        "finished_airing": "Finished",
        "currently_airing": "Airing",
        "not_yet_aired": "Upcoming",
        "finished": "Finished",
        "currently_publishing": "Publishing",
        "not_yet_published": "Upcoming",
        "on_hiatus": "On Hiatus",
        "discontinued": "Discontinued",
    }
    if response["status"] in status_map:
        return status_map[response["status"]]
    return response["status"].replace("_", " ").title()


def get_synopsis(response):
    """Add the synopsis to the response."""
    # when no synopsis, value from response is empty string
    # e.g manga: 160219
    if response["synopsis"] == "":
        return "No synopsis available."
    return response["synopsis"]


def get_number_of_episodes(response):
    """Return the number of episodes for the media."""
    # when unknown episodes, value from response is 0
    # e.g manga: 160219
    try:
        episodes = response["num_episodes"]
    except KeyError:
        episodes = response["num_chapters"]

    return episodes if episodes != 0 else None


def get_runtime(response):
    """Return the average episode duration."""
    # when unknown duration, value from response is 0
    # e.g anime: 43333
    duration = response["average_episode_duration"]

    # Convert average_episode_duration to hours and minutes
    if duration:
        # duration are in seconds
        hours, minutes = divmod(int(duration / 60), 60)
        return f"{hours}h {minutes}m" if hours > 0 else f"{minutes} min"
    return None


def get_genres(response):
    """Return the genres for the media."""
    # when unknown genres, genres key is not present in the response
    # e.g manga: 151971
    if response.get("genres"):
        return [genre["name"] for genre in response["genres"]]
    return None


def get_studios(response):
    """Return the studios for the media."""
    # when unknown studio, studios is an empty list
    # e.g anime: 43333

    if response["studios"]:
        return [studio["name"] for studio in response["studios"]]
    return None


def get_season(response):
    """Return the season for the media."""
    # when unknown start season, no start_season key in response
    # e.g anime: 43333
    try:
        season = response["start_season"]
        return f"{season['season'].title()} {season['year']}"
    except KeyError:
        return None


def get_broadcast(response):
    """Return the broadcast day and time for the media."""
    start_date = response.get("start_date")
    if not start_date:
        return None

    # when unknown broadcast, value is not present in the response
    # e.g anime: 38869
    broadcast = response.get("broadcast")
    if not broadcast:
        return None

    # when unknown start time, value is not present in the broadcast dict
    start_time = broadcast.get("start_time") if broadcast else None
    if not start_time:
        return None

    japan_timezone = ZoneInfo("Asia/Tokyo")
    # Try parsing with different date formats
    try:
        date_obj = datetime.strptime(start_date, "%Y-%m-%d").replace(
            tzinfo=japan_timezone,
        )
    except ValueError:
        date_obj = datetime.strptime(start_date, "%Y-%m").replace(tzinfo=japan_timezone)

    broadcast_time_japan = datetime.strptime(
        f"{date_obj.strftime('%Y-%m-%d')} {start_time}",
        "%Y-%m-%d %H:%M",
    ).replace(tzinfo=japan_timezone)

    broadcast_time_local = broadcast_time_japan.astimezone(settings.TZ)
    return broadcast_time_local.strftime("%A %H:%M")


def get_source(response):
    """Return the source for the media."""
    # when unknown source, value from response is empty string
    # e.g anime: 32253
    try:
        return response["source"].replace("_", " ").title()
    except KeyError:
        return None


def get_score(response):
    """Return the score for the media."""
    # when num_scoring_users is small, the response does not include this field.
    try:
        return round(response["mean"], 1)
    except KeyError:
        return None


def get_score_count(response):
    """Return the score count for the media."""
    if get_score(response):
        return response["num_scoring_users"]
    return 0


def get_english_title(response):
    """Return the English title if available and different from the main title."""
    alt_titles = response.get("alternative_titles", {})
    en_title = alt_titles.get("en", "")
    if en_title and en_title != response.get("title", ""):
        return en_title
    return ""


def get_related(related_medias, media_type):
    """Return list of related media for the selected media."""
    if related_medias:
        return [
            {
                "media_id": media["node"]["id"],
                "source": Sources.MAL.value,
                "title": media["node"]["title"],
                "english_title": get_english_title(media["node"]),
                "media_type": media_type,
                "image": get_image_url(media["node"]),
                "relation_type": media.get("relation_type", ""),
            }
            for media in related_medias
        ]
    return []


_GROUPING_RELATION_TYPES = frozenset({"sequel", "prequel"})


def _save_anime_relationships(media_id, related_anime):
    """Persist sequel/prequel relationships from MAL API data."""
    from app.models import Item, ItemRelationship  # noqa: PLC0415

    groupable = [
        r for r in related_anime if r.get("relation_type") in _GROUPING_RELATION_TYPES
    ]
    if not groupable:
        return

    try:
        from_item = Item.objects.get(
            media_id=str(media_id),
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
        )
    except Item.DoesNotExist:
        return

    for related in groupable:
        to_item, _ = Item.objects.get_or_create(
            media_id=str(related["media_id"]),
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            defaults={
                "title": related.get("title", "-"),
                "image": related.get("image", settings.IMG_NONE),
            },
        )
        ItemRelationship.objects.get_or_create(
            from_item=from_item,
            to_item=to_item,
            relation_type=related["relation_type"],
        )
