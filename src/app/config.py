from django.urls import reverse
from django.utils.http import urlencode

from app.models import MediaTypes, Sources, Status

# --- Color Constants ---
COLORS = {
    "emerald": {
        "text": "text-emerald-400",
        "background": "bg-emerald-400",
        "hex": "#10b981",
    },
    "purple": {
        "text": "text-purple-400",
        "background": "bg-purple-400",
        "hex": "#a855f7",
    },
    "indigo": {
        "text": "text-indigo-400",
        "background": "bg-indigo-400",
        "hex": "#6366f1",
    },
    "orange": {
        "text": "text-orange-400",
        "background": "bg-orange-400",
        "hex": "#f97316",
    },
    "blue": {
        "text": "text-blue-400",
        "background": "bg-blue-400",
        "hex": "#3b82f6",
    },
    "red": {
        "text": "text-red-400",
        "background": "bg-red-400",
        "hex": "#ef4444",
    },
    "yellow": {
        "text": "text-yellow-400",
        "background": "bg-yellow-400",
        "hex": "#eab308",
    },
    "fuchsia": {
        "text": "text-fuchsia-400",
        "background": "bg-fuchsia-400",
        "hex": "#d946ef",
    },
    "cyan": {
        "text": "text-cyan-400",
        "background": "bg-cyan-400",
        "hex": "#06b6d4",
    },
    "lime": {
        "text": "text-lime-400",
        "background": "bg-lime-400",
        "hex": "#84cc16",
    },
    "sky": {
        "text": "text-sky-400",
        "background": "bg-sky-400",
        "hex": "#87ceeb",
    },
}

