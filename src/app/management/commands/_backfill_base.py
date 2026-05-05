from django.core.management.base import BaseCommand

from app.models import Item
from app.providers import services
from app.providers.services import ProviderAPIError


class BackfillCommand(BaseCommand):
    """Shared backfill loop driven by subclass class-attributes."""

    field_name: str = ""
    metadata_key: str = ""
    label: str = ""
    queryset_filter: dict | None = None
    queryset_excludes: tuple[dict, ...] = ()

    def add_arguments(self, parser):
        """Add the --dry-run flag."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )

    def handle(self, **options):
        """Iterate matching items and persist metadata-derived field values."""
        items = Item.objects.filter(**(self.queryset_filter or {}))
        for exclude_kwargs in self.queryset_excludes:
            items = items.exclude(**exclude_kwargs)

        total = items.count()
        self.stdout.write(
            f"Found {total} {self.label} items with empty {self.field_name}"
        )

        updated = 0
        errors = 0
        for item in items.iterator():
            try:
                metadata = services.get_media_metadata(
                    item.media_type, item.media_id, item.source
                )
                value = metadata.get(self.metadata_key, "")
                if value:
                    if not options["dry_run"]:
                        setattr(item, self.field_name, value)
                        item.save(update_fields=[self.field_name])
                    updated += 1
                    self.stdout.write(self._format_update(item, value))
            except ProviderAPIError as e:
                errors += 1
                self.stderr.write(self._format_error(item, e))

        prefix = "[DRY RUN] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Done. Updated: {updated}, Errors: {errors}, "
                f"Skipped: {total - updated - errors}"
            )
        )

    def _format_update(self, item, value):  # noqa: ARG002
        """Format the success log line; subclasses may override."""
        return f"  Updated: {item.title}"

    def _format_error(self, item, error):
        """Format the error log line; subclasses may override."""
        return f"  Error for {item.title} ({item.source}/{item.media_id}): {error}"
