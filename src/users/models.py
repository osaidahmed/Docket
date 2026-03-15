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

    home_truncation = models.CharField(
        max_length=2,
        default=HomeTruncationChoices.ALL,
        choices=HomeTruncationChoices.choices,
    )

    # Media type preferences: TV Shows
    tv_enabled = models.BooleanField(default=True)
    tv_layout = models.CharField(
        max_length=20,
        default=LayoutChoices.GRID,
        choices=LayoutChoices.choices,
    )
    tv_sort = models.CharField(
        max_length=20,
        default=MediaSortChoices.SCORE,
        choices=MediaSortChoices.choices,
    )
    tv_status = models.CharField(
        max_length=20,
        default=MediaStatusChoices.ALL,
        choices=MediaStatusChoices.choices,
    )

    # Media type preferences: TV Seasons
    season_enabled = models.BooleanField(default=True)
    season_layout = models.CharField(
        max_length=20,
        default=LayoutChoices.GRID,
        choices=LayoutChoices.choices,
    )
    season_sort = models.CharField(
        max_length=20,
        default=MediaSortChoices.SCORE,
        choices=MediaSortChoices.choices,
    )
    season_status = models.CharField(
        max_length=20,
        default=MediaStatusChoices.ALL,
        choices=MediaStatusChoices.choices,
    )

    # Media type preferences: Movies
    movie_enabled = models.BooleanField(default=True)
    movie_layout = models.CharField(
        max_length=20,
        default=LayoutChoices.GRID,
        choices=LayoutChoices.choices,
    )
    movie_sort = models.CharField(
        max_length=20,
        default=MediaSortChoices.SCORE,
        choices=MediaSortChoices.choices,
    )
    movie_status = models.CharField(
        max_length=20,
        default=MediaStatusChoices.ALL,
        choices=MediaStatusChoices.choices,
    )

    # Media type preferences: Anime
    anime_enabled = models.BooleanField(default=True)
    anime_layout = models.CharField(
        max_length=20,
        default=LayoutChoices.TABLE,
        choices=LayoutChoices.choices,
    )
    anime_sort = models.CharField(
        max_length=20,
        default=MediaSortChoices.SCORE,
        choices=MediaSortChoices.choices,
    )
    anime_status = models.CharField(
        max_length=20,
        default=MediaStatusChoices.ALL,
        choices=MediaStatusChoices.choices,
    )

    # Media type preferences: Manga
    manga_enabled = models.BooleanField(default=True)
    manga_layout = models.CharField(
        max_length=20,
        default=LayoutChoices.TABLE,
        choices=LayoutChoices.choices,
    )
    manga_sort = models.CharField(
        max_length=20,
        default=MediaSortChoices.SCORE,
        choices=MediaSortChoices.choices,
    )
    manga_status = models.CharField(
        max_length=20,
        default=MediaStatusChoices.ALL,
        choices=MediaStatusChoices.choices,
    )

    # Media type preferences: Games
    game_enabled = models.BooleanField(default=True)
    game_layout = models.CharField(
        max_length=20,
        default=LayoutChoices.GRID,
        choices=LayoutChoices.choices,
    )
    game_sort = models.CharField(
        max_length=20,
        default=MediaSortChoices.SCORE,
        choices=MediaSortChoices.choices,
    )
    game_status = models.CharField(
        max_length=20,
        default=MediaStatusChoices.ALL,
        choices=MediaStatusChoices.choices,
    )

    # Media type preferences: Books
    book_enabled = models.BooleanField(default=True)
    book_layout = models.CharField(
        max_length=20,
        default=LayoutChoices.GRID,
        choices=LayoutChoices.choices,
    )
    book_sort = models.CharField(
        max_length=20,
        default=MediaSortChoices.SCORE,
        choices=MediaSortChoices.choices,
    )
    book_status = models.CharField(
        max_length=20,
        default=MediaStatusChoices.ALL,
        choices=MediaStatusChoices.choices,
    )

    # Media type preferences: Comics
    comic_enabled = models.BooleanField(default=True)
    comic_layout = models.CharField(
        max_length=20,
        default=LayoutChoices.GRID,
        choices=LayoutChoices.choices,
    )
    comic_sort = models.CharField(
        max_length=20,
        default=MediaSortChoices.SCORE,
        choices=MediaSortChoices.choices,
    )
    comic_status = models.CharField(
        max_length=20,
        default=MediaStatusChoices.ALL,
        choices=MediaStatusChoices.choices,
    )

    # Media type preferences: Board Games
    boardgame_enabled = models.BooleanField(default=True)
    boardgame_layout = models.CharField(
        max_length=20,
        default=LayoutChoices.GRID,
        choices=LayoutChoices.choices,
    )
    boardgame_sort = models.CharField(
        max_length=20,
        default=MediaSortChoices.SCORE,
        choices=MediaSortChoices.choices,
    )
    boardgame_status = models.CharField(
        max_length=20,
        default=MediaStatusChoices.ALL,
        choices=MediaStatusChoices.choices,
    )

    # Media type ordering
    media_type_order = models.JSONField(default=list, blank=True)

    # Home page default type filter (empty list = all types)
    home_default_types = models.JSONField(default=list, blank=True)

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
                name="home_truncation_valid",
                condition=models.Q(home_truncation__in=HomeTruncationChoices.values),
            ),
            models.CheckConstraint(
                name="tv_layout_valid",
                condition=models.Q(tv_layout__in=LayoutChoices.values),
            ),
            models.CheckConstraint(
                name="season_layout_valid",
                condition=models.Q(season_layout__in=LayoutChoices.values),
            ),
            models.CheckConstraint(
                name="movie_layout_valid",
                condition=models.Q(movie_layout__in=LayoutChoices.values),
            ),
            models.CheckConstraint(
                name="anime_layout_valid",
                condition=models.Q(anime_layout__in=LayoutChoices.values),
            ),
            models.CheckConstraint(
                name="manga_layout_valid",
                condition=models.Q(manga_layout__in=LayoutChoices.values),
            ),
            models.CheckConstraint(
                name="game_layout_valid",
                condition=models.Q(game_layout__in=LayoutChoices.values),
            ),
            models.CheckConstraint(
                name="book_layout_valid",
                condition=models.Q(book_layout__in=LayoutChoices.values),
            ),
            models.CheckConstraint(
                name="tv_sort_valid",
                condition=models.Q(tv_sort__in=MediaSortChoices.values),
            ),
            models.CheckConstraint(
                name="season_sort_valid",
                condition=models.Q(season_sort__in=MediaSortChoices.values),
            ),
            models.CheckConstraint(
                name="movie_sort_valid",
                condition=models.Q(movie_sort__in=MediaSortChoices.values),
            ),
            models.CheckConstraint(
                name="anime_sort_valid",
                condition=models.Q(anime_sort__in=MediaSortChoices.values),
            ),
            models.CheckConstraint(
                name="manga_sort_valid",
                condition=models.Q(manga_sort__in=MediaSortChoices.values),
            ),
            models.CheckConstraint(
                name="game_sort_valid",
                condition=models.Q(game_sort__in=MediaSortChoices.values),
            ),
            models.CheckConstraint(
                name="book_sort_valid",
                condition=models.Q(book_sort__in=MediaSortChoices.values),
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
                name="tv_status_valid",
                condition=models.Q(tv_status__in=MediaStatusChoices.values),
            ),
            models.CheckConstraint(
                name="season_status_valid",
                condition=models.Q(season_status__in=MediaStatusChoices.values),
            ),
            models.CheckConstraint(
                name="movie_status_valid",
                condition=models.Q(movie_status__in=MediaStatusChoices.values),
            ),
            models.CheckConstraint(
                name="anime_status_valid",
                condition=models.Q(anime_status__in=MediaStatusChoices.values),
            ),
            models.CheckConstraint(
                name="manga_status_valid",
                condition=models.Q(manga_status__in=MediaStatusChoices.values),
            ),
            models.CheckConstraint(
                name="game_status_valid",
                condition=models.Q(game_status__in=MediaStatusChoices.values),
            ),
            models.CheckConstraint(
                name="book_status_valid",
                condition=models.Q(book_status__in=MediaStatusChoices.values),
            ),
            models.CheckConstraint(
                name="quick_watch_date_valid",
                condition=models.Q(quick_watch_date__in=QuickWatchDateChoices.values),
            ),
        ]

    def _is_valid_preference(self, field_name, new_value):
        if field_name == "last_search_type":
            return new_value in VALID_SEARCH_TYPES
        field = self._meta.get_field(field_name)
        if not (hasattr(field, "choices") and field.choices):
            return True
        return new_value in {choice[0] for choice in field.choices}

    def update_preference(self, field_name, new_value):
        """Update user preference if the new value is valid and different."""
        if new_value is None or not self._is_valid_preference(field_name, new_value):
            return getattr(self, field_name)

        current_value = getattr(self, field_name)
        if new_value != current_value:
            setattr(self, field_name, new_value)
            self.save(update_fields=[field_name])
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
        ordered = []
        seen = set()
        for mt in list(self.media_type_order or []) + list(MediaTypes.values):
            if mt in skip or mt in seen:
                continue
            seen.add(mt)
            if getattr(self, f"{mt}_enabled", False):
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
        import_tasks = {
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

        # Reverse mapping to get source from task name
        task_to_source = {v: k for k, v in import_tasks.items()}

        task_result_filter_text = f"'user_id': {self.id},"

        # Get all task results for this user
        task_results = TaskResult.objects.filter(
            task_kwargs__contains=task_result_filter_text,
            task_name__in=import_tasks.values(),
        ).order_by(
            "-date_done",
        )  # Most recent first

        # Build results list
        results = []
        for task in task_results:
            source = task_to_source[task.task_name]
            processed_task = helpers.process_task_result(task)
            results.append(
                {
                    "task": processed_task,
                    "source": source,
                    "date": task.date_done,
                    "status": task.status,
                    "summary": processed_task.summary,
                    "errors": processed_task.errors,
                },
            )

        # Get periodic tasks with their crontab schedules
        periodic_tasks_filter_text = f'"user_id": {self.id},'
        periodic_tasks = PeriodicTask.objects.filter(
            task__in=import_tasks.values(),
            kwargs__contains=periodic_tasks_filter_text,
            enabled=True,
        ).select_related("crontab")

        # Build schedules list
        schedules = []
        for periodic_task in periodic_tasks:
            source = task_to_source.get(periodic_task.task, "unknown")

            # Extract username from task name if available
            username = ""
            if " for " in periodic_task.name:
                username = periodic_task.name.split(" for ")[1].split(" at ")[0]

            schedule_info = helpers.get_next_run_info(periodic_task)
            if schedule_info:
                schedules.append(
                    {
                        "task": periodic_task,
                        "source": source,
                        "username": username,
                        "last_run": periodic_task.last_run_at,
                        "next_run": schedule_info["next_run"],
                        "schedule": schedule_info["frequency"],
                        "mode": schedule_info["mode"],
                    },
                )

        return {
            "results": results,
            "schedules": schedules,
        }

    def regenerate_token(self):
        """Regenerate the user's token."""
        self.token = generate_token()
        self.save(update_fields=["token"])
