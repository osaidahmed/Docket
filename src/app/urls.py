from django.urls import path, register_converter

from app import converters, views

register_converter(converters.MediaTypeChecker, "media_type")
register_converter(converters.SourceChecker, "source")


urlpatterns = [
    path("", views.home, name="home"),
    path("medialist/<media_type:media_type>", views.media_list, name="medialist"),
    path(
        "medialist/<media_type:media_type>/export/",
        views.export_media,
        name="export_media",
    ),
    path(
        "medialist/<media_type:media_type>/export/txt/",
        views.export_media_txt,
        name="export_media_txt",
    ),
    path(
        "medialist/<media_type:media_type>/print/",
        views.print_media,
        name="print_media",
    ),
    path("search", views.media_search, name="search"),
    path("explore", views.explore, name="explore"),
    path(
        "explore/<media_type:media_type>",
        views.explore_type,
        name="explore_type",
    ),
    path(
        "details/<source:source>/<media_type:media_type>/<str:media_id>/<str:title>",
        views.media_details,
        name="media_details",
    ),
    path(
        "details/<source:source>/tv/<str:media_id>/<str:title>/season/<int:season_number>",
        views.season_details,
        name="season_details",
    ),
    path(
        "update-score/<media_type:media_type>/<int:instance_id>",
        views.update_media_score,
        name="update_media_score",
    ),
    path(
        "details/sync/<source:source>/<media_type:media_type>/<str:media_id>",
        views.sync_metadata,
        name="sync_metadata",
    ),
    path(
        "details/sync/<source:source>/<media_type:media_type>/<str:media_id>/<int:season_number>",
        views.sync_metadata,
        name="sync_metadata",
    ),
    path(
        "track_modal/<source:source>/<media_type:media_type>/<str:media_id>",
        views.track_modal,
        name="track_modal",
    ),
    path(
        "track_modal/<source:source>/<media_type:media_type>/<str:media_id>/<int:season_number>",
        views.track_modal,
        name="track_modal",
    ),
    path(
        "progress_edit/<media_type:media_type>/<int:instance_id>",
        views.progress_edit,
        name="progress_edit",
    ),
    path("media_save", views.media_save, name="media_save"),
    path("quick_add", views.quick_add, name="quick_add"),
    path("quick_archive", views.quick_archive, name="quick_archive"),
    path("quick_complete", views.quick_complete, name="quick_complete"),
    path("quick_drop", views.quick_drop, name="quick_drop"),
    path("quick_catch_up", views.quick_catch_up, name="quick_catch_up"),
    path("quick_rewatch", views.quick_rewatch, name="quick_rewatch"),
    path(
        "quick_status_transition",
        views.quick_status_transition,
        name="quick_status_transition",
    ),
    path("backlog_save", views.backlog_save, name="backlog_save"),
    path("quick_untrack", views.quick_untrack, name="quick_untrack"),
    path("media_delete", views.media_delete, name="media_delete"),
    path("episode_save", views.episode_save, name="episode_save"),
    path(
        "history_modal/<source:source>/<media_type:media_type>/<str:media_id>",
        views.history_modal,
        name="history_modal",
    ),
    path(
        "history_modal/<source:source>/<media_type:media_type>/<str:media_id>/<int:season_number>",
        views.history_modal,
        name="history_modal",
    ),
    path(
        "history_modal/<source:source>/<media_type:media_type>/<str:media_id>/<int:season_number>/<int:episode_number>",
        views.history_modal,
        name="history_modal",
    ),
    path(
        "media/history/<str:media_type>/<int:history_id>/delete/",
        views.delete_history_record,
        name="delete_history_record",
    ),
    path("create", views.create_entry, name="create_entry"),
    path("add_by_link", views.add_by_link, name="add_by_link"),
    path(
        "add_by_link/process",
        views.add_by_link_process,
        name="add_by_link_process",
    ),
    path("search/parent_tv", views.search_parent_tv, name="search_parent_tv"),
    path(
        "search/parent_season",
        views.search_parent_season,
        name="search_parent_season",
    ),
    path(
        "search/suggest/local",
        views.search_suggest_local,
        name="search_suggest_local",
    ),
    path(
        "search/suggest/api",
        views.search_suggest_api,
        name="search_suggest_api",
    ),
    path(
        "search/suggest/recent",
        views.search_suggest_recent,
        name="search_suggest_recent",
    ),
    path("statistics", views.statistics, name="statistics"),
    path("serviceworker.js", views.service_worker, name="service_worker"),
]
