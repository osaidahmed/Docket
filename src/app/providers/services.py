import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from defusedxml import ElementTree
from django.conf import settings
from pyrate_limiter import RedisBucket
from redis import ConnectionPool
from requests.adapters import HTTPAdapter
from requests_ratelimiter import LimiterAdapter, LimiterSession

from app.models import MediaTypes, Sources
from app.providers import (
    anilist,
    bgg,
    comicvine,
    hardcover,
    igdb,
    jikan,
    mal,
    mangaupdates,
    manual,
    openlibrary,
    tmdb,
)

logger = logging.getLogger(__name__)


def get_redis_connection():
    """Return a Redis connection pool."""
    if settings.TESTING:
        import fakeredis  # noqa: PLC0415

        return fakeredis.FakeStrictRedis().connection_pool
    return ConnectionPool.from_url(settings.REDIS_URL)


redis_pool = get_redis_connection()

REDIS_PREFIX = getattr(settings, "REDIS_PREFIX", None)
bucket_name = f"{REDIS_PREFIX}_api" if REDIS_PREFIX else "api"

session = LimiterSession(
    per_second=5,
    bucket_class=RedisBucket,
    bucket_kwargs={"redis_pool": redis_pool, "bucket_name": bucket_name},
)

session.mount("http://", HTTPAdapter(max_retries=3))
session.mount("https://", HTTPAdapter(max_retries=3))

session.mount(
    "https://api.myanimelist.net/v2",
    LimiterAdapter(per_minute=30),
)
session.mount(
    "https://graphql.anilist.co",
    LimiterAdapter(per_minute=85),
)
session.mount(
    "https://api.igdb.com/v4",
    LimiterAdapter(per_second=3),
)
session.mount(
    "https://api.tvmaze.com",
    LimiterAdapter(per_second=2),
)
session.mount(
    "https://comicvine.gamespot.com/api",
    LimiterAdapter(per_hour=190),
)
session.mount(
    "https://openlibrary.org",
    LimiterAdapter(per_minute=20),
)
session.mount(
    "https://api.hardcover.app/v1/graphql",
    LimiterAdapter(per_minute=50),
)
session.mount(
    "https://boardgamegeek.com/xmlapi2",
    LimiterAdapter(per_second=2),
)
session.mount(
    "https://api.jikan.moe",
    LimiterAdapter(per_second=3),
)


class ProviderAPIError(Exception):
    """Exception raised when a provider API fails to respond."""

    def __init__(self, provider, error, details=None):
        """Initialize the exception with the provider name."""
        self.provider = provider
        self.status_code = error.response.status_code
        try:
            provider = Sources(provider).label
        except ValueError:
            provider = provider.title()

        logger.error("%s error: %s", provider, error.response.text)

        message = (
            f"There was an error contacting the {provider} API "
            f"(HTTP {self.status_code})"
        )
        if details:
            message += f": {details}"
        message += ". Please try again later."
        super().__init__(message)


def raise_not_found_error(provider, media_id, media_type="item"):
    """
    Raise a 404 ProviderAPIError for when a media item is not found.

    Args:
        provider: The provider source value (e.g., Sources.COMICVINE.value)
        media_id: The media ID that was not found
        media_type: The type of media (e.g., "comic", "game", "book")
    """
    error_msg = f"{media_type.capitalize()} with ID {media_id} not found"
    logger.error("%s: %s", provider, error_msg)

    # Create a mock 404 error response
    mock_response = type(
        "obj",
        (object,),
        {
            "status_code": 404,
            "text": error_msg,
        },
    )()
    mock_error = requests.exceptions.HTTPError(response=mock_response)

    raise ProviderAPIError(provider, mock_error, error_msg)


MAX_RETRIES = 3


