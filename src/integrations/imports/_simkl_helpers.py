from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from app.models import Status

_STATUS_MAPPING = {
    "completed": Status.COMPLETED.value,
    "watching": Status.IN_PROGRESS.value,
    "plantowatch": Status.PLANNING.value,
    "hold": Status.PAUSED.value,
    "dropped": Status.DROPPED.value,
}


def map_status(status):
    """Map Simkl status to internal Status value."""
    return _STATUS_MAPPING.get(status, Status.IN_PROGRESS.value)


def parse_date(date_str):
    """Parse a Simkl date string into a datetime, or None if missing."""
    if date_str:
        return parse_datetime(date_str)
    return None


def get_episode_image(episode, season_number, metadata):
    """Return TMDB still URL for an episode, or fallback if missing."""
    for episode_metadata in metadata[f"season/{season_number}"]["episodes"]:
        if episode_metadata["episode_number"] == episode["number"]:
            return f"https://image.tmdb.org/t/p/w500{episode_metadata['still_path']}"
    return settings.IMG_NONE


def get_start_date(anime):
    """Earliest watched_at across the first season's episodes."""
    if "seasons" not in anime:
        return None
    dates = [parse_date(ep.get("watched_at")) for ep in anime["seasons"][0]["episodes"]]
    valid_dates = [d for d in dates if d is not None]
    return min(valid_dates) if valid_dates else None


def get_end_date(anime_status, last_watched_at):
    """Return end date if completed, else None."""
    if anime_status == Status.COMPLETED.value:
        return parse_date(last_watched_at)
    return None


def get_history_date(entry):
    """Pick the most appropriate history date from a Simkl entry."""
    if entry.get("last_watched_at"):
        return parse_datetime(entry.get("last_watched_at"))
    if entry.get("added_to_watchlist_at"):
        return parse_datetime(entry.get("added_to_watchlist_at"))
    return timezone.now()
