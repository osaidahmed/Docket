from app.models import MediaTypes, Sources
from app.providers import services  # noqa: F401 — re-exported for test patches

from ._backfill_base import BackfillCommand


class Command(BackfillCommand):
    """Backfill empty synopsis fields by fetching from providers."""

    help = "Backfill empty synopsis fields by fetching from providers"
    field_name = "synopsis"
    metadata_key = "synopsis"
    label = ""
    queryset_filter = {"synopsis": ""}
    queryset_excludes = (
        {"source": Sources.MANUAL.value},
        {
            "media_type__in": [
                MediaTypes.TV.value,
                MediaTypes.SEASON.value,
                MediaTypes.EPISODE.value,
            ]
        },
    )
