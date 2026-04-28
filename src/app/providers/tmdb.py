import logging
from datetime import UTC, datetime

import requests
from django.conf import settings
from django.core.cache import cache

from app import helpers
from app.models import MediaTypes, Sources
from app.providers import services

logger = logging.getLogger(__name__)
base_url = "https://api.themoviedb.org/3"
base_params = {
    "api_key": settings.TMDB_API,
    "language": settings.TMDB_LANG,
}


def handle_error(error):
    """Handle TMDB API errors."""
    error_resp = error.response
    status_code = error_resp.status_code

    try:
        error_json = error_resp.json()
    except requests.exceptions.JSONDecodeError as json_error:
        logger.exception("Failed to decode JSON response")
        raise services.ProviderAPIError(Sources.TMDB.value, error) from json_error

    # Handle authentication errors
    if status_code == requests.codes.unauthorized:
        details = error_json.get("status_message")
        if details:
            # Remove trailing period if present
            details = details.rstrip(".")
            raise services.ProviderAPIError(Sources.TMDB.value, error, details)

    raise services.ProviderAPIError(
        Sources.TMDB.value,
        error,
    )


def get_external_links(external_ids):
    """Build external links dictionary from TMDB external_ids response."""
    links = {}

    if external_ids.get("imdb_id"):
        links["IMDb"] = f"https://www.imdb.com/title/{external_ids['imdb_id']}/"

    if external_ids.get("tvdb_id"):
        links["TVDB"] = (
            f"https://www.thetvdb.com/dereferrer/series/{external_ids['tvdb_id']}"
        )

    if external_ids.get("wikidata_id"):
        links["Wikidata"] = (
            f"https://www.wikidata.org/wiki/{external_ids['wikidata_id']}"
        )

    return links


def search(media_type, query, page):
    """Search for media on TMDB."""
    cache_key = f"search_{Sources.TMDB.value}_{media_type}_{query}_{page}"
    data = cache.get(cache_key)

    if data is None:
        url = f"{base_url}/search/{media_type}"

        params = {
            **base_params,
            "query": query,
            "page": page,
        }

        if settings.TMDB_NSFW:
            params["include_adult"] = "true"

        try:
            response = services.api_request(
                Sources.TMDB.value,
                "GET",
                url,
                params=params,
            )
        except requests.exceptions.HTTPError as error:
            handle_error(error)

        results = [
            {
                "media_id": media["id"],
                "source": Sources.TMDB.value,
                "media_type": media_type,
                "title": get_title(media),
                "image": get_image_url(media["poster_path"]),
                "synopsis": media.get("overview", ""),
            }
            for media in response["results"]
        ]

        total_results = response["total_results"]
        per_page = 20  # TMDB always returns 20 results per page
        data = helpers.format_search_response(
            page,
            per_page,
            total_results,
            results,
        )

        cache.set(cache_key, data)

    return data


def search_multi(query, limit=5):
    """Search TMDB for TV and movie results using the multi endpoint."""
    cache_key = f"suggest_{Sources.TMDB.value}_multi_{query}_{limit}"
    data = cache.get(cache_key)
    if data is None:
        url = f"{base_url}/search/multi"
        params = {**base_params, "query": query, "page": 1}
        if settings.TMDB_NSFW:
            params["include_adult"] = "true"
        try:
            response = services.api_request(
                Sources.TMDB.value,
                "GET",
                url,
                params=params,
            )
        except requests.exceptions.HTTPError as error:
            handle_error(error)
        filtered = [
            {
                "media_id": media["id"],
                "source": Sources.TMDB.value,
                "media_type": media["media_type"],
                "title": get_title(media),
                "image": get_image_url(media.get("poster_path")),
            }
            for media in response["results"]
            if media.get("media_type") in ("tv", "movie")
        ]
        data = filtered[:limit]
        cache.set(cache_key, data)
    return data


def get_backdrop_url(path):
    """Return a landscape backdrop URL for carousel use."""
    if path:
        return f"https://image.tmdb.org/t/p/w1280{path}"
    return None


def _format_browse_result(media, media_type, *, include_backdrop=False):
    """Format a single TMDB browse result into Docket's standard format."""
    result = {
        "media_id": media["id"],
        "source": Sources.TMDB.value,
        "media_type": media_type,
        "title": get_title(media),
        "image": get_image_url(media["poster_path"]),
        "synopsis": media.get("overview", ""),
    }
    if include_backdrop:
        result["backdrop"] = get_backdrop_url(media.get("backdrop_path"))
    return result


def find(external_id, external_source):
    """Search for media on TMDB."""
    cache_key = f"find_{Sources.TMDB.value}_{external_id}_{external_source}"
    data = cache.get(cache_key)

    if data is None:
        url = f"{base_url}/find/{external_id}"

        params = {
            **base_params,
            "external_source": external_source,
        }

        try:
            response = services.api_request(
                Sources.TMDB.value,
                "GET",
                url,
                params=params,
            )
        except requests.exceptions.HTTPError as error:
            handle_error(error)

        cache.set(cache_key, response)
        return response

    return data


