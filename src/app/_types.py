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


class Sources(models.TextChoices):
    """Choices for the source of the item."""

    TMDB = "tmdb", "The Movie Database"
    MAL = "mal", "MyAnimeList"
    MANGAUPDATES = "mangaupdates", "MangaUpdates"
    IGDB = "igdb", "Internet Game Database"
    OPENLIBRARY = "openlibrary", "Open Library"
    HARDCOVER = "hardcover", "Hardcover"
    COMICVINE = "comicvine", "Comic Vine"
    BGG = "bgg", "BoardGameGeek"
    MANUAL = "manual", "Manual"


class Status(models.TextChoices):
    """Choices for item status."""

    COMPLETED = "Completed", "Completed"
    IN_PROGRESS = "In progress", "In Progress"
    PLANNING = "Planning", "Planning"
    PAUSED = "Paused", "Paused"
    DROPPED = "Dropped", "Dropped"


def is_episode_media(media_type: str) -> bool:
    return media_type == MediaTypes.EPISODE.value


def is_season_media(media_type: str) -> bool:
    return media_type == MediaTypes.SEASON.value


def is_tv_media(media_type: str) -> bool:
    return media_type == MediaTypes.TV.value


def is_movie_media(media_type: str) -> bool:
    return media_type == MediaTypes.MOVIE.value


def is_anime_media(media_type: str) -> bool:
    return media_type == MediaTypes.ANIME.value


def is_manga_media(media_type: str) -> bool:
    return media_type == MediaTypes.MANGA.value


def is_game_media(media_type: str) -> bool:
    return media_type == MediaTypes.GAME.value
