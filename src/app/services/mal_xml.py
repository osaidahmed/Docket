"""MAL animelist/mangalist XML export, accepted by MAL, AniList, Kitsu, Anime-Planet."""

import logging
import xml.etree.ElementTree as ET

from app._types import MediaTypes, Sources, Status

logger = logging.getLogger(__name__)

MAL_XML_MEDIA_TYPES = frozenset({MediaTypes.ANIME.value, MediaTypes.MANGA.value})

_NULL_DATE = "0000-00-00"

_ANIME_STATUS_MAP = {
    Status.COMPLETED.value: "Completed",
    Status.IN_PROGRESS.value: "Watching",
    Status.PLANNING.value: "Plan to Watch",
    Status.PAUSED.value: "On-Hold",
    Status.DROPPED.value: "Dropped",
}

_MANGA_STATUS_MAP = {
    Status.COMPLETED.value: "Completed",
    Status.IN_PROGRESS.value: "Reading",
    Status.PLANNING.value: "Plan to Read",
    Status.PAUSED.value: "On-Hold",
    Status.DROPPED.value: "Dropped",
}

_BUCKET_FOR_MAL_STATUS = {
    "Completed": "completed",
    "On-Hold": "on_hold",
    "Dropped": "dropped",
    "Watching": "in_progress",
    "Reading": "in_progress",
    "Plan to Watch": "planning",
    "Plan to Read": "planning",
}


def format_mal_xml(media_list, username, media_type):
    """Return (xml_string, skipped_count); skips entries without a usable MAL id."""
    is_anime = media_type == MediaTypes.ANIME.value
    status_map = _ANIME_STATUS_MAP if is_anime else _MANGA_STATUS_MAP
    build_entry = _build_anime_entry if is_anime else _build_manga_entry

    kept, skipped = _partition_by_mal_id(media_list)

    root = ET.Element("myanimelist")
    totals = _compute_totals(kept, status_map)
    _build_myinfo(root, username, totals, media_type)
    for media in kept:
        build_entry(root, media, status_map)

    if skipped:
        root.insert(0, ET.Comment(f" Skipped {skipped} entries without MAL IDs "))

    ET.indent(root, space="  ")
    body = ET.tostring(root, encoding="unicode", xml_declaration=True)
    return body, skipped


def _partition_by_mal_id(media_list):
    kept = []
    skipped = 0
    for media in media_list:
        if _extract_mal_id(media.item) is None:
            skipped += 1
            continue
        kept.append(media)
    return kept, skipped


def _extract_mal_id(item):
    if item.source != Sources.MAL.value:
        return None
    try:
        return int(item.media_id)
    except (TypeError, ValueError):
        return None


def _format_date(dt):
    if dt is None:
        return _NULL_DATE
    return dt.strftime("%Y-%m-%d")


def _round_score(score):
    if score is None:
        return 0
    return int(score)


def _repeat_count(media):
    repeats = int(getattr(media, "repeats", 1) or 1)
    return max(repeats - 1, 0)


def _compute_totals(entries, status_map):
    totals = {
        "total": len(entries),
        "completed": 0,
        "on_hold": 0,
        "dropped": 0,
        "in_progress": 0,
        "planning": 0,
    }
    for entry in entries:
        mal_status = status_map[entry.status]
        totals[_BUCKET_FOR_MAL_STATUS[mal_status]] += 1
    return totals


def _build_myinfo(root, username, totals, media_type):
    is_anime = media_type == MediaTypes.ANIME.value
    info = ET.SubElement(root, "myinfo")
    ET.SubElement(info, "user_id").text = "0"
    ET.SubElement(info, "user_name").text = username
    ET.SubElement(info, "user_export_type").text = "1" if is_anime else "2"
    total_tag = "user_total_anime" if is_anime else "user_total_manga"
    ET.SubElement(info, total_tag).text = str(totals["total"])
    in_progress_tag = "user_total_watching" if is_anime else "user_total_reading"
    ET.SubElement(info, in_progress_tag).text = str(totals["in_progress"])
    ET.SubElement(info, "user_total_completed").text = str(totals["completed"])
    ET.SubElement(info, "user_total_onhold").text = str(totals["on_hold"])
    ET.SubElement(info, "user_total_dropped").text = str(totals["dropped"])
    plan_tag = "user_total_plantowatch" if is_anime else "user_total_plantoread"
    ET.SubElement(info, plan_tag).text = str(totals["planning"])


def _build_anime_entry(parent, media, status_map):
    entry = ET.SubElement(parent, "anime")
    item = media.item
    ET.SubElement(entry, "series_animedb_id").text = str(int(item.media_id))
    ET.SubElement(entry, "series_title").text = item.title or ""
    ET.SubElement(entry, "my_watched_episodes").text = str(media.progress or 0)
    ET.SubElement(entry, "my_start_date").text = _format_date(media.start_date)
    ET.SubElement(entry, "my_finish_date").text = _format_date(media.end_date)
    ET.SubElement(entry, "my_score").text = str(_round_score(media.score))
    ET.SubElement(entry, "my_status").text = status_map[media.status]
    ET.SubElement(entry, "my_comments").text = media.notes or ""
    ET.SubElement(entry, "my_times_watched").text = str(_repeat_count(media))
    ET.SubElement(entry, "update_on_import").text = "1"


def _build_manga_entry(parent, media, status_map):
    entry = ET.SubElement(parent, "manga")
    item = media.item
    ET.SubElement(entry, "manga_mangadb_id").text = str(int(item.media_id))
    ET.SubElement(entry, "manga_title").text = item.title or ""
    ET.SubElement(entry, "my_read_volumes").text = "0"
    ET.SubElement(entry, "my_read_chapters").text = str(media.progress or 0)
    ET.SubElement(entry, "my_start_date").text = _format_date(media.start_date)
    ET.SubElement(entry, "my_finish_date").text = _format_date(media.end_date)
    ET.SubElement(entry, "my_score").text = str(_round_score(media.score))
    ET.SubElement(entry, "my_status").text = status_map[media.status]
    ET.SubElement(entry, "my_comments").text = media.notes or ""
    ET.SubElement(entry, "my_times_read").text = str(_repeat_count(media))
    ET.SubElement(entry, "update_on_import").text = "1"
