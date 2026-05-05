from app.models import Sources
from app.providers import services  # noqa: F401 — re-exported for test patches

from ._backfill_base import BackfillCommand


class Command(BackfillCommand):
    """Backfill empty english_title fields by fetching from providers."""

    help = "Backfill empty english_title fields by fetching from providers"
    field_name = "english_title"
    metadata_key = "english_title"
    label = "MAL"
    queryset_filter = {"english_title": "", "source": Sources.MAL.value}
    queryset_excludes = ()

    def _format_update(self, item, value):
        return f"  Updated: {item.title} -> {value}"

    def _format_error(self, item, error):
        return f"  Error for {item.title} ({item.media_id}): {error}"
