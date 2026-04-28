from django.apps import apps
from django.template.defaultfilters import pluralize

from app import config, helpers
from app.models import MediaTypes, Status
from app.templatetags import app_tags


def process_history_entries(history_records, media_type, media_entry_number, user):
    """Process all history records into timeline entries."""
    timeline_entries = []
    last = history_records.first()

    for _ in range(history_records.count()):
        entry = process_history_entry((last, last.prev_record), media_type, user)
        if entry["changes"]:
            entry["media_entry_number"] = media_entry_number
            timeline_entries.append(entry)
        last = last.prev_record

    return timeline_entries


def process_history_entry(entry, media_type, user):
    """Process a single history entry to organize and format changes."""
    new_record, old_record = entry
    processed_entry = {
        "id": new_record.history_id,
        "date": new_record.history_date,
        "changes": [],
    }

    if old_record is not None:
        delta = new_record.diff_against(old_record)
        changes = organize_changes(delta.changes, media_type, user)
    else:
        history_model = apps.get_model(
            app_label="app",
            model_name=f"historical{media_type}",
        )
        changes = collect_creation_changes(new_record, history_model, media_type, user)

    apply_date_status_integration(changes, user)
    build_changes_list(changes, processed_entry)
    return processed_entry


def organize_changes(changes, media_type, user):
    """Organize changes into categories."""
    organized = {
        "date_changes": {"start_date": None, "end_date": None},
        "status_change": None,
        "other_changes": [],
    }

    end_date_change = None

    for change in changes:
        if change.field == "progress" and media_type == MediaTypes.MOVIE.value:
            continue

        change_data = {
            "description": format_description(
                change.field,
                change.old,
                change.new,
                media_type,
                user,
            ),
            "field": change.field,
            "old": change.old,
            "new": change.new,
        }

        if change.field == "end_date":
            end_date_change = change_data
        else:
            _categorize_change(organized, change.field, change_data)

    if end_date_change:
        organized["date_changes"]["end_date"] = end_date_change

    return organized


_CREATION_SKIP_FIELDS = {"item", "user", "related_tv"}


def _should_skip_creation_field(field, new_record, media_type):
    if field.name.startswith("history_") or field.name == "id":
        return True
    if not hasattr(new_record, field.attname):
        return True
    return field.name == "progress" and media_type == MediaTypes.MOVIE.value


def collect_creation_changes(new_record, history_model, media_type, user):
    """Collect changes for a creation entry."""
    organized = {
        "date_changes": {"start_date": None, "end_date": None},
        "status_change": None,
        "other_changes": [],
    }

    for field in history_model._meta.get_fields():
        if _should_skip_creation_field(field, new_record, media_type):
            continue

        value = getattr(new_record, field.attname, None)
        if not value:
            continue

        change_data = {
            "field": field.name,
            "new": value,
            "description": format_description(
                field.name,
                None,
                value,
                media_type,
                user,
            ),
        }

        _categorize_change(organized, field.name, change_data)

    return organized


def _categorize_change(organized, field_name, change_data):
    if field_name == "status":
        organized["status_change"] = change_data
    elif field_name in organized["date_changes"]:
        organized["date_changes"][field_name] = change_data
    elif field_name not in _CREATION_SKIP_FIELDS:
        organized["other_changes"].append(change_data)


def apply_date_status_integration(changes, user):
    """Integrate status changes with date changes where appropriate."""
    status_change = changes["status_change"]
    if not status_change:
        return

    date_changes = changes["date_changes"]
    new_status = status_change["new"]

    if date_changes["start_date"] and new_status == Status.IN_PROGRESS.value:
        formatted = app_tags.date_format(date_changes["start_date"]["new"], user)
        date_changes["start_date"]["description"] = f"Started on {formatted}"
        changes["status_change"] = None
    elif date_changes["end_date"] and new_status == Status.COMPLETED.value:
        formatted = app_tags.date_format(date_changes["end_date"]["new"], user)
        date_changes["end_date"]["description"] = f"Finished on {formatted}"
        changes["status_change"] = None


def build_changes_list(changes, processed_entry):
    """Build the final changes list in the desired order."""
    # Add date changes
    if changes["date_changes"]["start_date"]:
        processed_entry["changes"].append(changes["date_changes"]["start_date"])
    if changes["date_changes"]["end_date"]:
        processed_entry["changes"].append(changes["date_changes"]["end_date"])

    # Add status if not integrated with dates
    if changes["status_change"]:
        processed_entry["changes"].append(changes["status_change"])

    # Add other changes
    processed_entry["changes"].extend(changes["other_changes"])


