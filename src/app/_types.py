from django.db import models


class MediaTypes(models.TextChoices):
    """Choices for the media type of the item."""

    ANIME = "anime", "Anime"
    MANGA = "manga", "Manga"
    TV = "tv", "TV Show"
    SEASON = "season", "TV Season"
    EPISODE = "episode", "Episode"
    MOVIE = "movie", "Movie"
    GAME = "game", "Game"
    BOOK = "book", "Book"
    COMIC = "comic", "Comic"
    BOARDGAME = "boardgame", "Board Game"


TV_STRUCTURED = frozenset(
    {MediaTypes.TV.value, MediaTypes.SEASON.value, MediaTypes.EPISODE.value}
)


def is_episode_media(media_type: str) -> bool:
    return media_type == MediaTypes.EPISODE.value


def is_tv_structured(media_type: str) -> bool:
    return media_type in TV_STRUCTURED
