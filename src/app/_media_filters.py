from app._types import is_episode_media, is_season_media


def build_item_filter(media_type, item_ids, user, status_filter):
    """Build filter kwargs for an item-level Media query."""
    prefix = "related_season__" if is_episode_media(media_type) else ""
    filter_kwargs = {"item__in": item_ids, f"{prefix}user": user}
    if status_filter:
        filter_kwargs[f"{prefix}status"] = status_filter
    return filter_kwargs


def get_media_params(user, media_type, instance_id):
    """Build filter kwargs for fetching one Media instance by id."""
    params = {"id": instance_id}
    if is_episode_media(media_type):
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
    if is_season_media(media_type):
        params["item__season_number"] = season_number
        params["user"] = user
    elif is_episode_media(media_type):
        params["item__season_number"] = season_number
        params["item__episode_number"] = episode_number
        params["related_season__user"] = user
    else:
        params["user"] = user
    return params
