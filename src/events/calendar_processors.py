import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from django.core.cache import cache

from app.models import Item, MediaTypes, Sources
from app.providers import comicvine, services, tmdb
from events._calendar_dates import date_parser
from events._calendar_other import process_other
from events.calendar import (
    SENTINEL_DATETIME,
    auto_move_completed_to_planning,
    cleanup_invalid_events,
    generate_final_message,
    get_items_to_process,
    save_events,
)
from events.models import Event, SentinelDatetime

logger = logging.getLogger(__name__)


def fetch_releases(user=None, items_to_process=None):
    """Fetch and process releases for the calendar."""
    if items_to_process and items_to_process[0].source == Sources.MANUAL.value:
        return "Manual sources are not processed"

    items_to_process = items_to_process or get_items_to_process(user)
    if not items_to_process:
        return "No items to process"

    events_bulk = _process_items(items_to_process)
    items_updated = save_events(events_bulk)
    cleanup_invalid_events(events_bulk)
    auto_move_completed_to_planning(events_bulk)

    return generate_final_message(items_to_process, items_updated)


def _process_items(items_to_process):
    """Process items and categorize them."""
    events_bulk = []
    anime_to_process = []

    for item in items_to_process:
        if item.media_type == MediaTypes.ANIME.value:
            anime_to_process.append(item)
        elif item.media_type == MediaTypes.TV.value:
            process_tv(item, events_bulk)
        elif item.media_type == MediaTypes.COMIC.value:
            process_comic(item, events_bulk)
        else:
            process_other(item, events_bulk)

    process_anime_bulk(anime_to_process, events_bulk)
    return events_bulk


def process_tv(tv_item, events_bulk):
    """Process TV item and create events for all seasons and episodes."""
    logger.info("Processing TV show: %s", tv_item)

    try:
        seasons_to_process = get_seasons_to_process(tv_item)

        if not seasons_to_process:
            logger.info("%s - No seasons need processing", tv_item)
            return

        process_tv_seasons(tv_item, seasons_to_process, events_bulk)

    except services.ProviderAPIError:
        logger.warning("Failed to fetch metadata for %s", tv_item)
    except Exception:
        logger.exception("Error processing %s", tv_item)


def get_seasons_to_process(tv_item):
    """Identify which seasons of a TV show need to be processed."""
    tv_metadata = tmdb.tv(tv_item.media_id)

    if not tv_metadata.get("related", {}).get("seasons"):
        logger.warning("No seasons found for TV show: %s", tv_item)
        return []

    season_numbers = [
        season["season_number"] for season in tv_metadata["related"]["seasons"]
    ]

    if not season_numbers:
        logger.warning("No valid seasons found for TV show: %s", tv_item)
        return []

    next_episode_season = tv_metadata.get("next_episode_season")

    existing_season_events = Event.objects.filter(
        item__media_id=tv_item.media_id,
        item__source=tv_item.source,
        item__media_type=MediaTypes.SEASON.value,
    ).select_related("item")

    seasons_with_events = {event.item.season_number for event in existing_season_events}

    seasons_to_process = [
        season_num
        for season_num in season_numbers
        if _should_process_season(season_num, seasons_with_events, next_episode_season)
    ]

    if not seasons_to_process:
        return []

    logger.info(
        "%s - Processing %d seasons (Next episode season: %s)",
        tv_item,
        len(seasons_to_process),
        next_episode_season,
    )

    return seasons_to_process


def _should_process_season(season_num, seasons_with_events, next_episode_season):
    """Determine whether a season needs processing."""
    if season_num not in seasons_with_events:
        return True
    return bool(next_episode_season and season_num >= next_episode_season)


def process_tv_seasons(tv_item, seasons_to_process, events_bulk):
    """Process specific seasons of a TV show."""
    process_seasons_data = tmdb.tv_with_seasons(
        tv_item.media_id,
        seasons_to_process,
    )

    for season_number in seasons_to_process:
        season_key = f"season/{season_number}"
        if season_key not in process_seasons_data:
            logger.warning(
                "Season %s data not found for %s",
                season_number,
                tv_item,
            )
            continue

        season_metadata = process_seasons_data[season_key]

        season_item, _ = Item.objects.get_or_create(
            media_id=tv_item.media_id,
            source=tv_item.source,
            media_type=MediaTypes.SEASON.value,
            season_number=season_number,
            defaults={
                "title": tv_item.title,
                "image": season_metadata["image"],
            },
        )

        _process_season_episodes(season_item, season_metadata, events_bulk)


