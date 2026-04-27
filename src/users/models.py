import secrets

from django.contrib.auth.models import AbstractUser
from django.db import models
from django_celery_beat.models import PeriodicTask
from django_celery_results.models import TaskResult

from app.models import Item, MediaTypes, Status
from users import helpers

EXCLUDED_SEARCH_TYPES = [MediaTypes.SEASON.value, MediaTypes.EPISODE.value]

VALID_SEARCH_TYPES = [
    value for value in MediaTypes.values if value not in EXCLUDED_SEARCH_TYPES
]


def generate_token():
    """Generate a user token."""
    return secrets.token_urlsafe(24)


class HomeSortChoices(models.TextChoices):
    """Choices for home page sort options."""

    UPCOMING = "upcoming", "Upcoming"
    RECENT = "recent", "Recent"
    COMPLETION = "completion", "Completion"
    EPISODES_LEFT = "episodes_left", "Episodes Left"
    TITLE = "title", "Title"


class HomeTruncationChoices(models.TextChoices):
    """Choices for home page category truncation."""

    THREE = "3", "3"
    FIVE = "5", "5"
    TEN = "10", "10"
    ALL = "0", "All"


class HomeLayoutChoices(models.TextChoices):
    """Choices for home page layout options."""

    CARDS = "cards", "Cards"
    GRID = "grid", "Grid"
    TABLE = "table", "Table"


class HomeGroupChoices(models.TextChoices):
    """Choices for home page grouping options."""

    TYPE = "type", "Type"
    STATUS = "status", "Status"


class ArchiveSortChoices(models.TextChoices):
    """Choices for archive page sort options."""

    SCORE = "score", "Score"
    TITLE = "title", "Title"
    START_DATE = "start_date", "Start Date"
    END_DATE = "end_date", "End Date"


class MediaSortChoices(models.TextChoices):
    """Choices for media list sort options."""

    SCORE = "score", "Score"
    TITLE = "title", "Title"
    PROGRESS = "progress", "Progress"
    STATUS = "status", "Status"
    START_DATE = "start_date", "Start Date"
    END_DATE = "end_date", "End Date"


class MediaStatusChoices(models.TextChoices):
    """Choices for media list status options."""

    ALL = "All", "All"
    COMPLETED = Status.COMPLETED.value, Status.COMPLETED.label
    IN_PROGRESS = Status.IN_PROGRESS.value, Status.IN_PROGRESS.label
    PLANNING = Status.PLANNING.value, Status.PLANNING.label
    PAUSED = Status.PAUSED.value, Status.PAUSED.label
    DROPPED = Status.DROPPED.value, Status.DROPPED.label


class LayoutChoices(models.TextChoices):
    """Choices for media list layout options."""

    CARDS = "cards", "Cards"
    GRID = "grid", "Grid"
    TABLE = "table", "Table"


class CalendarLayoutChoices(models.TextChoices):
    """Choices for calendar layout options."""

    GRID = "grid", "Grid"
    LIST = "list", "List"


class ListSortChoices(models.TextChoices):
    """Choices for list sort options."""

    LAST_ITEM_ADDED = "last_item_added", "Last Item Added"
    NAME = "name", "Name"
    ITEMS_COUNT = "items_count", "Items Count"
    NEWEST_FIRST = "newest_first", "Newest First"


class ListDetailSortChoices(models.TextChoices):
    """Choices for list detail sort options."""

    DATE_ADDED = "date_added", "Date Added"
    TITLE = "title", "Title"
    MEDIA_TYPE = "media_type", "Media Type"


class QuickWatchDateChoices(models.TextChoices):
    """Choices for quick watch date behavior when bulk-marking media as completed."""

    CURRENT_DATE = "current_date", "Current Date"
    RELEASE_DATE = "release_date", "Release Date"
    NO_DATE = "no_date", "No Date"


class DateFormatChoices(models.TextChoices):
    """Choices for date format display."""

    ISO = "Y-m-d", "2026-01-18 (ISO)"
    EUROPEAN = "d/m/Y", "18/01/2026 (EU)"
    US = "m/d/Y", "01/18/2026 (US)"
    LONG = "M j, Y", "Jan 18, 2026"


