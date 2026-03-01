import csv
import io
import json
from collections import defaultdict

EXPORT_FIELDS = [
    "title",
    "english_title",
    "score",
    "progress",
    "max_progress",
    "status",
    "start_date",
    "end_date",
    "notes",
    "link",
    "is_rewatch",
    "caught_up",
    "source",
]


def serialize_media_list(media_list, media_type):
    """Convert an annotated media list to a list of export dicts."""
    rows = []
    for media in media_list:
        row = {
            "title": media.item.title,
            "english_title": media.item.english_title or "",
            "score": (str(media.formatted_score) if media.score is not None else ""),
            "progress": media.formatted_progress,
            "max_progress": (str(media.max_progress) if media.max_progress else ""),
            "status": media.status,
            "start_date": (
                media.start_date.strftime("%Y-%m-%d") if media.start_date else ""
            ),
            "end_date": (media.end_date.strftime("%Y-%m-%d") if media.end_date else ""),
            "notes": media.notes or "",
            "link": media.link or "",
            "is_rewatch": "Yes" if media.is_rewatch else "No",
            "caught_up": "Yes" if media.caught_up else "No",
            "source": media.item.source,
        }
        rows.append(row)
    return rows


def format_csv(rows):
    """Return CSV string from list of dicts."""
    if not rows:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=rows[0].keys(),
        quoting=csv.QUOTE_ALL,
    )
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def format_json(rows):
    """Return JSON string from list of dicts."""
    return json.dumps(rows, indent=2, ensure_ascii=False)


def format_markdown(rows):
    """Return Markdown table string from list of dicts."""
    if not rows:
        return ""
    headers = list(rows[0].keys())
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")
    for row in rows:
        cells = [
            str(row.get(h, "")).replace("|", "\\|").replace("\n", " ") for h in headers
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def format_txt(rows, template, separator="\n"):
    """Apply a user template to each row and join with separator."""
    lines = []
    for row in rows:
        mapping = defaultdict(str, row)
        lines.append(template.format_map(mapping))
    return separator.join(lines)