def _process_season_episodes(item, metadata, events_bulk):
    """Process episodes for a season and add them to events_bulk."""
    tvmaze_map = {}
    if metadata.get("tvdb_id"):
        logger.info("%s - TVDB ID found, fetching TVMaze episode data", item)
        tvmaze_map = get_tvmaze_episode_map(metadata["tvdb_id"])
    else:
        logger.warning("%s - No TVDB ID found, skipping TVMaze episode data", item)

    if not metadata.get("episodes"):
        logger.warning("%s - No episodes found in metadata", item)
        return

    for episode in metadata["episodes"]:
        episode_number = episode["episode_number"]
        season_number = metadata["season_number"]

        episode_datetime = get_episode_datetime(
            episode,
            season_number,
            episode_number,
            tvmaze_map,
        )

        events_bulk.append(
            Event(
                item=item,
                content_number=episode_number,
                datetime=episode_datetime,
            ),
        )


def process_comic(item, events_bulk):
    """Process comic item and add events to the event list."""
    logger.info("Fetching releases for %s", item)
    try:
        metadata = services.get_media_metadata(
            item.media_type,
            item.media_id,
            item.source,
        )
    except services.ProviderAPIError:
        logger.warning("Failed to fetch metadata for %s", item)
        return

    latest_event = Event.objects.filter(item=item).order_by("-datetime").first()
    last_issue_event_number = latest_event.content_number if latest_event else 0
    last_published_issue_number = metadata["max_issue_number"]
    if last_issue_event_number == last_published_issue_number:
        return

    try:
        issue_metadata = comicvine.issue(metadata["last_issue_id"])
    except services.ProviderAPIError:
        logger.warning("Failed to fetch issue metadata for %s", item)
        return

    if issue_metadata["store_date"]:
        issue_datetime = date_parser(issue_metadata["store_date"])
    elif issue_metadata["cover_date"]:
        issue_datetime = date_parser(issue_metadata["cover_date"])
    else:
        return

    events_bulk.append(
        Event(
            item=item,
            content_number=last_published_issue_number,
            datetime=issue_datetime,
        ),
    )


def process_anime_bulk(items, events_bulk):
    """Process multiple anime items and add events to the event list."""
    if not items:
        return

    anime_data = get_anime_schedule_bulk([item.media_id for item in items])

    for item in items:
        episodes = anime_data.get(item.media_id)

        if episodes:
            for episode in episodes:
                events_bulk.append(_convert_anime_episode(item, episode))
        else:
            logger.info(
                "Anime: %s (%s), not proccesed by AniList",
                item.title,
                item.media_id,
            )
            process_other(item, events_bulk)


def _convert_anime_episode(item, episode):
    """Convert a single anime episode entry to an Event."""
    if episode["airingAt"] is None:
        episode_datetime = SENTINEL_DATETIME
    else:
        episode_datetime = datetime.fromtimestamp(
            episode["airingAt"],
            tz=ZoneInfo("UTC"),
        )
    return Event(
        item=item,
        content_number=episode["episode"],
        datetime=episode_datetime,
    )


_ANIME_SCHEDULE_QUERY = """
query ($ids: [Int], $page: Int) {
  Page(page: $page) {
    pageInfo { hasNextPage }
    media(idMal_in: $ids, type: ANIME) {
      idMal
      endDate { year month day }
      episodes
      airingSchedule { nodes { episode airingAt } }
    }
  }
}
"""


def get_anime_schedule_bulk(media_ids):
    """Get the airing schedule for multiple anime items from AniList API."""
    all_data = {}
    page = 1
    url = "https://graphql.anilist.co"

    while True:
        variables = {"ids": media_ids, "page": page}
        response = services.api_request(
            "ANILIST",
            "POST",
            url,
            params={"query": _ANIME_SCHEDULE_QUERY, "variables": variables},
        )

        for media_data in response["data"]["Page"]["media"]:
            _process_anime_page_entry(media_data, all_data)

        if not response["data"]["Page"]["pageInfo"]["hasNextPage"]:
            break
        page += 1

    return all_data


def _process_anime_page_entry(media_data, all_data):
    """Process a single anime entry from an AniList page response."""
    airing_schedule = media_data["airingSchedule"]["nodes"]
    total_episodes = media_data["episodes"]
    mal_id = str(media_data["idMal"])

    if not total_episodes:
        return

    if airing_schedule:
        airing_schedule = _filter_excess_episodes(
            airing_schedule,
            total_episodes,
            mal_id,
        )

    if not airing_schedule or airing_schedule[-1]["episode"] < total_episodes:
        airing_schedule = _fill_missing_episodes(
            airing_schedule,
            total_episodes,
            mal_id,
            media_data["endDate"],
        )
        if airing_schedule is None:
            return

    all_data[mal_id] = airing_schedule


def _filter_excess_episodes(airing_schedule, total_episodes, mal_id):
    """Filter out episodes beyond the total episode count."""
    original_length = len(airing_schedule)
    filtered = [
        episode for episode in airing_schedule if episode["episode"] <= total_episodes
    ]

    if original_length > len(filtered):
        logger.info(
            "Filtered episodes for MAL ID %s - keep only %s episodes",
            mal_id,
            total_episodes,
        )

    return filtered