class TimeFormatChoices(models.TextChoices):
    """Choices for time format display."""

    HOUR_24 = "H:i", "14:30 (24-hour)"
    HOUR_12 = "g:i A", "2:30 PM (12-hour)"


PER_TYPE_FIELDS = {"enabled", "layout", "sort", "status"}

PER_TYPE_LAYOUT_DEFAULTS = {
    "anime": "table",
    "manga": "table",
}

BUILTIN_MEDIA_TYPES = frozenset(
    {"tv", "season", "movie", "anime", "manga", "game", "book", "comic", "boardgame"},
)


class UserMediaPreference(models.Model):
    """Per-media-type preferences (layout, sort, status filter, enabled)."""

    user = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="media_preferences",
    )
    media_type = models.CharField(max_length=20)
    enabled = models.BooleanField(default=True)
    layout = models.CharField(
        max_length=20,
        choices=LayoutChoices.choices,
        default=LayoutChoices.GRID,
    )
    sort = models.CharField(
        max_length=20,
        choices=MediaSortChoices.choices,
        default=MediaSortChoices.SCORE,
    )
    status_filter = models.CharField(
        max_length=20,
        choices=MediaStatusChoices.choices,
        default=MediaStatusChoices.ALL,
    )

    class Meta:
        """Database constraints for UserMediaPreference."""

        constraints = [
            models.UniqueConstraint(
                fields=["user", "media_type"],
                name="unique_user_media_pref",
            ),
        ]

    def __str__(self):
        """Return a human-readable identifier for this preference row."""
        return f"{self.user.username} - {self.media_type}"


def _value_in_field_choices(value, field):
    """Return True if value is acceptable for field (choices-bound or free-form)."""
    if not (hasattr(field, "choices") and field.choices):
        return True
    return value in {choice[0] for choice in field.choices}


_IMPORT_TASKS = {
    "trakt": "Import from Trakt",
    "simkl": "Import from SIMKL",
    "myanimelist": "Import from MyAnimeList",
    "anilist": "Import from AniList",
    "kitsu": "Import from Kitsu",
    "docket": "Import from Docket",
    "hltb": "Import from HowLongToBeat",
    "steam": "Import from Steam",
    "imdb": "Import from IMDB",
    "goodreads": "Import from GoodReads",
}
_TASK_TO_SOURCE = {v: k for k, v in _IMPORT_TASKS.items()}