def movie(media_id):
    """Return the metadata for the selected movie from The Movie Database."""
    cache_key = f"{Sources.TMDB.value}_{MediaTypes.MOVIE.value}_{media_id}"
    data = cache.get(cache_key)
    if data is None:
        url = f"{base_url}/movie/{media_id}"
        params = {
            **base_params,
            "append_to_response": "recommendations,external_ids,credits",
        }
        try:
            response = services.api_request(
                Sources.TMDB.value, "GET", url, params=params
            )
        except requests.exceptions.HTTPError as error:
            handle_error(error)
        data = _build_movie_metadata(media_id, response)
        cache.set(cache_key, data)
    return data


def _build_movie_metadata(media_id, response):
    """Assemble the cached metadata dict for a TMDB movie response."""
    collection_response = _fetch_movie_collection(response)
    collection_items = get_collection(collection_response)
    collection_ids = {item["media_id"] for item in collection_items}
    recommended_items = response.get("recommendations", {}).get("results", [])
    data = {
        "media_id": media_id,
        "source": Sources.TMDB.value,
        "source_url": f"https://www.themoviedb.org/movie/{media_id}",
        "media_type": MediaTypes.MOVIE.value,
        "title": response["title"],
        "max_progress": 1,
        "image": get_image_url(response["poster_path"]),
        "synopsis": response["overview"] or "No synopsis available.",
        "genres": get_genres(response["genres"]),
        "score": get_score(response["vote_average"]),
        "score_count": response["vote_count"],
        "details": {
            "format": "Movie",
            "release_date": response["release_date"] or None,
            "status": response["status"],
            "runtime": get_readable_duration(response["runtime"]),
            "studios": get_companies(response["production_companies"]),
            "country": get_country(response["production_countries"]),
            "languages": get_languages(response["spoken_languages"]),
        },
        "cast": _build_cast_list(response.get("credits", {})),
        "external_links": get_external_links(response.get("external_ids", {})),
    }
    data["related"] = {
        collection_response.get("name", "collection"): collection_items,
        "recommendations": get_related(
            [r for r in recommended_items if r["id"] not in collection_ids],
            MediaTypes.MOVIE.value,
        ),
    }
    return data


def _fetch_movie_collection(response):
    collection = response.get("belongs_to_collection")
    if not collection:
        return {}
    collection_id = collection.get("id")
    if not collection_id:
        return {}
    try:
        return services.api_request(
            Sources.TMDB.value,
            "GET",
            f"{base_url}/collection/{collection_id}",
            params={**base_params},
        )
    except requests.exceptions.HTTPError as error:
        logger.warning("Failed to get collection: %s", error)
        return {}


def _build_cast_list(credits_data, limit=10):
    return [
        {
            "id": member.get("id"),
            "name": member.get("name"),
            "character": member.get("character"),
            "image": get_image_url(member.get("profile_path")),
        }
        for member in credits_data.get("cast", [])[:limit]
    ]


def get_cached_seasons(media_id, season_numbers):
    """Check cache for seasons and return cached data and list of uncached seasons."""
    cached_data = {}
    uncached_seasons = []

    for season_number in season_numbers:
        season_cache_key = (
            f"{Sources.TMDB.value}_{MediaTypes.SEASON.value}_{media_id}_{season_number}"
        )
        season_data = cache.get(season_cache_key)
        if season_data:
            cached_data[f"season/{season_number}"] = season_data
        else:
            uncached_seasons.append(season_number)

    return cached_data, uncached_seasons


def enrich_season_with_tv_data(season_data, tv_data, media_id, season_number):
    """Add TV show metadata to season metadata."""
    season_data["media_id"] = media_id
    season_data["source_url"] = (
        f"https://www.themoviedb.org/tv/{media_id}/season/{season_number}"
    )
    season_data["title"] = tv_data["title"]
    season_data["tvdb_id"] = tv_data["tvdb_id"]
    season_data["external_links"] = tv_data["external_links"]
    season_data["genres"] = tv_data["genres"]
    if season_data["synopsis"] == "No synopsis available.":
        season_data["synopsis"] = tv_data["synopsis"]
    return season_data


