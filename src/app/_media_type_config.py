"""Static configuration data for media types and statuses."""

from app._types import MediaTypes, Sources, Status

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
        "supports_recommendations": True,
        "explore_categories": [
            {"slug": "trending", "label": "Trending"},
            {"slug": "popular", "label": "Popular"},
            {"slug": "top_rated", "label": "Top Rated"},
            {"slug": "on_the_air", "label": "Airing Now"},
        ],
        "explore_filters": [
            {
                "key": "sort_by",
                "label": "Sort By",
                "type": "single_select",
                "options_source": "static",
                "options": [
                    {"value": "vote_average", "label": "Top Rated"},
                    {"value": "first_air_date", "label": "Air Date"},
                ],
            },
            {
                "key": "genres",
                "label": "Genres",
                "type": "multi_select",
                "options_source": "provider",
                "provider_key": "tmdb_tv_genres",
                "priority_ids": [
                    18,
                    35,
                    10759,
                    10765,
                    80,
                    9648,
                    10764,
                    99,
                    10751,
                    16,
                    10768,
                    37,
                ],
            },
            {
                "key": "year",
                "label": "Year",
                "type": "year",
            },
            {
                "key": "min_score",
                "label": "Min Rating",
                "type": "preset_buttons",
                "presets": [
                    {"value": "", "label": "Any"},
                    {"value": "5", "label": "5+"},
                    {"value": "6", "label": "6+"},
                    {"value": "7", "label": "7+"},
                    {"value": "8", "label": "8+"},
                    {"value": "9", "label": "9+"},
                ],
            },
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
        "supports_recommendations": True,
        "explore_categories": [
            {"slug": "trending", "label": "Trending"},
            {"slug": "popular", "label": "Popular"},
            {"slug": "top_rated", "label": "Top Rated"},
            {"slug": "now_playing", "label": "Now Playing"},
        ],
        "explore_filters": [
            {
                "key": "sort_by",
                "label": "Sort By",
                "type": "single_select",
                "options_source": "static",
                "options": [
                    {"value": "vote_average", "label": "Top Rated"},
                    {"value": "primary_release_date", "label": "Release Date"},
                    {"value": "revenue", "label": "Revenue"},
                ],
            },
            {
                "key": "genres",
                "label": "Genres",
                "type": "multi_select",
                "options_source": "provider",
                "provider_key": "tmdb_movie_genres",
                "priority_ids": [
                    28,
                    35,
                    18,
                    878,
                    53,
                    27,
                    12,
                    14,
                    10749,
                    80,
                    16,
                    99,
                ],
            },
            {
                "key": "year",
                "label": "Year",
                "type": "year",
            },
            {
                "key": "min_score",
                "label": "Min Rating",
                "type": "preset_buttons",
                "presets": [
                    {"value": "", "label": "Any"},
                    {"value": "5", "label": "5+"},
                    {"value": "6", "label": "6+"},
                    {"value": "7", "label": "7+"},
                    {"value": "8", "label": "8+"},
                    {"value": "9", "label": "9+"},
                ],
            },
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
        "supports_recommendations": True,
        "explore_categories": [
            {"slug": "all", "label": "Top Rated"},
            {"slug": "airing", "label": "Currently Airing"},
            {"slug": "upcoming", "label": "Upcoming"},
            {"slug": "bypopularity", "label": "Most Popular"},
            {"slug": "seasonal", "label": "Seasonal"},
        ],
        "explore_filters": [
            {
                "key": "sort_by",
                "label": "Sort By",
                "type": "single_select",
                "options_source": "static",
                "options": [
                    {"value": "score", "label": "Score"},
                    {"value": "start_date", "label": "Start Date"},
                    {"value": "members", "label": "Members"},
                    {"value": "favorites", "label": "Favorites"},
                ],
            },
            {
                "key": "genres",
                "label": "Genres",
                "type": "multi_select",
                "options_source": "provider",
                "provider_key": "jikan_anime_genres",
                "priority_ids": [
                    1,
                    2,
                    4,
                    8,
                    10,
                    22,
                    24,
                    36,
                    37,
                    14,
                    30,
                    41,
                ],
            },
            {
                "key": "anime_type",
                "label": "Type",
                "type": "single_select",
                "options_source": "static",
                "options": [
                    {"value": "", "label": "All"},
                    {"value": "tv", "label": "TV"},
                    {"value": "movie", "label": "Movie"},
                    {"value": "ova", "label": "OVA"},
                    {"value": "ona", "label": "ONA"},
                    {"value": "special", "label": "Special"},
                    {"value": "music", "label": "Music"},
                ],
            },
            {
                "key": "min_score",
                "label": "Min Score",
                "type": "preset_buttons",
                "presets": [
                    {"value": "", "label": "Any"},
                    {"value": "5", "label": "5+"},
                    {"value": "6", "label": "6+"},
                    {"value": "7", "label": "7+"},
                    {"value": "8", "label": "8+"},
                    {"value": "9", "label": "9+"},
                ],
            },
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
        "supports_recommendations": True,
        "explore_categories": [
            {"slug": "all", "label": "Top Rated"},
            {"slug": "bypopularity", "label": "Most Popular"},
            {"slug": "manga", "label": "Top Manga"},
            {"slug": "novels", "label": "Top Novels"},
        ],
        "explore_filters": [
            {
                "key": "sort_by",
                "label": "Sort By",
                "type": "single_select",
                "options_source": "static",
                "options": [
                    {"value": "score", "label": "Score"},
                    {"value": "start_date", "label": "Start Date"},
                    {"value": "members", "label": "Members"},
                    {"value": "favorites", "label": "Favorites"},
                ],
            },
            {
                "key": "genres",
                "label": "Genres",
                "type": "multi_select",
                "options_source": "provider",
                "provider_key": "jikan_manga_genres",
                "priority_ids": [
                    1,
                    2,
                    4,
                    8,
                    10,
                    22,
                    24,
                    36,
                    37,
                    14,
                    30,
                    41,
                ],
            },
            {
                "key": "manga_type",
                "label": "Type",
                "type": "single_select",
                "options_source": "static",
                "options": [
                    {"value": "", "label": "All"},
                    {"value": "manga", "label": "Manga"},
                    {"value": "novel", "label": "Novel"},
                    {"value": "lightnovel", "label": "Light Novel"},
                    {"value": "oneshot", "label": "One-shot"},
                    {"value": "manhwa", "label": "Manhwa"},
                    {"value": "manhua", "label": "Manhua"},
                ],
            },
            {
                "key": "min_score",
                "label": "Min Score",
                "type": "preset_buttons",
                "presets": [
                    {"value": "", "label": "Any"},
                    {"value": "5", "label": "5+"},
                    {"value": "6", "label": "6+"},
                    {"value": "7", "label": "7+"},
                    {"value": "8", "label": "8+"},
                    {"value": "9", "label": "9+"},
                ],
            },
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
        "supports_recommendations": True,
        "explore_categories": [
            {"slug": "popular", "label": "Popular"},
            {"slug": "top_rated", "label": "Top Rated"},
            {"slug": "recent", "label": "Recently Released"},
            {"slug": "anticipated", "label": "Most Anticipated"},
        ],
        "explore_filters": [
            {
                "key": "sort_by",
                "label": "Sort By",
                "type": "single_select",
                "options_source": "static",
                "options": [
                    {"value": "rating", "label": "Top Rated"},
                    {"value": "date", "label": "Release Date"},
                    {"value": "hype", "label": "Most Hyped"},
                ],
            },
            {
                "key": "genres",
                "label": "Genres",
                "type": "multi_select",
                "options_source": "provider",
                "provider_key": "igdb_genres",
                "priority_ids": [
                    12,
                    5,
                    31,
                    8,
                    15,
                    14,
                    10,
                    9,
                    4,
                    32,
                    13,
                    7,
                ],
            },
            {
                "key": "themes",
                "label": "Themes",
                "type": "multi_select",
                "options_source": "provider",
                "provider_key": "igdb_themes",
                "priority_ids": [
                    1,
                    17,
                    18,
                    19,
                    38,
                    21,
                    44,
                    27,
                    31,
                    28,
                    23,
                    35,
                ],
            },
            {
                "key": "platforms",
                "label": "Platforms",
                "type": "multi_select",
                "options_source": "provider",
                "provider_key": "igdb_platforms",
            },
            {
                "key": "min_score",
                "label": "Min Rating",
                "type": "preset_buttons",
                "presets": [
                    {"value": "", "label": "Any"},
                    {"value": "50", "label": "50+"},
                    {"value": "60", "label": "60+"},
                    {"value": "70", "label": "70+"},
                    {"value": "80", "label": "80+"},
                    {"value": "90", "label": "90+"},
                ],
            },
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
        "supports_recommendations": True,
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

AIRING_CATEGORIES = frozenset({"airing", "on_the_air"})

# --- Discover Page Configuration ---
DISCOVER_SECTIONS = {
    MediaTypes.MOVIE.value: [
        {
            "key": "spotlight",
            "label": "Spotlight",
            "type": "spotlight_carousel",
            "browse_category": "trending",
            "limit": 10,
        },
        {
            "key": "trending",
            "label": "Trending",
            "type": "ranked_carousel",
            "browse_category": "trending",
            "limit": 10,
        },
        {
            "key": "now_playing",
            "label": "Now Playing",
            "type": "card_grid",
            "browse_category": "now_playing",
            "explore_category": "now_playing",
            "limit": 12,
        },
        {
            "key": "upcoming",
            "label": "Upcoming",
            "type": "card_grid",
            "browse_category": "popular",
            "explore_category": "popular",
            "limit": 12,
        },
    ],
    MediaTypes.TV.value: [
        {
            "key": "spotlight",
            "label": "Spotlight",
            "type": "spotlight_carousel",
            "browse_category": "trending",
            "limit": 10,
        },
        {
            "key": "trending",
            "label": "Trending",
            "type": "ranked_carousel",
            "browse_category": "trending",
            "limit": 10,
        },
        {
            "key": "airing_now",
            "label": "Airing Now",
            "type": "card_grid",
            "browse_category": "on_the_air",
            "explore_category": "on_the_air",
            "limit": 12,
        },
        {
            "key": "top_rated",
            "label": "Top Rated",
            "type": "card_grid",
            "browse_category": "top_rated",
            "explore_category": "top_rated",
            "limit": 12,
        },
    ],
    MediaTypes.ANIME.value: [
        {
            "key": "trending",
            "label": "Trending",
            "type": "ranked_carousel",
            "provider": "anilist_trending",
            "limit": 10,
        },
        {
            "key": "recently_updated",
            "label": "Recently Updated",
            "type": "card_grid",
            "provider": "anilist_recently_updated",
            "limit": 30,
        },
        {
            "key": "schedule",
            "label": "Estimated Schedule",
            "type": "schedule_list",
            "provider": "anilist_schedule",
            "limit": 20,
        },
        {
            "key": "upcoming",
            "label": "Upcoming",
            "type": "card_grid",
            "provider": "anilist_upcoming",
            "limit": 30,
        },
    ],
    MediaTypes.MANGA.value: [
        {
            "key": "trending",
            "label": "Trending",
            "type": "ranked_carousel",
            "provider": "anilist_trending",
            "limit": 10,
        },
        {
            "key": "recently_updated",
            "label": "Recently Updated",
            "type": "card_grid",
            "provider": "anilist_recently_updated",
            "limit": 30,
        },
        {
            "key": "upcoming",
            "label": "Upcoming",
            "type": "card_grid",
            "provider": "anilist_upcoming",
            "limit": 30,
        },
    ],
    MediaTypes.GAME.value: [
        {
            "key": "trending",
            "label": "Trending",
            "type": "ranked_carousel",
            "browse_category": "popular",
            "limit": 10,
        },
        {
            "key": "recent",
            "label": "Recently Released",
            "type": "card_grid",
            "browse_category": "recent",
            "explore_category": "recent",
            "limit": 12,
        },
        {
            "key": "anticipated",
            "label": "Most Anticipated",
            "type": "card_grid",
            "browse_category": "anticipated",
            "explore_category": "anticipated",
            "limit": 12,
        },
    ],
}