# --- Central Configuration Dictionary ---
MEDIA_TYPE_CONFIG = {
    MediaTypes.TV.value: {
        "sources": [Sources.TMDB],
        "default_source": Sources.TMDB,
        "sample_query": "Breaking Bad",
        "unicode_icon": "📺",
        "verb": ("watch", "watched"),
        "text_color": COLORS["emerald"]["text"],
        "stats_color": COLORS["emerald"]["hex"],
        "svg_icon": """
            <rect width="20" height="15" x="2" y="7" rx="2" ry="2"/>
            <polyline points="17 2 12 7 7 2"/>""",
        "explore_categories": [
            {"slug": "trending", "label": "Trending"},
            {"slug": "popular", "label": "Popular"},
            {"slug": "top_rated", "label": "Top Rated"},
            {"slug": "on_the_air", "label": "Airing Now"},
        ],
    },
    MediaTypes.SEASON.value: {
        "sources": [Sources.TMDB],
        "default_source": Sources.TMDB,
        "unicode_icon": "📺",
        "verb": ("watch", "watched"),
        "text_color": COLORS["purple"]["text"],
        "stats_color": COLORS["purple"]["hex"],
        "svg_icon": """
            <path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0
            1.83l8.58 3.91 a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.83Z"/>
            <path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"/>
            <path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"/>""",
        "unit": ("E", "Episode"),
    },
    MediaTypes.EPISODE.value: {
        "sources": [Sources.TMDB],
        "default_source": Sources.TMDB,
        "unicode_icon": "📺",
        "verb": ("watch", "watched"),
        "text_color": COLORS["indigo"]["text"],
        "stats_color": COLORS["indigo"]["hex"],
        "svg_icon": """<polygon points="6 3 20 12 6 21 6 3"/>""",
    },
    MediaTypes.MOVIE.value: {
        "sources": [Sources.TMDB],
        "default_source": Sources.TMDB,
        "sample_query": "The Shawshank Redemption",
        "unicode_icon": "🎬",
        "verb": ("watch", "watched"),
        "text_color": COLORS["orange"]["text"],
        "stats_color": COLORS["orange"]["hex"],
        "svg_icon": """
            <rect width="18" height="18" x="3" y="3" rx="2"/>
            <path d="M7 3v18"/>
            <path d="M3 7.5h4"/>
            <path d="M3 12h18"/>
            <path d="M3 16.5h4"/>
            <path d="M17 3v18"/>
            <path d="M17 7.5h4"/>
            <path d="M17 16.5h4"/>""",
        "date_key": "release_date",
        "explore_categories": [
            {"slug": "trending", "label": "Trending"},
            {"slug": "popular", "label": "Popular"},
            {"slug": "top_rated", "label": "Top Rated"},
            {"slug": "now_playing", "label": "Now Playing"},
        ],
    },
    MediaTypes.ANIME.value: {
        "sources": [Sources.MAL],
        "default_source": Sources.MAL,
        "sample_query": "Perfect Blue",
        "unicode_icon": "🎭",
        "verb": ("watch", "watched"),
        "text_color": COLORS["blue"]["text"],
        "stats_color": COLORS["blue"]["hex"],
        "svg_icon": """
            <circle cx="12" cy="12" r="10"/>
            <polygon points="10 8 16 12 10 16 10 8"/>""",
        "unit": ("E", "Episode"),
        "date_key": "end_date",
        "plural_label": "Anime",
        "explore_categories": [
            {"slug": "all", "label": "Top Rated"},
            {"slug": "airing", "label": "Currently Airing"},
            {"slug": "upcoming", "label": "Upcoming"},
            {"slug": "bypopularity", "label": "Most Popular"},
            {"slug": "seasonal", "label": "Seasonal"},
        ],
    },
    MediaTypes.MANGA.value: {
        "sources": [Sources.MAL, Sources.MANGAUPDATES],
        "default_source": Sources.MAL,
        "sample_query": "Berserk",
        "unicode_icon": "📚",
        "verb": ("read", "read"),
        "text_color": COLORS["red"]["text"],
        "stats_color": COLORS["red"]["hex"],
        "svg_icon": """
            <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2
            0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>
            <path d="M14 2v4a2 2 0 0 0 2 2h4"/>
            <path d="M10 9H8"/>
            <path d="M16 13H8"/>
            <path d="M16 17H8"/>""",
        "date_key": "end_date",
        "unit": ("#", "Chapter"),
        "plural_label": "Manga",
        "explore_categories": [
            {"slug": "all", "label": "Top Rated"},
            {"slug": "bypopularity", "label": "Most Popular"},
            {"slug": "manga", "label": "Top Manga"},
            {"slug": "novels", "label": "Top Novels"},
        ],
    },
    MediaTypes.GAME.value: {
        "sources": [Sources.IGDB],
        "default_source": Sources.IGDB,
        "sample_query": "Half-Life",
        "unicode_icon": "🎮",
        "verb": ("play", "played"),
        "text_color": COLORS["yellow"]["text"],
        "stats_color": COLORS["yellow"]["hex"],
        "svg_icon": """
            <line x1="6" x2="10" y1="11" y2="11"/>
            <line x1="8" x2="8" y1="9" y2="13"/>
            <line x1="15" x2="15.01" y1="12" y2="12"/>
            <line x1="18" x2="18.01" y1="10" y2="10"/>
            <path d="M17.32 5H6.68a4 4 0 0 0-3.978
            3.59c-.006.052-.01.101-.017.152C2.6049.416
            2 14.456 2 16a3 3 0 0 0 3 3c1 0 1.5-.5
            2-1l1.414-1.414A2 2 0 0 1 9.828 16h4.344a2
            2 0 0 1 1.414.586L17 18c.5.5 1 1 2 1a3 3 0 0 0
            3-3c0-1.545-.604-6.584-.685-7.258-.007-.05-.011-.1-.017-.151A4
            4 0 0 0 17.32 5z"/>""",
        "date_key": "release_date",
        "supports_repeat": False,
        "supports_caught_up": False,
        "explore_categories": [
            {"slug": "popular", "label": "Popular"},
            {"slug": "top_rated", "label": "Top Rated"},
            {"slug": "recent", "label": "Recently Released"},
            {"slug": "anticipated", "label": "Most Anticipated"},
        ],
    },
    MediaTypes.BOOK.value: {
        "sources": [Sources.HARDCOVER, Sources.OPENLIBRARY],
        "default_source": Sources.HARDCOVER,
        "sample_query": "The Great Gatsby",
        "unicode_icon": "📖",
        "verb": ("read", "read"),
        "text_color": COLORS["fuchsia"]["text"],
        "stats_color": COLORS["fuchsia"]["hex"],
        "svg_icon": """
            <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5
            2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>""",
        "date_key": "publish_date",
        "unit": ("P", "Page"),
        "explore_categories": [
            {"slug": "trending", "label": "Trending"},
            {"slug": "popular", "label": "Popular"},
            {"slug": "top_rated", "label": "Top Rated"},
        ],
    },
    MediaTypes.COMIC.value: {
        "sources": [Sources.COMICVINE],
        "default_source": Sources.COMICVINE,
        "sample_query": "Batman",
        "unicode_icon": "📕",
        "verb": ("read", "read"),
        "text_color": COLORS["cyan"]["text"],
        "stats_color": COLORS["cyan"]["hex"],
        "svg_icon": """
            <rect width="8" height="18" x="3" y="3" rx="1"/>
            <path d="M7 3v18"/>
            <path d="M20.4 18.9c.2.5-.1 1.1-.6 1.3l-1.9.7c-.5.2-1.1-.1-1.3-.6L11.1
            5.1c-.2-.5.1-1.1.6-1.3l1.9-.7c.5-.2 1.1.1 1.3.6Z"/>""",
        "unit": ("#", "Issue"),
        "explore_categories": [
            {"slug": "recent", "label": "Recently Added"},
            {"slug": "updated", "label": "Recently Updated"},
        ],
    },
    MediaTypes.BOARDGAME.value: {
        "sources": [Sources.BGG],
        "default_source": Sources.BGG,
        "sample_query": "Catan",
        "unicode_icon": "🎲",
        "verb": ("play", "played"),
        "text_color": COLORS["lime"]["text"],
        "stats_color": COLORS["lime"]["hex"],
        "svg_icon": """
            <rect width="18" height="18" x="3" y="3" rx="2" ry="2"/>
            <circle cx="8" cy="8" r="2"/>
            <path d="M16 8h-2"/>
            <circle cx="16" cy="16" r="2"/>
            <path d="M8 16v-2"/>""",
        "unit": ("#", "Play"),
        "date_key": "year",
        "supports_repeat": False,
        "supports_caught_up": False,
        "explore_categories": [
            {"slug": "hot", "label": "Hot"},
        ],
    },
}

