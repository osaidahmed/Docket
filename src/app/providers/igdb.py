import logging
from enum import IntEnum

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from app import helpers
from app.models import MediaTypes, Sources
from app.providers import services

logger = logging.getLogger(__name__)
base_url = "https://api.igdb.com/v4"


class ExternalGameSource(IntEnum):
    """External game source IDs from IGDB API."""

    STEAM = 1
    GOG = 5
    YOUTUBE = 10
    MICROSOFT = 11
    APPLE = 13
    TWITCH = 14
    ANDROID = 15
    AMAZON_ASIN = 20
    AMAZON_LUNA = 22
    AMAZON_ADG = 23
    EPIC_GAME_STORE = 26
    OCULUS = 28
    UTOMIK = 29
    ITCH_IO = 30
    XBOX_MARKETPLACE = 31
    KARTRIDGE = 32
    PLAYSTATION_STORE_US = 36
    FOCUS_ENTERTAINMENT = 37
    XBOX_GAME_PASS_ULTIMATE_CLOUD = 54
    GAMEJOLT = 55


def handle_error(error):
    """Handle IGDB API errors."""
    error_resp = error.response
    status_code = error_resp.status_code

    # Invalid access token, expired or revoked
    if status_code == requests.codes.unauthorized:
        logger.warning(
            "%s: Invalid access token, refreshing",
            Sources.IGDB.label,
        )
        cache.delete(f"{Sources.IGDB.value}_access_token")
        return {"retry": True}

    try:
        error_json = error_resp.json()
    except requests.exceptions.JSONDecodeError as json_error:
        logger.exception("Failed to decode JSON response")
        raise services.ProviderAPIError(Sources.IGDB.value, error) from json_error

    # Invalid keys
    if status_code in (requests.codes.bad_request, requests.codes.forbidden):
        try:
            details = error_json.get("message").capitalize()
            if details:
                raise services.ProviderAPIError(
                    Sources.IGDB.value,
                    error,
                    details,
                )
        # it can be other error format
        except (KeyError, AttributeError):
            logger.exception("Unexpected error format from IGDB API")
            raise services.ProviderAPIError(Sources.IGDB.value, error) from None

    raise services.ProviderAPIError(Sources.IGDB.value, error)


def get_access_token():
    """Return the access token for the IGDB API."""
    access_token = cache.get(f"{Sources.IGDB.value}_access_token")
    if access_token is None:
        url = "https://id.twitch.tv/oauth2/token"
        json = {
            "client_id": settings.IGDB_ID,
            "client_secret": settings.IGDB_SECRET,
            "grant_type": "client_credentials",
        }

        try:
            response = services.api_request(
                Sources.IGDB.value,
                "POST",
                url,
                params=json,
            )
        except requests.exceptions.HTTPError as error:
            handle_error(error)

        access_token = response["access_token"]
        cache.set(
            f"{Sources.IGDB.value}_access_token",
            access_token,
            response["expires_in"] - 60,
        )  # 1 min buffer to avoid using an expired token
    return access_token


def _igdb_request(url, data):
    """Make an IGDB API request with auth token and 401 retry."""
    access_token = get_access_token()
    headers = {
        "Client-ID": settings.IGDB_ID,
        "Authorization": f"Bearer {access_token}",
    }
    try:
        return services.api_request(
            Sources.IGDB.value,
            "POST",
            url,
            data=data,
            headers=headers,
        )
    except requests.exceptions.HTTPError as error:
        error_resp = handle_error(error)
        if error_resp and error_resp.get("retry"):
            headers["Authorization"] = f"Bearer {get_access_token()}"
            return services.api_request(
                Sources.IGDB.value,
                "POST",
                url,
                data=data,
                headers=headers,
            )
        raise


def _extract_multiquery_results(response, results_name, count_name):
    """Extract results and count from a multiquery response."""
    results = next(
        (item["result"] for item in response if item["name"] == results_name),
        [],
    )
    total = next(
        (item["count"] for item in response if item["name"] == count_name),
        0,
    )
    return results, total


def _format_game_results(search_results):
    """Format IGDB search/browse results into standard media dicts."""
    return [
        {
            "media_id": media["id"],
            "source": Sources.IGDB.value,
            "media_type": MediaTypes.GAME.value,
            "title": media["name"],
            "image": get_image_url(media),
            "synopsis": media.get("summary", ""),
        }
        for media in search_results
    ]


