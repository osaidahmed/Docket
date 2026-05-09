"""News aggregator configuration: RSS sources and per-item support flags."""

NEWS_SOURCES = {
    "anime": [
        {
            "slug": "comicbook-anime",
            "label": "ComicBook.com Anime",
            "rss_url": "https://comicbook.com/category/anime/feed/",
        },
    ],
    "manga": [
        {
            "slug": "comicbook-manga",
            "label": "ComicBook.com Manga",
            "rss_url": "https://comicbook.com/tag/manga/feed/",
        },
    ],
    "tv": [
        {
            "slug": "deadline-tv",
            "label": "Deadline TV",
            "rss_url": "https://deadline.com/v/tv/feed/",
        },
        {
            "slug": "variety-tv",
            "label": "Variety TV",
            "rss_url": "https://variety.com/v/tv/feed/",
        },
        {
            "slug": "thr-tv",
            "label": "Hollywood Reporter TV",
            "rss_url": "https://www.hollywoodreporter.com/c/tv/feed/",
        },
    ],
    "movie": [
        {
            "slug": "deadline-film",
            "label": "Deadline Film",
            "rss_url": "https://deadline.com/v/film/feed/",
        },
        {
            "slug": "variety-film",
            "label": "Variety Film",
            "rss_url": "https://variety.com/v/film/feed/",
        },
        {
            "slug": "thr-movies",
            "label": "Hollywood Reporter Movies",
            "rss_url": "https://www.hollywoodreporter.com/c/movies/feed/",
        },
    ],
    "game": [
        {
            "slug": "gamespot",
            "label": "GameSpot",
            "rss_url": "https://www.gamespot.com/feeds/news/",
        },
    ],
    "book": [
        {
            "slug": "pw",
            "label": "Publishers Weekly",
            "rss_url": "https://www.publishersweekly.com/pw/feeds/news.xml",
        },
    ],
    "comic": [
        {
            "slug": "icv2",
            "label": "ICv2",
            "rss_url": "https://icv2.com/articles/news/rss.xml",
        },
    ],
    "boardgame": [
        {
            "slug": "bgg-news",
            "label": "BoardGameGeek News",
            "rss_url": "https://boardgamegeek.com/blog/rss/1",
        },
    ],
}

PER_ITEM_NEWS_SUPPORT = frozenset({"anime", "manga", "game", "boardgame"})

PER_ITEM_SAMPLE_SIZE = {
    "anime": 5,
    "manga": 5,
    "game": 5,
    "boardgame": 3,
}


def get_news_sources(media_type):
    """Return the list of industry RSS sources configured for a media type."""
    return NEWS_SOURCES.get(media_type, [])


def supports_per_item_news(media_type):
    """Return whether per-item news is supported for this media type."""
    return media_type in PER_ITEM_NEWS_SUPPORT


def get_sample_size(media_type):
    """Return how many tracked items to spotlight per type for library news."""
    return PER_ITEM_SAMPLE_SIZE.get(media_type, 5)
