"""Episode-level helpers for TMDB."""

from app.models import MediaTypes, Sources
from app.providers import services
from app.providers import tmdb as _tmdb


def process_episodes(season_metadata, episodes_in_db):
    """Process the episodes for the selected season."""
    episodes_metadata = []

    # Convert the queryset to a dictionary for efficient lookups
    tracked_episodes = {}
    for ep in episodes_in_db:
        episode_number = ep.item.episode_number
        if episode_number not in tracked_episodes:
            tracked_episodes[episode_number] = []
        tracked_episodes[episode_number].append(ep)

    for episode in season_metadata["episodes"]:
        episode_number = episode["episode_number"]

        episodes_metadata.append(
            {
                "media_id": season_metadata["media_id"],
                "media_type": MediaTypes.EPISODE.value,
                "source": Sources.TMDB.value,
                "season_number": season_metadata["season_number"],
                "episode_number": episode_number,
                "air_date": episode["air_date"],  # when unknown, response returns null
                "image": _tmdb.get_image_url(episode["still_path"]),
                "title": episode["name"],
                "overview": episode["overview"],
                "history": tracked_episodes.get(episode_number, []),
                "runtime": _tmdb.get_readable_duration(episode["runtime"]),
            },
        )
    return episodes_metadata


def find_next_episode(episode_number, episodes_metadata):
    """Find the next episode number."""
    # Find the current episode in the sorted list
    current_episode_index = None
    for index, episode in enumerate(episodes_metadata):
        if episode["episode_number"] == episode_number:
            current_episode_index = index
            break

    # If episode not found or it's the last episode, return None
    if current_episode_index is None or current_episode_index + 1 >= len(
        episodes_metadata,
    ):
        return None

    # Return the next episode number
    return episodes_metadata[current_episode_index + 1]["episode_number"]


def episode(media_id, season_number, episode_number):
    """Return the metadata for the selected episode from The Movie Database."""
    tv_metadata = _tmdb.tv_with_seasons(media_id, [season_number])
    season_metadata = tv_metadata[f"season/{season_number}"]

    for episode in season_metadata["episodes"]:
        if episode["episode_number"] == int(episode_number):
            return {
                "title": season_metadata["title"],
                "season_title": season_metadata["season_title"],
                "episode_title": episode["name"],
                "image": _tmdb.get_image_url(episode["still_path"]),
            }

    # Episode not found - throw ProviderAPIError
    msg = (
        f"Episode {episode_number} not found in season {season_number} "
        f"for {Sources.TMDB.label} with ID {media_id}"
    )
    raise services.ProviderAPIError(Sources.TMDB.value, 404, msg)
