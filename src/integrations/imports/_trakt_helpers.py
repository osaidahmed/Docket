import requests
from django.conf import settings

from app.models import Sources
from integrations.imports.helpers import MediaImportError


def get_episode_image(episode_number, season_metadata):
    """Extract episode image URL from season metadata, or fallback to placeholder."""
    for episode in season_metadata["episodes"]:
        if episode["episode_number"] == episode_number:
            if episode.get("still_path"):
                return f"https://image.tmdb.org/t/p/w500{episode['still_path']}"
            break
    return settings.IMG_NONE


def episode_exists_in_metadata(episode_number, season_metadata):
    """Return True if episode_number is present in season_metadata['episodes']."""
    return any(
        ep["episode_number"] == episode_number for ep in season_metadata["episodes"]
    )


def translate_api_error(error, username):
    """Map common Trakt HTTP errors to MediaImportError; otherwise re-raise."""
    status = error.response.status_code
    if status == requests.codes.not_found:
        msg = (
            f"User slug {username} not found. "
            "User slug can be found in your Trakt profile URL."
        )
        raise MediaImportError(msg) from error
    if status == requests.codes.unauthorized:
        msg = "This account is set to private, use OAuth import instead."
        raise MediaImportError(msg) from error
    raise error


def get_tmdb_id_or_warn(entry_data, warnings):
    """Return string TMDB id from entry_data, or None and append a warning."""
    tmdb_id = entry_data.get("ids", {}).get("tmdb")
    if tmdb_id:
        return str(tmdb_id)
    warnings.append(f"{entry_data['title']}: No {Sources.TMDB.label} ID found.")
    return None