# --- Status Configuration ---
STATUS_CONFIG = {
    Status.COMPLETED.value: {
        "text_color": COLORS["emerald"]["text"],
        "stats_color": COLORS["emerald"]["hex"],
        "background_color": COLORS["emerald"]["background"],
    },
    Status.IN_PROGRESS.value: {
        "text_color": COLORS["indigo"]["text"],
        "stats_color": COLORS["indigo"]["hex"],
        "background_color": COLORS["indigo"]["background"],
    },
    Status.PAUSED.value: {
        "text_color": COLORS["orange"]["text"],
        "stats_color": COLORS["orange"]["hex"],
        "background_color": COLORS["orange"]["background"],
    },
    Status.PLANNING.value: {
        "text_color": COLORS["sky"]["text"],
        "stats_color": COLORS["sky"]["hex"],
        "background_color": COLORS["sky"]["background"],
    },
    Status.DROPPED.value: {
        "text_color": COLORS["red"]["text"],
        "stats_color": COLORS["red"]["hex"],
        "background_color": COLORS["red"]["background"],
    },
}


ANIME_SEASONS = [
    {"value": "winter", "label": "Winter"},
    {"value": "spring", "label": "Spring"},
    {"value": "summer", "label": "Summer"},
    {"value": "fall", "label": "Fall"},
]


MONTH_TO_SEASON = {
    1: "winter",
    2: "winter",
    3: "winter",
    4: "spring",
    5: "spring",
    6: "spring",
    7: "summer",
    8: "summer",
    9: "summer",
    10: "fall",
    11: "fall",
    12: "fall",
}

SEASON_START_MONTH = {
    "winter": 1,
    "spring": 4,
    "summer": 7,
    "fall": 10,
}

ANNOUNCED_STATUSES = frozenset(
    {
        "Upcoming",  # MAL: not_yet_aired / not_yet_published
        "Announced",  # TMDB movie
        "In Production",  # TMDB movie/TV
        "Post Production",  # TMDB movie
        "Planned",  # TMDB movie/TV
        "Rumored",  # TMDB movie
    }
)


def is_announced_media(metadata):
    """Return True if the media's status indicates it's not yet released."""
    status = metadata.get("details", {}).get("status", "")
    return status in ANNOUNCED_STATUSES


def get_current_anime_season():
    """Return the current (year, season) tuple for seasonal anime."""
    from django.utils import timezone  # noqa: PLC0415

    now = timezone.now()
    return now.year, MONTH_TO_SEASON[now.month]


