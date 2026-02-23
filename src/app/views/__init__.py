from app.views.actions import (
    backlog_save,
    quick_add,
    quick_archive,
    quick_catch_up,
    quick_complete,
    quick_drop,
    quick_rewatch,
    quick_status_transition,
)
from app.views.crud import (
    create_entry,
    episode_save,
    media_delete,
    media_save,
    track_modal,
)
from app.views.details import (
    media_details,
    season_details,
    sync_metadata,
    update_media_score,
)
from app.views.explore import (
    explore,
    explore_type,
)
from app.views.history import (
    delete_history_record,
    history_modal,
)
from app.views.home import (
    home,
    media_list,
    progress_edit,
)
from app.views.search import (
    media_search,
    search_parent_season,
    search_parent_tv,
    search_suggest_api,
    search_suggest_local,
)
from app.views.stats import (
    service_worker,
    statistics,
)

__all__ = [
    "backlog_save",
    "create_entry",
    "delete_history_record",
    "episode_save",
    "explore",
    "explore_type",
    "history_modal",
    "home",
    "media_delete",
    "media_details",
    "media_list",
    "media_save",
    "media_search",
    "progress_edit",
    "quick_add",
    "quick_archive",
    "quick_catch_up",
    "quick_complete",
    "quick_drop",
    "quick_rewatch",
    "quick_status_transition",
    "search_parent_season",
    "search_parent_tv",
    "search_suggest_api",
    "search_suggest_local",
    "season_details",
    "service_worker",
    "statistics",
    "sync_metadata",
    "track_modal",
    "update_media_score",
]