def external_game(external_id, source=ExternalGameSource.STEAM):
    """Find IGDB game by external ID using the external_game endpoint."""
    cache_key = f"external_game_{Sources.IGDB.value}_{source}_{external_id}"
    data = cache.get(cache_key)

    if data is None:
        query = (
            f'fields game; where uid = "{external_id}" & '
            f"external_game_source = {source};"
        )
        response = _igdb_request(f"{base_url}/external_games", query)

        if response and len(response) > 0:
            data = response[0].get("game")
            logger.debug(
                "Found IGDB match for external ID %s (source: %s): %s",
                external_id,
                source.name,
                data,
            )
        else:
            data = None
            logger.debug(
                "No IGDB match found for external ID %s (source: %s)",
                external_id,
                source.name,
            )

        cache.set(cache_key, data)

    return data


def search(query, page):
    """Search for games on IGDB using MultiQuery."""
    cache_key = f"search_{Sources.IGDB.value}_{MediaTypes.GAME.value}_{query}_{page}"
    data = cache.get(cache_key)

    if data is None:
        base_conditions = (
            f'where name ~ *"{query}"* & game_type = (0,1,2,3,4,5,6,7,8,9,10)'
        )
        if not settings.IGDB_NSFW:
            base_conditions += " & themes != (42)"

        offset = (page - 1) * settings.PER_PAGE
        multiquery = (
            'query games "SearchResults" {'
            "fields name,cover.image_id,summary;"
            "sort total_rating_count desc;"
            f"limit {settings.PER_PAGE};"
            f"offset {offset};"
            f"{base_conditions};"
            "};"
            'query games/count "TotalCount" {'
            f"{base_conditions};"
            "};"
        )

        response = _igdb_request(f"{base_url}/multiquery", multiquery)
        search_results, total_results = _extract_multiquery_results(
            response,
            "SearchResults",
            "TotalCount",
        )

        data = helpers.format_search_response(
            page,
            settings.PER_PAGE,
            total_results,
            _format_game_results(search_results),
        )
        cache.set(cache_key, data)

    return data


def browse(category, page):
    """Browse games on IGDB by category."""
    cache_key = f"browse_{Sources.IGDB.value}_{MediaTypes.GAME.value}_{category}_{page}"
    data = cache.get(cache_key)

    if data is None:
        now_timestamp = int(timezone.now().timestamp())
        offset = (page - 1) * settings.PER_PAGE
        query_clause = _build_category_query_clause(category, now_timestamp)
        multiquery = (
            'query games "BrowseResults" {'
            "fields name,cover.image_id,summary;"
            f"{query_clause}"
            f"limit {settings.PER_PAGE};"
            f"offset {offset};"
            "};"
            'query games/count "TotalCount" {'
            f"{query_clause}"
            "};"
        )

        response = _igdb_request(f"{base_url}/multiquery", multiquery)
        search_results, total_results = _extract_multiquery_results(
            response,
            "BrowseResults",
            "TotalCount",
        )

        data = helpers.format_search_response(
            page,
            settings.PER_PAGE,
            total_results,
            _format_game_results(search_results),
        )
        cache.set(cache_key, data)

    return data


def _build_category_query_clause(category, now_timestamp):
    """Build the IGDB where/sort clause for a browse category."""
    base_type_filter = "game_type = (0,1,2,3,4,5,6,7,8,9,10)"
    nsfw_filter = "" if settings.IGDB_NSFW else " & themes != (42)"
    queries = {
        "popular": (
            f"where {base_type_filter}{nsfw_filter}"
            " & total_rating_count > 50;"
            " sort total_rating_count desc;"
        ),
        "top_rated": (
            f"where {base_type_filter}{nsfw_filter}"
            " & total_rating_count > 100;"
            " sort total_rating desc;"
        ),
        "recent": (
            f"where {base_type_filter}{nsfw_filter}"
            f" & first_release_date < {now_timestamp}"
            " & first_release_date != null;"
            " sort first_release_date desc;"
        ),
        "anticipated": (
            f"where {base_type_filter}{nsfw_filter}"
            f" & first_release_date > {now_timestamp}"
            " & hypes > 0;"
            " sort hypes desc;"
        ),
    }
    return queries[category]