def _fill_missing_episodes(schedule, total_episodes, mal_id, end_date):
    """Fill in missing episode data when AniList schedule is incomplete.

    Returns the updated schedule, or None if the entry should be skipped.
    """
    mal_metadata = services.get_media_metadata(
        media_type=MediaTypes.ANIME.value,
        media_id=mal_id,
        source=Sources.MAL.value,
    )
    mal_total_episodes = mal_metadata["max_progress"]
    if mal_total_episodes and mal_total_episodes > total_episodes:
        logger.info(
            "MAL ID %s - MAL has %s episodes, AniList has %s",
            mal_id,
            mal_total_episodes,
            total_episodes,
        )
        return None

    logger.info(
        "Adding final episode for MAL ID %s - Ep %s",
        mal_id,
        total_episodes,
    )
    end_date_timestamp = anilist_date_parser(end_date)
    schedule.append(
        {"episode": total_episodes, "airingAt": end_date_timestamp},
    )
    return schedule


def get_episode_datetime(episode, season_number, episode_number, tvmaze_map):
    """Determine the most accurate air datetime for an episode."""
    tvmaze_key = f"{season_number}_{episode_number}"
    tvmaze_airstamp = tvmaze_map.get(tvmaze_key)

    if tvmaze_airstamp:
        return datetime.fromisoformat(tvmaze_airstamp)

    if episode["air_date"]:
        try:
            return date_parser(episode["air_date"])
        except ValueError:
            logger.warning(
                "Invalid air date for S%sE%s from TMDB: %s",
                season_number,
                episode_number,
                episode["air_date"],
            )

    return SENTINEL_DATETIME


def get_tvmaze_episode_map(tvdb_id):
    """Fetch and process episode data from TVMaze using TVDB ID with caching."""
    cache_key = f"tvmaze_map_{tvdb_id}"
    cached_map = cache.get(cache_key)

    if cached_map:
        logger.info("%s - Using cached TVMaze episode map", tvdb_id)
        return cached_map

    show_response = get_tvmaze_response(tvdb_id)

    tvmaze_map = {}

    if show_response:
        episodes = show_response["_embedded"]["episodes"]

        for ep in episodes:
            season_num = ep.get("season")
            episode_num = ep.get("number")
            if season_num is not None and episode_num is not None:
                key = f"{season_num}_{episode_num}"
                tvmaze_map[key] = ep.get("airstamp")

    cache.set(cache_key, tvmaze_map)
    logger.info(
        "%s - Cached TVMaze episode map with %d entries",
        tvdb_id,
        len(tvmaze_map),
    )

    return tvmaze_map


def get_tvmaze_response(tvdb_id):
    """Fetch episode data from TVMaze using TVDB ID."""
    tvmaze_id = _lookup_tvmaze_id(tvdb_id)
    if not tvmaze_id:
        return {}

    show_url = f"https://api.tvmaze.com/shows/{tvmaze_id}?embed=episodes"
    try:
        return services.api_request("TVMaze", "GET", show_url)
    except requests.exceptions.HTTPError:
        return {}


def _lookup_tvmaze_id(tvdb_id):
    """Look up the TVMaze show ID from a TVDB ID."""
    lookup_url = f"https://api.tvmaze.com/lookup/shows?thetvdb={tvdb_id}"
    try:
        lookup_response = services.api_request("TVMaze", "GET", lookup_url)
    except requests.exceptions.HTTPError as err:
        if err.response.status_code == requests.codes.not_found:
            logger.warning(
                "TVMaze lookup failed for TVDB ID %s - %s",
                tvdb_id,
                err.response.text,
            )
        else:
            logger.warning(
                "%s - TVMaze lookup error: %s",
                tvdb_id,
                err.response.text,
            )
        return None

    if not lookup_response:
        logger.warning("%s - No TVMaze lookup response for TVDB ID", tvdb_id)
        return None

    tvmaze_id = lookup_response.get("id")
    if not tvmaze_id:
        logger.warning("%s - TVMaze ID not found for TVDB ID", tvdb_id)
        return None

    return tvmaze_id


def anilist_date_parser(start_date):
    """Parse the start date from AniList to a timestamp."""
    if not start_date["year"]:
        return None

    month = start_date["month"] or 1
    day = start_date["day"] or 1

    dt = datetime(
        start_date["year"],
        month,
        day,
        hour=SentinelDatetime.HOUR,
        minute=SentinelDatetime.MINUTE,
        second=SentinelDatetime.SECOND,
        microsecond=SentinelDatetime.MICROSECOND,
        tzinfo=ZoneInfo("UTC"),
    )

    return dt.timestamp()