def api_request(
    provider,
    method,
    url,
    params=None,
    data=None,
    headers=None,
    response_format="json",
):
    """Make a request to the API and return the response."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = _execute_request(method, url, params, data, headers)
            return _parse_response(response, response_format)
        except requests.exceptions.HTTPError as error:
            _handle_http_error(error, attempt)
        except (
            requests.exceptions.ConnectionError,
            requests.exceptions.Timeout,
        ) as error:
            logger.exception("Connection error for %s", provider)
            raise _connection_error(provider, error) from error


def _parse_response(response, response_format):
    if response_format == "xml":
        return ElementTree.fromstring(response.text)
    return response.json()


def _handle_http_error(error, attempt):
    """Handle HTTP errors, retrying on 429 with exponential backoff."""
    if error.response.status_code != requests.codes.too_many_requests:
        raise error from None
    if attempt == MAX_RETRIES:
        raise error from None
    seconds_to_wait = int(error.response.headers.get("Retry-After", 5))
    wait_time = max(seconds_to_wait + 3, 5 * (2 ** (attempt - 1)))
    logger.warning(
        "Rate limited, waiting %s seconds (attempt %d/%d)",
        wait_time,
        attempt,
        MAX_RETRIES,
    )
    time.sleep(wait_time)


def _execute_request(method, url, params, data, headers):
    kwargs = {"url": url, "headers": headers, "timeout": settings.REQUEST_TIMEOUT}
    if method == "GET":
        kwargs["params"] = params
        response = session.get(**kwargs)
    else:
        kwargs["data"] = data
        kwargs["json"] = params
        response = session.post(**kwargs)
    response.raise_for_status()
    return response


def _connection_error(provider, error):
    mock_response = type("obj", (object,), {"status_code": 503, "text": str(error)})()
    return ProviderAPIError(
        provider,
        requests.exceptions.HTTPError(response=mock_response),
        "Connection failed — the provider may be temporarily unavailable",
    )


def get_media_metadata(
    media_type,
    media_id,
    source,
    season_numbers=None,
    episode_number=None,
):
    """Return the metadata for the selected media."""
    if source == Sources.MANUAL.value:
        if media_type == MediaTypes.SEASON.value:
            return manual.season(media_id, season_numbers[0])
        if media_type == MediaTypes.EPISODE.value:
            return manual.episode(media_id, season_numbers[0], episode_number)
        if media_type == "tv_with_seasons":
            media_type = MediaTypes.TV.value
        return manual.metadata(media_id, media_type)

    metadata_retrievers = {
        MediaTypes.ANIME.value: lambda: mal.anime(media_id),
        MediaTypes.MANGA.value: lambda: (
            mangaupdates.manga(media_id)
            if source == Sources.MANGAUPDATES.value
            else mal.manga(media_id)
        ),
        MediaTypes.TV.value: lambda: tmdb.tv(media_id),
        "tv_with_seasons": lambda: tmdb.tv_with_seasons(media_id, season_numbers),
        MediaTypes.SEASON.value: lambda: tmdb.tv_with_seasons(media_id, season_numbers)[
            f"season/{season_numbers[0]}"
        ],
        MediaTypes.EPISODE.value: lambda: tmdb.episode(
            media_id,
            season_numbers[0],
            episode_number,
        ),
        MediaTypes.MOVIE.value: lambda: tmdb.movie(media_id),
        MediaTypes.GAME.value: lambda: igdb.game(media_id),
        MediaTypes.BOOK.value: lambda: (
            hardcover.book(media_id)
            if source == Sources.HARDCOVER.value
            else openlibrary.book(media_id)
        ),
        MediaTypes.COMIC.value: lambda: comicvine.comic(media_id),
        MediaTypes.BOARDGAME.value: lambda: bgg.boardgame(media_id),
    }
    return metadata_retrievers[media_type]()


def search(media_type, query, page, source=None):
    """Search for media based on the query and return the results."""
    search_handlers = {
        MediaTypes.MANGA.value: lambda: (
            mangaupdates.search(query, page)
            if source == Sources.MANGAUPDATES.value
            else mal.search(media_type, query, page)
        ),
        MediaTypes.ANIME.value: lambda: mal.search(media_type, query, page),
        MediaTypes.TV.value: lambda: tmdb.search(media_type, query, page),
        MediaTypes.MOVIE.value: lambda: tmdb.search(media_type, query, page),
        MediaTypes.SEASON.value: lambda: tmdb.search(MediaTypes.TV.value, query, page),
        MediaTypes.EPISODE.value: lambda: tmdb.search(MediaTypes.TV.value, query, page),
        MediaTypes.GAME.value: lambda: igdb.search(query, page),
        MediaTypes.BOOK.value: lambda: (
            openlibrary.search(query, page)
            if source == Sources.OPENLIBRARY.value
            else hardcover.search(query, page)
        ),
        MediaTypes.COMIC.value: lambda: comicvine.search(query, page),
        MediaTypes.BOARDGAME.value: lambda: bgg.search(query, page),
    }
    return search_handlers[media_type]()


def browse(media_type, category, page, year=None, season=None):
    """Browse media by category and return the results."""
    from app import helpers as app_helpers  # noqa: PLC0415

    if category == "seasonal" and media_type == MediaTypes.ANIME.value:
        return mal.browse_seasonal(year, season, page)

    browse_handlers = {
        MediaTypes.ANIME.value: lambda: mal.browse(
            MediaTypes.ANIME.value, category, page
        ),
        MediaTypes.MANGA.value: lambda: mal.browse(
            MediaTypes.MANGA.value, category, page
        ),
        MediaTypes.TV.value: lambda: tmdb.browse(MediaTypes.TV.value, category, page),
        MediaTypes.MOVIE.value: lambda: tmdb.browse(
            MediaTypes.MOVIE.value, category, page
        ),
        MediaTypes.GAME.value: lambda: igdb.browse(category, page),
        MediaTypes.BOOK.value: lambda: (
            openlibrary.browse(category, page)
            if category == "trending"
            else hardcover.browse(category, page)
        ),
        MediaTypes.COMIC.value: lambda: comicvine.browse(category, page),
        MediaTypes.BOARDGAME.value: lambda: bgg.browse(category, page),
    }
    handler = browse_handlers.get(media_type)
    if handler is None:
        return app_helpers.format_search_response(page, 24, 0, [])
    return handler()


def browse_filtered(media_type, filters, page):
    """Browse media with filter parameters."""
    from app import helpers as app_helpers  # noqa: PLC0415

    filter_handlers = {
        MediaTypes.MOVIE.value: lambda: tmdb.discover(
            MediaTypes.MOVIE.value, filters, page
        ),
        MediaTypes.TV.value: lambda: tmdb.discover(MediaTypes.TV.value, filters, page),
        MediaTypes.ANIME.value: lambda: jikan.browse(
            MediaTypes.ANIME.value, filters, page
        ),
        MediaTypes.MANGA.value: lambda: jikan.browse(
            MediaTypes.MANGA.value, filters, page
        ),
        MediaTypes.GAME.value: lambda: igdb.browse_filtered(filters, page),
    }
    handler = filter_handlers.get(media_type)
    if handler is None:
        return app_helpers.format_search_response(page, 24, 0, [])
    return handler()


def get_filter_options(provider_key):
    """Fetch filter options (e.g., genre lists) from the appropriate provider."""
    option_fetchers = {
        "tmdb_movie_genres": lambda: tmdb.get_genre_list(MediaTypes.MOVIE.value),
        "tmdb_tv_genres": lambda: tmdb.get_genre_list(MediaTypes.TV.value),
        "jikan_anime_genres": lambda: jikan.get_genres(MediaTypes.ANIME.value),
        "jikan_manga_genres": lambda: jikan.get_genres(MediaTypes.MANGA.value),
        "igdb_genres": igdb.get_genres,
        "igdb_platforms": igdb.get_platforms,
        "igdb_themes": igdb.get_themes,
    }
    fetcher = option_fetchers.get(provider_key)
    if fetcher is None:
        return []
    return fetcher()


UNIFIED_SEARCH_MAX_PER_TYPE = 3
UNIFIED_SEARCH_TIMEOUT = 5  # seconds per future


def search_all(query, enabled_types):
    """Search all enabled media types in parallel."""
    from app import config  # noqa: PLC0415

    searchable = [
        mt
        for mt in enabled_types
        if mt in config.MEDIA_TYPE_CONFIG
        and "sample_query" in config.MEDIA_TYPE_CONFIG[mt]
    ]

    if not searchable:
        return []

    grouped = _parallel_search(query, searchable)

    return [
        {"media_type": mt, "results": grouped[mt]}
        for mt in enabled_types
        if mt in grouped
    ]


DISCOVER_TIMEOUT = 8


def _resolve_section_fetcher(media_type, section_cfg):
    """Return a callable(page) that fetches data for a discover section."""
    provider = section_cfg.get("provider", "")
    limit = section_cfg.get("limit", 24)

    dispatch = {
        "anilist_trending": lambda p: anilist.trending(media_type, p, limit),
        "anilist_recently_updated": lambda p: anilist.recently_updated(
            media_type, p, limit
        ),
        "anilist_upcoming": lambda p: anilist.upcoming(media_type, p, limit),
        "anilist_schedule": lambda p: anilist.airing_schedule(p, limit),
        "jikan_schedule": lambda _p: jikan.browse_schedule(limit=limit),
        "mangaupdates_releases": lambda p: mangaupdates.browse("releases", p),
    }
    if provider in dispatch:
        return dispatch[provider]

    category = section_cfg.get("browse_category", "")
    if section_cfg.get("type") == "spotlight_carousel":
        return lambda p: tmdb.browse_for_discover(media_type, category, p)
    return lambda p: browse(media_type, category, p)


def discover_sections(media_type):
    """Fetch all discover sections for a media type in parallel."""
    from app import config  # noqa: PLC0415

    sections_config = config.get_discover_sections(media_type)
    if not sections_config:
        return {}

    results = {}
    with ThreadPoolExecutor(max_workers=len(sections_config)) as executor:
        futures = {
            executor.submit(_resolve_section_fetcher(media_type, cfg), 1): cfg["key"]
            for cfg in sections_config
        }
        for future in as_completed(futures, timeout=DISCOVER_TIMEOUT):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception:
                logger.exception("Discover section %s failed", key)
                results[key] = None

    return results


def discover_section_page(media_type, section_cfg, page):
    """Fetch a single discover section's page (for HTMX load-more)."""
    fetcher = _resolve_section_fetcher(media_type, section_cfg)
    return fetcher(page)