def browse_filtered(filters, page):
    """Browse games with filters using IGDB query language."""
    filter_hash = _build_browse_filter_hash(filters)
    cache_key = (
        f"browse_filtered_{Sources.IGDB.value}"
        f"_{MediaTypes.GAME.value}_{filter_hash}_{page}"
    )
    data = cache.get(cache_key)

    if data is None:
        offset = (page - 1) * settings.PER_PAGE
        where_clause = _build_filter_where_clause(filters)

        order = filters.get("order", "desc")
        sort_field_map = {
            "popularity": "total_rating_count",
            "rating": "total_rating",
            "date": "first_release_date",
            "hype": "hypes",
        }
        sort_field = sort_field_map.get(
            filters.get("sort_by", "popularity"),
            "total_rating_count",
        )
        sort = f"{sort_field} {order}"

        multiquery = (
            'query games "BrowseResults" {'
            f"fields name,cover.image_id,summary;"
            f"where {where_clause};"
            f"sort {sort};"
            f"limit {settings.PER_PAGE};"
            f"offset {offset};"
            "};"
            'query games/count "TotalCount" {'
            f"where {where_clause};"
            "};"
        )

        response = _igdb_request(f"{base_url}/multiquery", multiquery)
        search_results, total_results = _extract_multiquery_results(
            response,
            "BrowseResults",
            "TotalCount",
        )

        data = helpers.format_search_response(
            page,
            settings.PER_PAGE,
            total_results,
            _format_game_results(search_results),
        )
        cache.set(cache_key, data)

    return data


def _build_filter_where_clause(filters):
    """Build IGDB where clause from filter dict."""
    where_parts = ["game_type = (0,1,2,3,4,5,6,7,8,9,10)"]
    if not settings.IGDB_NSFW:
        where_parts.append("themes != (42)")
    if filters.get("genres"):
        where_parts.append(f"genres = ({filters['genres']})")
    if filters.get("themes"):
        where_parts.append(f"themes = ({filters['themes']})")
    if filters.get("platforms"):
        where_parts.append(f"platforms = ({filters['platforms']})")
    if filters.get("min_score"):
        where_parts.append(f"total_rating >= {float(filters['min_score'])}")
        where_parts.append("total_rating_count > 5")
    return " & ".join(where_parts)


def _get_enum_list(endpoint, cache_key, extra_filter=None):
    """Fetch an IGDB enum list (genres, platforms, themes)."""
    data = cache.get(cache_key)
    if data is None:
        where = f"where {extra_filter}; " if extra_filter else ""
        query = f"fields id,name; {where}sort name asc; limit 500;"
        response = _igdb_request(f"{base_url}/{endpoint}", query)
        data = [{"id": item["id"], "name": item["name"]} for item in response]
        cache.set(cache_key, data, timeout=60 * 60 * 24 * 7)
    return data


def get_genres():
    """Fetch genre list from IGDB."""
    return _get_enum_list("genres", "igdb_genres")


def get_themes():
    """Fetch theme list from IGDB."""
    return _get_enum_list("themes", "igdb_themes")


def get_platforms():
    """Fetch platform list from IGDB (main platform categories only)."""
    return _get_enum_list(
        "platforms", "igdb_platforms", extra_filter="category = (1,2,3,4,5,6)"
    )


def _build_browse_filter_hash(filters):
    parts = [f"{key}={filters[key]}" for key in sorted(filters) if filters[key]]
    return "_".join(parts) if parts else "nofilter"


def game(media_id):
    """Return the metadata for the selected game from IGDB."""
    cache_key = f"{Sources.IGDB.value}_{MediaTypes.GAME.value}_{media_id}"
    data = cache.get(cache_key)
    if data is None:
        query = (
            "fields name,cover.image_id,artworks.image_id,"
            "url,summary,game_type,first_release_date,total_rating,total_rating_count,"
            "genres.name,themes.name,platforms.name,involved_companies.company.name,"
            "parent_game.name,parent_game.cover.image_id,"
            "remasters.name,remasters.cover.image_id,"
            "remakes.name,remakes.cover.image_id,"
            "expansions.name,expansions.cover.image_id,"
            "standalone_expansions.name,standalone_expansions.cover.image_id,"
            "expanded_games.name,expanded_games.cover.image_id,"
            "similar_games.name,similar_games.cover.image_id,"
            "dlcs.name,dlcs.cover.image_id;"
            f"where id = {media_id};"
        )
        response = _igdb_request(f"{base_url}/games", query)

        if not response:
            services.raise_not_found_error(Sources.IGDB.value, media_id, "game")

        data = _build_game_metadata(response[0])
        cache.set(cache_key, data)
    return data