def is_upcoming_category(media_type, category, year=None, season_name=None):
    """Return whether the explore category represents upcoming/unreleased media."""
    if category in ("upcoming", "anticipated"):
        return True
    if (
        category == "seasonal"
        and media_type == MediaTypes.ANIME.value
        and year is not None
        and season_name is not None
    ):
        from datetime import date  # noqa: PLC0415

        from django.utils import timezone  # noqa: PLC0415

        start_month = SEASON_START_MONTH.get(season_name)
        if start_month:
            season_start = date(int(year), start_month, 1)
            return timezone.now().date() < season_start
    return False


def get_explore_categories(media_type):
    """Return the browse categories for a media type, or None if not explorable."""
    cfg = get_config(media_type)
    return cfg.get("explore_categories") if cfg else None


def get_explorable_types():
    """Return media type values that support explore/browse."""
    return [mt for mt, cfg in MEDIA_TYPE_CONFIG.items() if "explore_categories" in cfg]


def get_searchable_types():
    """Return media type values that have a sample_query (i.e., are searchable)."""
    return [mt for mt, cfg in MEDIA_TYPE_CONFIG.items() if "sample_query" in cfg]


def get_config(media_type):
    """Get the full config dictionary for a media type."""
    return MEDIA_TYPE_CONFIG.get(media_type)


def get_property(media_type, prop_name):
    """Get a specific property for a media type."""
    config = get_config(media_type)
    try:
        return config[prop_name]
    except KeyError:
        msg = f"Property '{prop_name}' not found for media type '{media_type}'."
        raise KeyError(msg) from None


def get_sources(media_type):
    """Get the list of sources for a media type."""
    return get_property(media_type, "sources")


def get_default_source_name(media_type):
    """Get the human-readable default source name."""
    return get_property(media_type, "default_source")


def get_sample_query(media_type):
    """Get the sample search query."""
    return get_property(media_type, "sample_query")


def get_sample_search_url(media_type):
    """Get the full sample search URL."""
    if media_type == MediaTypes.SEASON.value:
        media_type = MediaTypes.TV.value

    query = get_sample_query(media_type)

    base_url = reverse("search")
    query_params = {"media_type": media_type, "q": query}
    return f"{base_url}?{urlencode(query_params)}"


def get_unicode_icon(media_type):
    """Get the unicode icon."""
    return get_property(media_type, "unicode_icon")


def get_verb(media_type, past_tense):
    """Get the verb (present or past tense)."""
    verbs = get_property(media_type, "verb")
    return verbs[1] if past_tense else verbs[0]


def get_text_color(media_type):
    """Get the text color class."""
    return get_property(media_type, "text_color")


def get_stats_color(media_type):
    """Get the stats color."""
    return get_property(media_type, "stats_color")


def get_svg_icon(media_type):
    """Get the SVG path data."""
    return get_property(media_type, "svg_icon")


def get_date_key(media_type):
    """Get the primary date key used for fetching release/start dates."""
    return get_property(media_type, "date_key")


def get_unit(media_type, short):
    """Get the unit of measurement (e.g., episode, chapter)."""
    cfg = get_config(media_type)
    unit = cfg.get("unit")
    if not unit:
        return ""
    return unit[0] if short else unit[1]


def get_plural_label(media_type):
    """Get the plural label, falling back to singular + 's'."""
    cfg = get_config(media_type)
    return cfg.get("plural_label", f"{MediaTypes(media_type).label}s")


def supports_repeat(media_type):
    """Return whether the media type supports repeat/rewatch tracking."""
    cfg = get_config(media_type)
    return cfg.get("supports_repeat", True)


def supports_caught_up(media_type):
    """Return whether the media type supports caught-up tracking."""
    cfg = get_config(media_type)
    return cfg.get("supports_caught_up", True)


def get_status_config(status):
    """Get the full config dictionary for a status."""
    return STATUS_CONFIG.get(status)


def get_status_property(status, prop_name):
    """Get a specific property for a status."""
    config = get_status_config(status)
    if config is None:
        msg = f"Status '{status}' not found in configuration."
        raise KeyError(msg)
    try:
        return config[prop_name]
    except KeyError:
        msg = f"Property '{prop_name}' not found for status '{status}'."
        raise KeyError(msg) from None


def get_status_text_color(status):
    """Get the text color class for a status."""
    return get_status_property(status, "text_color")


def get_status_stats_color(status):
    """Get the stats color for a status."""
    return get_status_property(status, "stats_color")


def get_status_background_color(status):
    """Get the background color for a status."""
    return get_status_property(status, "background_color")