def _parallel_search(query, searchable):
    from app import config  # noqa: PLC0415

    def _search_one(media_type):
        source = config.get_default_source_name(media_type).value
        data = search(media_type, query, 1, source)
        return media_type, data.get("results", [])[:UNIFIED_SEARCH_MAX_PER_TYPE]

    grouped = {}
    with ThreadPoolExecutor(max_workers=len(searchable)) as executor:
        futures = {executor.submit(_search_one, mt): mt for mt in searchable}
        for future in as_completed(futures):
            try:
                mt, results = future.result(timeout=UNIFIED_SEARCH_TIMEOUT)
                if results:
                    grouped[mt] = results
            except Exception:
                logger.exception("Unified search failed for %s", futures[future])
    return grouped


SUGGEST_API_TIMEOUT = 2  # seconds per future
SUGGEST_API_LIMIT = 5


def _build_suggest_tasks(query, enabled_types, limit):
    """Build the list of provider tasks for search suggestions."""
    tasks = []

    # TMDB multi covers both TV and Movie in one call
    if MediaTypes.TV.value in enabled_types or MediaTypes.MOVIE.value in enabled_types:
        tasks.append(("tmdb_multi", lambda: tmdb.search_multi(query, limit)))

    # Map each remaining media type to its default provider search
    provider_map = {
        MediaTypes.ANIME.value: (
            "mal_anime",
            lambda: mal.search(MediaTypes.ANIME.value, query, 1)["results"][:limit],
        ),
        MediaTypes.MANGA.value: (
            "mal_manga",
            lambda: mal.search(MediaTypes.MANGA.value, query, 1)["results"][:limit],
        ),
        MediaTypes.GAME.value: (
            "igdb_game",
            lambda: igdb.search(query, 1)["results"][:limit],
        ),
        MediaTypes.BOOK.value: (
            "hardcover_book",
            lambda: hardcover.search(query, 1)["results"][:limit],
        ),
        MediaTypes.COMIC.value: (
            "comicvine_comic",
            lambda: comicvine.search(query, 1)["results"][:limit],
        ),
        MediaTypes.BOARDGAME.value: (
            "bgg_boardgame",
            lambda: bgg.search(query, 1)["results"][:limit],
        ),
    }

    for mt in enabled_types:
        if mt in (MediaTypes.TV.value, MediaTypes.MOVIE.value):
            continue  # handled by tmdb_multi
        if mt in provider_map:
            tasks.append(provider_map[mt])

    return tasks