class User(AbstractUser):
    """Custom user model."""

    is_demo = models.BooleanField(default=False)

    last_search_type = models.CharField(
        max_length=10,
        default=MediaTypes.TV.value,
        choices=MediaTypes.choices,
    )

    home_sort = models.CharField(
        max_length=20,
        default=HomeSortChoices.UPCOMING,
        choices=HomeSortChoices.choices,
    )

    archive_sort = models.CharField(
        max_length=20,
        default=ArchiveSortChoices.END_DATE,
        choices=ArchiveSortChoices.choices,
    )

    home_truncation = models.CharField(
        max_length=2,
        default=HomeTruncationChoices.ALL,
        choices=HomeTruncationChoices.choices,
    )

    # Media type ordering
    media_type_order = models.JSONField(default=list, blank=True)

    # Home page default type filter (empty list = all types)
    home_default_types = models.JSONField(default=list, blank=True)

    # Per-media-type external link preferences. Each value is a mapping with
    # optional "provider" (site id from link_providers.registry) and "template"
    # (URL string with {title}/{english_title}/{year} placeholders) keys.
    link_preferences = models.JSONField(default=dict, blank=True)

    # Home page layout and grouping
    home_layout = models.CharField(
        max_length=20,
        default=HomeLayoutChoices.CARDS,
        choices=HomeLayoutChoices.choices,
    )
    home_group = models.CharField(
        max_length=20,
        default=HomeGroupChoices.TYPE,
        choices=HomeGroupChoices.choices,
    )

    # Export preferences
    export_txt_config = models.JSONField(default=dict, blank=True)

    # Color scheme
    COLOR_SCHEME_CHOICES = [
        ("charcoal", "Charcoal"),
        ("ocean", "Ocean"),
        ("twilight", "Twilight"),
        ("forest", "Forest"),
        ("ember", "Ember"),
        ("sakura", "Sakura"),
    ]
    color_scheme = models.CharField(
        max_length=20,
        choices=COLOR_SCHEME_CHOICES,
        default="charcoal",
    )

    # UI preferences
    clickable_media_cards = models.BooleanField(
        default=False,
        help_text="Hide hover overlay on touch devices",
    )

    # Tracking settings
    quick_watch_date = models.CharField(
        max_length=20,
        default=QuickWatchDateChoices.CURRENT_DATE,
        choices=QuickWatchDateChoices.choices,
        help_text="Date to use when bulk-marking media as completed",
    )

    date_format = models.CharField(
        max_length=20,
        default=DateFormatChoices.ISO,
        choices=DateFormatChoices.choices,
        help_text="Preferred date display format",
    )
    time_format = models.CharField(
        max_length=20,
        default=TimeFormatChoices.HOUR_24,
        choices=TimeFormatChoices.choices,
        help_text="Preferred time display format",
    )

    # Progress bar
    progress_bar = models.BooleanField(
        default=True,
        help_text="Show progress bar",
    )

    # Hide completed recommendations
    hide_completed_recommendations = models.BooleanField(
        default=False,
        help_text="Hide completed media in recommendations",
    )

    # Hide zero ratings
    hide_zero_rating = models.BooleanField(
        default=False,
        help_text="Hide zero ratings from media cards",
    )

    # Group related media
    group_related_media = models.BooleanField(
        default=False,
        help_text="Group related seasons and sequels on list pages",
    )

    # Calendar preferences
    calendar_layout = models.CharField(
        max_length=20,
        default=CalendarLayoutChoices.GRID,
        choices=CalendarLayoutChoices.choices,
    )

    # Lists preferences
    lists_sort = models.CharField(
        max_length=20,
        default=ListSortChoices.LAST_ITEM_ADDED,
        choices=ListSortChoices.choices,
    )
    list_detail_sort = models.CharField(
        max_length=20,
        default=ListDetailSortChoices.DATE_ADDED,
        choices=ListDetailSortChoices.choices,
    )
    list_detail_status = models.CharField(
        max_length=20,
        default=MediaStatusChoices.ALL,
        choices=MediaStatusChoices.choices,
    )

    # Notification settings
    notification_urls = models.TextField(
        blank=True,
        help_text="Apprise URLs for notifications",
    )
    notification_excluded_items = models.ManyToManyField(
        Item,
        related_name="excluded_by_users",
        blank=True,
        help_text="Items excluded from notifications",
    )
    release_notifications_enabled = models.BooleanField(
        default=True,
        help_text="Receive notifications for recently released media",
    )
    daily_digest_enabled = models.BooleanField(
        default=True,
        help_text="Receive a daily digest of upcoming releases",
    )

    # Integration settings
    token = models.CharField(
        max_length=32,
        unique=True,
        default=generate_token,
        help_text="Token for external integrations",
    )
    plex_usernames = models.TextField(
        blank=True,
        help_text="Comma-separated list of Plex usernames for webhook matching",
    )

    class Meta:
        """Meta options for the model."""

        ordering = ["username"]
        constraints = [
            models.CheckConstraint(
                name="last_search_type_valid",
                condition=models.Q(last_search_type__in=VALID_SEARCH_TYPES),
            ),
            models.CheckConstraint(
                name="home_layout_valid",
                condition=models.Q(home_layout__in=HomeLayoutChoices.values),
            ),
            models.CheckConstraint(
                name="home_group_valid",
                condition=models.Q(home_group__in=HomeGroupChoices.values),
            ),
            models.CheckConstraint(
                name="home_sort_valid",
                condition=models.Q(home_sort__in=HomeSortChoices.values),
            ),
            models.CheckConstraint(
                name="archive_sort_valid",
                condition=models.Q(archive_sort__in=ArchiveSortChoices.values),
            ),
            models.CheckConstraint(
                name="home_truncation_valid",
                condition=models.Q(home_truncation__in=HomeTruncationChoices.values),
            ),
            models.CheckConstraint(
                name="calendar_layout_valid",
                condition=models.Q(calendar_layout__in=CalendarLayoutChoices.values),
            ),
            models.CheckConstraint(
                name="lists_sort_valid",
                condition=models.Q(lists_sort__in=ListSortChoices.values),
            ),
            models.CheckConstraint(
                name="list_detail_sort_valid",
                condition=models.Q(list_detail_sort__in=ListDetailSortChoices.values),
            ),
            models.CheckConstraint(
                name="list_detail_status_valid",
                condition=models.Q(list_detail_status__in=MediaStatusChoices.values),
            ),
            models.CheckConstraint(
                name="quick_watch_date_valid",
                condition=models.Q(quick_watch_date__in=QuickWatchDateChoices.values),
            ),
        ]

    @staticmethod
    def _parse_per_type_field(field_name):
        """Parse 'tv_layout' → ('tv', 'layout'). Returns None if not per-type."""
        for suffix in PER_TYPE_FIELDS:
            if field_name.endswith(f"_{suffix}"):
                media_type = field_name[: -(len(suffix) + 1)]
                if media_type and media_type in BUILTIN_MEDIA_TYPES:
                    return media_type, suffix
        return None

    def get_media_pref(self, media_type):
        """Return the UserMediaPreference for this media type, or None."""
        if not hasattr(self, "_pref_cache"):
            self._pref_cache = {p.media_type: p for p in self.media_preferences.all()}
        return self._pref_cache.get(media_type)

    def get_or_create_media_pref(self, media_type):
        """Return the UserMediaPreference, creating with defaults if missing."""
        pref = self.get_media_pref(media_type)
        if pref is None:
            defaults = {
                "layout": PER_TYPE_LAYOUT_DEFAULTS.get(
                    media_type,
                    LayoutChoices.GRID,
                ),
            }
            pref, _ = UserMediaPreference.objects.get_or_create(
                user=self,
                media_type=media_type,
                defaults=defaults,
            )
            if hasattr(self, "_pref_cache"):
                self._pref_cache[media_type] = pref
        return pref

    def _is_valid_preference(self, field_name, new_value):
        if field_name == "last_search_type":
            return new_value in VALID_SEARCH_TYPES
        parsed = self._parse_per_type_field(field_name)
        if parsed:
            _, attr = parsed
            pref_attr = "status_filter" if attr == "status" else attr
            field = UserMediaPreference._meta.get_field(pref_attr)
            return _value_in_field_choices(new_value, field)
        return _value_in_field_choices(new_value, self._meta.get_field(field_name))

    def update_preference(self, field_name, new_value):
        """Update user preference if the new value is valid and different."""
        parsed = self._parse_per_type_field(field_name)
        if parsed:
            return self._update_per_type_preference(parsed, new_value)

        if new_value is None or not self._is_valid_preference(field_name, new_value):
            return getattr(self, field_name)

        current_value = getattr(self, field_name)
        if new_value != current_value:
            setattr(self, field_name, new_value)
            self.save(update_fields=[field_name])
        return new_value

    def _update_per_type_preference(self, parsed, new_value):
        """Update a per-media-type preference field."""
        media_type, attr = parsed
        pref_attr = "status_filter" if attr == "status" else attr
        pref = self.get_or_create_media_pref(media_type)
        current = getattr(pref, pref_attr)

        if new_value is None or not self._is_valid_preference(
            f"{media_type}_{attr}",
            new_value,
        ):
            return current

        if new_value != current:
            setattr(pref, pref_attr, new_value)
            pref.save(update_fields=[pref_attr])
            if hasattr(self, "_pref_cache"):
                self._pref_cache[media_type] = pref
        return new_value

    def update_home_type_filter(self, raw_param):
        """Parse, validate, save, and return the home type filter list."""
        if raw_param is None:
            return self.home_default_types

        if raw_param == "all":
            new_value = []
        else:
            enabled = set(self.get_enabled_media_types())
            new_value = [t for t in raw_param.split(",") if t in enabled]

        if new_value != self.home_default_types:
            self.home_default_types = new_value
            self.save(update_fields=["home_default_types"])

        return new_value

    def resolve_watch_date(self, now, release_date):
        """
        Resolve the appropriate watch date based on user preference.

        Args:
            now: Pre-calculated current datetime
            release_date: The release/air date for the specific media item

        Returns:
            datetime or None based on user preference
        """
        if self.quick_watch_date == QuickWatchDateChoices.NO_DATE:
            return None

        if self.quick_watch_date == QuickWatchDateChoices.RELEASE_DATE:
            return release_date  # Will be None if not available in metadata

        # CURRENT_DATE is the default
        return now

    def get_enabled_media_types(self):
        """Return a list of enabled media type values based on user preferences."""
        skip = {MediaTypes.EPISODE.value, MediaTypes.SEASON.value}
        if not hasattr(self, "_pref_cache"):
            self._pref_cache = {p.media_type: p for p in self.media_preferences.all()}

        ordered = []
        seen = set()
        for mt in list(self.media_type_order or []) + list(MediaTypes.values):
            if mt in skip or mt in seen:
                continue
            seen.add(mt)
            pref = self._pref_cache.get(mt)
            if pref is None or pref.enabled:
                ordered.append(mt)
        return ordered

    def get_active_media_types(self):
        """Return a list of active media type values based on user preferences."""
        enabled_types = self.get_enabled_media_types()

        # Add season right after TV if TV is enabled
        if (
            MediaTypes.TV.value in enabled_types
            and MediaTypes.SEASON.value not in enabled_types
        ):
            tv_index = enabled_types.index(MediaTypes.TV.value)
            enabled_types.insert(tv_index + 1, MediaTypes.SEASON.value)

        return enabled_types

    def get_import_tasks(self):
        """Return import tasks history and schedules for the user."""
        return {
            "results": self._collect_task_results(),
            "schedules": self._collect_periodic_tasks(),
        }

    def _collect_task_results(self):
        """Build the recent-import history list for this user."""
        task_results = TaskResult.objects.filter(
            task_kwargs__contains=f"'user_id': {self.id},",
            task_name__in=_IMPORT_TASKS.values(),
        ).order_by("-date_done")  # Most recent first

        results = []
        for task in task_results:
            processed_task = helpers.process_task_result(task)
            results.append(
                {
                    "task": processed_task,
                    "source": _TASK_TO_SOURCE[task.task_name],
                    "date": task.date_done,
                    "status": task.status,
                    "summary": processed_task.summary,
                    "errors": processed_task.errors,
                },
            )
        return results

    def _collect_periodic_tasks(self):
        """Build the active import-schedule list for this user."""
        periodic_tasks = PeriodicTask.objects.filter(
            task__in=_IMPORT_TASKS.values(),
            kwargs__contains=f'"user_id": {self.id},',
            enabled=True,
        ).select_related("crontab")

        schedules = []
        for periodic_task in periodic_tasks:
            schedule_info = helpers.get_next_run_info(periodic_task)
            if not schedule_info:
                continue
            username = ""
            if " for " in periodic_task.name:
                username = periodic_task.name.split(" for ")[1].split(" at ")[0]
            schedules.append(
                {
                    "task": periodic_task,
                    "source": _TASK_TO_SOURCE.get(periodic_task.task, "unknown"),
                    "username": username,
                    "last_run": periodic_task.last_run_at,
                    "next_run": schedule_info["next_run"],
                    "schedule": schedule_info["frequency"],
                    "mode": schedule_info["mode"],
                },
            )
        return schedules

    def regenerate_token(self):
        """Regenerate the user's token."""
        self.token = generate_token()
        self.save(update_fields=["token"])