def format_description(field_name, old_value, new_value, media_type=None, user=None):
    """Format change description in a human-readable way."""
    if field_name in {"start_date", "end_date"}:
        new_value = app_tags.date_format(new_value, user)
        old_value = app_tags.date_format(old_value, user)

    if old_value is None:
        formatter = _INITIAL_FORMATTERS.get(field_name, _fmt_generic_initial)
        return formatter(field_name, new_value, media_type)

    formatter = _CHANGE_FORMATTERS.get(field_name, _fmt_generic_change)
    return formatter(field_name, old_value, new_value, media_type)


_STATUS_INITIAL_TEMPLATES = {
    Status.IN_PROGRESS.value: "Marked as currently {verb}ing",
    Status.COMPLETED.value: "Marked as finished {verb}ing",
    Status.PLANNING.value: "Added to {verb}ing list",
    Status.PAUSED.value: "Marked as paused {verb}ing",
}


def _fmt_status_initial(_field_name, new_value, media_type):
    if new_value == Status.DROPPED.value:
        return "Marked as dropped"
    template = _STATUS_INITIAL_TEMPLATES.get(new_value)
    if template is None:
        return f"Set status to {new_value}"
    return template.format(verb=config.get_verb(media_type, past_tense=False))


def _fmt_score_initial(_field_name, new_value, _media_type):
    return f"Rated {new_value}/10"


def _fmt_progress_initial(_field_name, new_value, media_type):
    if not media_type:
        return f"Set progress to {new_value}"
    verb = config.get_verb(media_type, past_tense=True).title()
    if media_type == MediaTypes.GAME.value:
        return f"{verb} for {helpers.minutes_to_hhmm(new_value)}"
    unit = config.get_unit(media_type, short=False).lower()
    return f"{verb} up to {unit} {new_value}"


def _fmt_date_initial(field_name, new_value, _media_type):
    label = "Started" if field_name == "start_date" else "Finished"
    return f"{label} on {new_value}"


def _fmt_notes_initial(_field_name, _new_value, _media_type):
    return "Added notes"


def _fmt_generic_initial(field_name, new_value, _media_type):
    return f"Set {field_name.replace('_', ' ').lower()} to {new_value}"


def _fmt_status_change(_field_name, old_value, new_value, media_type):
    verb = config.get_verb(media_type, past_tense=False)
    transitions = {
        (Status.PLANNING.value, Status.IN_PROGRESS.value): f"Currently {verb}ing",
        (Status.IN_PROGRESS.value, Status.COMPLETED.value): f"Finished {verb}ing",
        (Status.IN_PROGRESS.value, Status.PAUSED.value): f"Paused {verb}ing",
        (Status.PAUSED.value, Status.IN_PROGRESS.value): f"Resumed {verb}ing",
        (Status.IN_PROGRESS.value, Status.DROPPED.value): f"Stopped {verb}ing",
    }
    return transitions.get(
        (old_value, new_value),
        f"Changed status from {old_value} to {new_value}",
    )


def _fmt_score_change(_field_name, old_value, new_value, _media_type):
    if old_value == 0:
        return f"Rated {new_value}/10"
    return f"Changed rating from {old_value} to {new_value}"


def _fmt_progress_change(_field_name, old_value, new_value, media_type):
    diff = new_value - old_value
    diff_abs = abs(diff)

    if media_type == MediaTypes.GAME.value:
        if diff > 0:
            return f"Added {helpers.minutes_to_hhmm(diff_abs)} of playtime"
        return f"Removed {helpers.minutes_to_hhmm(diff_abs)} of playtime"

    unit = f"{config.get_unit(media_type, short=False).lower()}{pluralize(new_value)}"
    return f"Progress set to {new_value} {unit}"


def _fmt_date_change(field_name, old_value, new_value, _media_type):
    label = "Start" if field_name == "start_date" else "End"
    if not new_value:
        return f"Removed {label.lower()} date"
    if not old_value:
        return f"{label}ed on {new_value}"
    return f"{label} date changed to {new_value}"


def _fmt_notes_change(_field_name, old_value, new_value, _media_type):
    if not old_value:
        return "Added notes"
    if not new_value:
        return "Removed notes"
    return "Updated notes"


def _fmt_generic_change(field_name, old_value, new_value, _media_type):
    field_label = field_name.replace("_", " ").lower()
    return f"Updated {field_label} from {old_value} to {new_value}"


_INITIAL_FORMATTERS = {
    "status": _fmt_status_initial,
    "score": _fmt_score_initial,
    "progress": _fmt_progress_initial,
    "start_date": _fmt_date_initial,
    "end_date": _fmt_date_initial,
    "notes": _fmt_notes_initial,
}

_CHANGE_FORMATTERS = {
    "status": _fmt_status_change,
    "score": _fmt_score_change,
    "progress": _fmt_progress_change,
    "start_date": _fmt_date_change,
    "end_date": _fmt_date_change,
    "notes": _fmt_notes_change,
}