def fetch_and_cache_seasons(media_id, season_numbers, tv_data):
    """Fetch uncached seasons from API and cache them."""
    url = f"{base_url}/tv/{media_id}"
    base_append = "recommendations,external_ids"
    max_seasons_per_request = 18
    fetched_tv_data = tv_data
    result_data = {}

    for i in range(0, len(season_numbers), max_seasons_per_request):
        season_subset = season_numbers[i : i + max_seasons_per_request]
        append_text = ",".join([f"season/{season}" for season in season_subset])

        params = {
            **base_params,
            "append_to_response": f"{base_append},{append_text}",
        }

        try:
            response = services.api_request(
                Sources.TMDB.value,
                "GET",
                url,
                params=params,
            )
        except requests.exceptions.HTTPError as error:
            handle_error(error)

        # Cache TV metadata if we haven't fetched it yet
        if fetched_tv_data is None:
            fetched_tv_data = process_tv(response)
            tv_cache_key = f"{Sources.TMDB.value}_{MediaTypes.TV.value}_{media_id}"
            cache.set(tv_cache_key, fetched_tv_data)

        # Process and cache each season
        for season_number in season_subset:
            season_key = f"season/{season_number}"
            if season_key not in response:
                msg = (
                    f"Season {season_number} not found in {Sources.TMDB.label} "
                    f"with ID {media_id}"
                )
                raise services.ProviderAPIError(msg, 404, msg)

            season_data = process_season(response[season_key])
            season_data = enrich_season_with_tv_data(
                season_data,
                fetched_tv_data,
                media_id,
                season_number,
            )

            cache.set(
                f"{Sources.TMDB.value}_{MediaTypes.SEASON.value}_{media_id}_{season_number}",
                season_data,
            )
            result_data[season_key] = season_data

    return result_data, fetched_tv_data


def tv_with_seasons(media_id, season_numbers):
    """Return the metadata for the tv show with seasons appended to the response."""
    if not season_numbers:
        return tv(media_id)

    tv_cache_key = f"{Sources.TMDB.value}_{MediaTypes.TV.value}_{media_id}"
    tv_data = cache.get(tv_cache_key)
    cached_seasons, uncached_seasons = get_cached_seasons(media_id, season_numbers)

    if not uncached_seasons:
        return (tv_data or tv(media_id)) | cached_seasons

    fetched_seasons, fetched_tv_data = fetch_and_cache_seasons(
        media_id, uncached_seasons, tv_data
    )
    cached_seasons.update(fetched_seasons)
    return (tv_data or fetched_tv_data) | cached_seasons


def tv(media_id):
    """Return the metadata for the selected tv show from The Movie Database."""
    cache_key = f"{Sources.TMDB.value}_{MediaTypes.TV.value}_{media_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = f"{base_url}/tv/{media_id}"
    params = {**base_params, "append_to_response": "recommendations,external_ids"}
    try:
        response = services.api_request(Sources.TMDB.value, "GET", url, params=params)
    except requests.exceptions.HTTPError as error:
        handle_error(error)
    data = process_tv(response)
    cache.set(cache_key, data)
    return data


def process_tv(response):
    """Process the metadata for the selected tv show from The Movie Database."""
    num_episodes = response["number_of_episodes"]
    next_episode = response.get("next_episode_to_air")
    last_episode = response.get("last_episode_to_air")
    return {
        "media_id": response["id"],
        "source": Sources.TMDB.value,
        "source_url": f"https://www.themoviedb.org/tv/{response['id']}",
        "media_type": MediaTypes.TV.value,
        "title": response["name"],
        "max_progress": num_episodes,
        "image": get_image_url(response["poster_path"]),
        "synopsis": response["overview"] or "No synopsis available.",
        "genres": get_genres(response["genres"]),
        "score": get_score(response["vote_average"]),
        "score_count": response["vote_count"],
        "details": _build_tv_details(response, num_episodes),
        "related": {
            "seasons": get_related(
                response["seasons"],
                MediaTypes.SEASON.value,
                response,
            ),
            "recommendations": get_related(
                response.get("recommendations", {}).get("results", []),
                MediaTypes.TV.value,
            ),
        },
        "tvdb_id": response.get("external_ids", {}).get("tvdb_id"),
        "external_links": get_external_links(response.get("external_ids", {})),
        "last_episode_season": last_episode["season_number"] if last_episode else None,
        "next_episode_season": next_episode["season_number"] if next_episode else None,
    }


def _build_tv_details(response, num_episodes):
    """Build the 'details' subdict for process_tv."""
    return {
        "format": "TV",
        "first_air_date": response["first_air_date"] or None,
        "last_air_date": response["last_air_date"],
        "status": response["status"],
        "seasons": response["number_of_seasons"],
        "episodes": num_episodes,
        "runtime": (
            get_readable_duration(response["episode_run_time"][0])
            if response["episode_run_time"]
            else None
        ),
        "studios": get_companies(response["production_companies"]),
        "country": get_country(response["production_countries"]),
        "languages": get_languages(response["spoken_languages"]),
    }