def _collect_suggest_results(future, name, seen_keys, all_results):
    """Collect deduplicated results from a single completed suggest future."""
    try:
        results = future.result()
        for item in results:
            key = (str(item["media_id"]), item["source"])
            if key not in seen_keys:
                seen_keys.add(key)
                all_results.append(item)
    except Exception:
        logger.exception("Suggest API failed for %s", name)


def _cross_provider_dedup(all_results, enabled_types):
    """Remove cross-provider duplicates between TMDB TV and MAL anime."""
    tv_type = MediaTypes.TV.value
    anime_type = MediaTypes.ANIME.value

    if tv_type not in enabled_types or anime_type not in enabled_types:
        return all_results

    tv_results = [r for r in all_results if r["media_type"] == tv_type]
    anime_results = [r for r in all_results if r["media_type"] == anime_type]

    if not tv_results or not anime_results:
        return all_results

    to_remove = _find_dedup_removals(tv_results, anime_results, enabled_types)
    return [r for r in all_results if id(r) not in to_remove]


def _find_dedup_removals(tv_results, anime_results, enabled_types):
    tv_type = MediaTypes.TV.value
    anime_type = MediaTypes.ANIME.value
    tv_preferred = enabled_types.index(tv_type) < enabled_types.index(anime_type)

    anime_titles = {}
    for r in anime_results:
        anime_titles[r["title"].lower()] = r
        english = r.get("english_title", "")
        if english:
            anime_titles[english.lower()] = r

    tv_titles = {r["title"].lower(): r for r in tv_results}
    loser_index = anime_titles if tv_preferred else tv_titles
    return {id(loser_index[t]) for t in tv_titles if t in anime_titles}


