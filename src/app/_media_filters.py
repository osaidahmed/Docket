from app._types import MediaTypes


def build_item_filter(media_type, item_ids, user, status_filter):
    """Build filter kwargs for an item-level Media query."""
    is_episode = media_type == MediaTypes.EPISODE.value
    prefix = "related_season__" if is_episode else ""
    filter_kwargs = {"item__in": item_ids, f"{prefix}user": user}
    if status_filter:
        filter_kwargs[f"{prefix}status"] = status_filter
    return filter_kwargs


def get_media_params(user, media_type, instance_id):
    """Build filter kwargs for fetching one Media instance by id."""
    params = {"id": instance_id}
    if media_type == MediaTypes.EPISODE.value:
        params["related_season__user"] = user
    else:
        params["user"] = user
    return params


def filter_media_params(
    media_type, media_id, source, user, season_number=None, episode_number=None
):
    """Build filter kwargs for resolving Media by external (media_id, source)."""
    params = {
        "item__media_type": media_type,
        "item__source": source,
        "item__media_id": media_id,
    }
    if media_type == MediaTypes.SEASON.value:
        params["item__season_number"] = season_number
        params["user"] = user
    elif media_type == MediaTypes.EPISODE.value:
        params["item__season_number"] = season_number
        params["item__episode_number"] = episode_number
        params["related_season__user"] = user
    else:
        params["user"] = user
    return params
