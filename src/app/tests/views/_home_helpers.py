"""Shared helpers for home view test files."""

from app.models import Item

_DEFAULT_IMAGE = "http://example.com/image.jpg"


def create_item(media_id, source, media_type, title, **kwargs):
    """Create an Item with default image."""
    return Item.objects.create(
        media_id=media_id,
        source=source,
        media_type=media_type,
        title=title,
        image=_DEFAULT_IMAGE,
        **kwargs,
    )


def backlog_save_data(media):
    """Build POST data for backlog_save from a media instance."""
    return {
        "media_id": media.item.media_id,
        "source": media.item.source,
        "media_type": media.item.media_type,
        "instance_id": media.id,
        "score": "",
        "progress": media.progress if media.progress is not None else "",
        "status": media.status,
        "start_date": "",
        "end_date": "",
        "notes": "",
        "link": "",
    }