def _build_game_metadata(response):
    """Build game metadata dict from IGDB API response."""
    return {
        "media_id": response["id"],
        "source": Sources.IGDB.value,
        "source_url": response["url"],
        "media_type": MediaTypes.GAME.value,
        "title": response["name"],
        "max_progress": None,
        "image": get_image_url(response),
        "synopsis": response.get("summary", "No synopsis available."),
        "genres": get_list(response, "genres"),
        "score": get_score(response),
        "score_count": response.get("total_rating_count"),
        "details": {
            "format": get_game_type(response["game_type"]),
            "release_date": get_start_date(response),
            "themes": get_list(response, "themes"),
            "platforms": get_list(response, "platforms"),
            "companies": get_companies(response),
        },
        "related": {
            "parent_game": get_parent(response.get("parent_game")),
            "remasters": get_related(response.get("remasters")),
            "remakes": get_related(response.get("remakes")),
            "expansions": get_related(response.get("expansions")),
            "dlcs": get_related(response.get("dlcs")),
            "standalone_expansions": get_related(
                response.get("standalone_expansions"),
            ),
            "expanded_games": get_related(response.get("expanded_games")),
            "recommendations": get_related(response.get("similar_games")),
        },
    }


def get_image_url(response):
    """Return the image URL for the media."""
    # when no image, cover is not present in the response
    # e.g game: 287348
    try:
        return f"https://images.igdb.com/igdb/image/upload/t_original/{response['cover']['image_id']}.jpg"
    except KeyError:
        return settings.IMG_NONE


def get_game_type(game_type_id):
    """Return the game_type of the game."""
    game_type_mapping = {
        0: "Main game",
        1: "DLC",
        2: "Expansion",
        3: "Bundle",
        4: "Standalone expansion",
        5: "Mod",
        6: "Episode",
        7: "Season",
        8: "Remake",
        9: "Remaster",
        10: "Expanded game",
        11: "Port",
        12: "Fork",
        13: "Pack",
        14: "Update",
    }
    return game_type_mapping.get(game_type_id)


def _safe_extract(response, key, transform):
    try:
        return transform(response[key])
    except KeyError:
        return None


def get_start_date(response):
    """Return the start date of the game."""
    # when no release date, first_release_date is not present in the response
    # e.g game: 210710
    try:
        return timezone.datetime.fromtimestamp(
            response["first_release_date"],
            tz=timezone.get_current_timezone(),
        ).strftime("%Y-%m-%d")
    except KeyError:
        return None


def get_list(response, field):
    """Return the list of names from a list of dictionaries."""
    # when no data of field, field is not present in the response
    # e.g game: 25222
    return _safe_extract(
        response, field, lambda items: [item["name"] for item in items]
    )


def get_companies(response):
    """Return the companies involved in the game."""
    # when no companies, involved_companies is not present in the response
    # e.g game: 238417
    companies = response.get("involved_companies")
    if companies is None:
        return None
    return ", ".join(c["company"]["name"] for c in companies)


def get_score(response):
    """Return the score of the game."""
    # when no score, total_rating is not present in the response
    try:
        score = response["total_rating"]  # returns e.g 92.70730625238252
        return round(score / 10, 1)
    except KeyError:
        return None


def get_parent(parent_game):
    """Return the parent game to the selected game."""
    if parent_game:
        return [
            {
                "source": Sources.IGDB.value,
                "media_id": parent_game["id"],
                "media_type": MediaTypes.GAME.value,
                "title": parent_game["name"],
                "image": get_image_url(parent_game),
            },
        ]
    return []


def get_related(related_medias):
    """Return the related games to the selected game."""
    if related_medias:
        return [
            {
                "source": Sources.IGDB.value,
                "media_id": game["id"],
                "media_type": MediaTypes.GAME.value,
                "title": game["name"],
                "image": get_image_url(game),
            }
            for game in related_medias
        ]
    return []
