from app.views.actions import (
    backlog_save,
    bulk_action,
    quick_add,
    quick_archive,
    quick_catch_up,
    quick_catch_up_add,
    quick_complete,
    quick_drop,
    quick_rewatch,
    quick_status_transition,
    quick_untrack,
    save_pin_order,
    toggle_pin,
)
from app.views.add_by_link import (
    add_by_link,
    add_by_link_process,
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
from app.views.discover import (
    explore_section,
)
from app.views.explore import (
    explore,
    explore_type,
)
from app.views.export import (
    export_media,
    export_media_txt,
    print_media,
)
from app.views.history import (
    delete_history_record,
    history_modal,
)
from app.views.home import (
    home,
    media_list,
    progress_edit,
    recommendations_section,
    toggle_grouping,
)
from app.views.search import (
    media_search,
    search_parent_season,
    search_parent_tv,
    search_suggest_api,
    search_suggest_local,
    search_suggest_recent,
)
from app.views.stats import (
    service_worker,
    statistics,
)

__all__ = [
    "add_by_link",
    "add_by_link_process",
    "backlog_save",
    "bulk_action",
    "create_entry",
    "delete_history_record",
    "episode_save",
    "explore",
    "explore_section",
    "explore_type",
    "export_media",
    "export_media_txt",
    "history_modal",
    "home",
    "media_delete",
    "media_details",
    "media_list",
    "media_save",
    "media_search",
    "print_media",
    "progress_edit",
    "quick_add",
    "quick_archive",
    "quick_catch_up",
    "quick_catch_up_add",
    "quick_complete",
    "quick_drop",
    "quick_rewatch",
    "quick_status_transition",
    "quick_untrack",
    "recommendations_section",
    "save_pin_order",
    "search_parent_season",
    "search_parent_tv",
    "search_suggest_api",
    "search_suggest_local",
    "search_suggest_recent",
    "season_details",
    "service_worker",
    "statistics",
    "sync_metadata",
    "toggle_grouping",
    "toggle_pin",
    "track_modal",
    "update_media_score",
]