def _interleave_results(all_results, enabled_types, limit):
    """Round-robin interleave results by media type in preference order."""
    from collections import defaultdict  # noqa: PLC0415

    grouped = defaultdict(list)
    for item in all_results:
        grouped[item["media_type"]].append(item)

    type_order = [mt for mt in enabled_types if mt in grouped]
    max_len = max((len(grouped[mt]) for mt in type_order), default=0)

    flat = [
        grouped[mt][i]
        for i in range(max_len)
        for mt in type_order
        if i < len(grouped[mt])
    ]

    return flat[:limit]


def search_suggest_api(query, enabled_types, local_keys=None, limit=SUGGEST_API_LIMIT):
    """Search API providers for suggestions, combining results in parallel.

    Uses as_completed so fast providers are processed immediately. Results
    are interleaved round-robin by media type preference for diversity.
    """
    if not query or not query.strip():
        return []

    if local_keys is None:
        local_keys = set()

    tasks = _build_suggest_tasks(query, enabled_types, limit)
    if not tasks:
        return []

    all_results = []
    seen_keys = set(local_keys)

    executor = ThreadPoolExecutor(max_workers=len(tasks))
    try:
        futures = {executor.submit(fn): name for name, fn in tasks}

        for future in as_completed(futures, timeout=SUGGEST_API_TIMEOUT):
            _collect_suggest_results(future, futures[future], seen_keys, all_results)
    except TimeoutError:
        pass
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    all_results = _cross_provider_dedup(all_results, enabled_types)
    return _interleave_results(all_results, enabled_types, limit)
