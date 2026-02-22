from django.core.management.base import BaseCommand

from app.models import Item, Sources
from app.providers import services
from app.providers.services import ProviderAPIError


class Command(BaseCommand):
    """Backfill empty english_title fields by fetching from providers."""

    help = "Backfill empty english_title fields by fetching from providers"

    def add_arguments(self, parser):
        """Add --dry-run flag."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )

    def handle(self, **options):
        """Fetch and populate english_title for MAL items missing it."""
        items = Item.objects.filter(
            english_title="",
            source=Sources.MAL.value,
        )

        total = items.count()
        self.stdout.write(f"Found {total} MAL items with empty english_title")

        updated = 0
        errors = 0
        for item in items.iterator():
            try:
                metadata = services.get_media_metadata(
                    item.media_type, item.media_id, item.source
                )
                english_title = metadata.get("english_title", "")
                if english_title:
                    if not options["dry_run"]:
                        item.english_title = english_title
                        item.save(update_fields=["english_title"])
                    updated += 1
                    self.stdout.write(f"  Updated: {item.title} -> {english_title}")
            except ProviderAPIError as e:
                errors += 1
                self.stderr.write(f"  Error for {item.title} ({item.media_id}): {e}")

        prefix = "[DRY RUN] " if options["dry_run"] else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Done. Updated: {updated}, Errors: {errors}, "
                f"Skipped: {total - updated - errors}"
            )
        )