def process_season(response):
    """Process the metadata for the selected season from The Movie Database."""
    episodes = response["episodes"]
    avg_runtime, total_runtime, score_count = _aggregate_episode_stats(episodes)
    today_str = datetime.now(tz=UTC).date().isoformat()
    aired_episodes = [
        ep for ep in episodes if ep.get("air_date") and ep["air_date"] <= today_str
    ]
    return {
        "source": Sources.TMDB.value,
        "media_type": MediaTypes.SEASON.value,
        "season_title": response["name"],
        "max_progress": aired_episodes[-1]["episode_number"] if aired_episodes else 0,
        "image": get_image_url(response["poster_path"]),
        "season_number": response["season_number"],
        "synopsis": response["overview"] or "No synopsis available.",
        "score": get_score(response["vote_average"]),
        "score_count": score_count,
        "details": {
            "first_air_date": response["air_date"] or None,
            "last_air_date": (
                response["episodes"][-1]["air_date"] if response["episodes"] else None
            ),
            "episodes": len(episodes),
            "runtime": avg_runtime,
            "total_runtime": total_runtime,
        },
        "episodes": response["episodes"],
    }


def _aggregate_episode_stats(episodes):
    """Return (avg_runtime, total_runtime, score_count) across episodes."""
    runtimes = []
    total_runtime = 0
    score_count = 0
    for ep in episodes:
        if ep["runtime"] is not None:
            runtimes.append(ep["runtime"])
            total_runtime += ep["runtime"]
        score_count += ep["vote_count"]
    avg_runtime = (
        get_readable_duration(sum(runtimes) / len(runtimes)) if runtimes else None
    )
    total_runtime = get_readable_duration(total_runtime) if total_runtime else None
    return avg_runtime, total_runtime, score_count


def get_image_url(path):
    """Return the image URL for the media."""
    # when no image, value from response is null
    # e.g movie: 445290
    if path:
        return f"https://image.tmdb.org/t/p/w500{path}"
    return settings.IMG_NONE


def get_title(response):
    """Return the title for the media."""
    # tv shows have name instead of title
    try:
        return response["title"]
    except KeyError:
        return response["name"]


def get_readable_duration(duration):
    """Convert duration in minutes to a readable format."""
    # if unknown movie runtime, value from response is 0
    # e.g movie: 274613
    if duration:
        hours, minutes = divmod(int(duration), 60)
        return f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"
    return None


def get_genres(genres):
    """Return the genres for the media."""
    # when unknown genres, value from response is empty list (e.g tv: 24795)
    return services.extract_name_list(genres, key="name")


def get_country(countries):
    """Return the production country for the media."""
    # when unknown production country, value from response is empty list
    # e.g tv: 24795
    if countries:
        return countries[0]["name"]
    return None


def get_languages(languages):
    """Return the languages for the media."""
    # when unknown spoken languages, value from response is empty list (e.g tv: 24795)
    return services.extract_name_list(languages, key="english_name")


def get_companies(companies):
    """Return the production companies for the media."""
    # when unknown production companies, value from response is empty list
    # e.g tv: 24795
    if companies:
        return [company["name"] for company in companies[:3]]
    return None


def get_score(score):
    """Return the score for the media with one decimal place."""
    # when unknown score, value from response is 0.0

    return round(score, 1)


def get_related(related_medias, media_type, parent_response=None):
    """Return list of related media for the selected media."""
    related = []
    for media in related_medias:
        data = {
            "source": Sources.TMDB.value,
            "media_type": media_type,
            "image": get_image_url(media["poster_path"]),
        }
        if media_type == MediaTypes.SEASON.value:
            data["media_id"] = parent_response["id"]
            data["title"] = parent_response["name"]
            data["season_number"] = media["season_number"]
            data["season_title"] = media["name"]
            data["first_air_date"] = media["air_date"] or None
            data["max_progress"] = media["episode_count"]
        else:
            data["media_id"] = media["id"]
            data["title"] = get_title(media)
        related.append(data)
    return related


def get_collection(collection_response):
    """Format media collection list to match related media."""

    def date_key(media):
        date = media.get("release_date", "")
        if date is None or date == "":
            # If release date is unknown, sort by title after known releases
            title = get_title(media)
            date = f"9999-99-99-{title}"
        return date

    parts = sorted(collection_response.get("parts", []), key=date_key)
    return [
        {
            "source": Sources.TMDB.value,
            "media_type": MediaTypes.MOVIE.value,
            "image": get_image_url(media["poster_path"]),
            "media_id": media["id"],
            "title": get_title(media),
        }
        for media in parts
    ]


from app.providers._tmdb_browse import (  # noqa: E402, F401
    _build_discover_filter_hash,
    _build_discover_params,
    browse,
    browse_for_discover,
    discover,
    get_genre_list,
)
from app.providers._tmdb_episodes import (  # noqa: E402, F401
    episode,
    find_next_episode,
    process_episodes,
)
