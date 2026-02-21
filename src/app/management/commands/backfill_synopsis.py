from django.core.management.base import BaseCommand

from app.models import Item, MediaTypes, Sources
from app.providers import services
from app.providers.services import ProviderAPIError


class Command(BaseCommand):
    """Backfill empty synopsis fields by fetching from providers."""

    help = "Backfill empty synopsis fields by fetching from providers"

    def add_arguments(self, parser):
        """Add --dry-run flag."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )

    def handle(self, **options):
        """Fetch and populate synopsis for items missing it."""
        skip_types = [
            MediaTypes.TV.value,
            MediaTypes.SEASON.value,
            MediaTypes.EPISODE.value,
        ]
        items = (
            Item.objects.filter(synopsis="")
            .exclude(source=Sources.MANUAL.value)
            .exclude(media_type__in=skip_types)
        )

        total = items.count()
        self.stdout.write(f"Found {total} items with empty synopsis")

        updated = 0
        errors = 0
        for item in items.iterator():
            try:
                metadata = services.get_media_metadata(
                    item.media_type, item.media_id, item.source
                )
                synopsis = metadata.get("synopsis", "")
                if synopsis:
                    if not options["dry_run"]:
                        item.synopsis = synopsis
                        item.save(update_fields=["synopsis"])
                    updated += 1
                    self.stdout.write(f"  Updated: {item.title}")
            except ProviderAPIError as e:
                errors += 1
                self.stderr.write(
                    f"  Error for {item.title} ({item.source}/{item.media_id}): {e}"
                )

        prefix = "[DRY RUN] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Done. Updated: {updated}, Errors: {errors}, "
                f"Skipped: {total - updated - errors}"
            )
        )
