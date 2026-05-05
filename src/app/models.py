import logging

from django.conf import settings
from django.core.validators import (
    DecimalValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models, transaction
from django.db.models import (
    CheckConstraint,
    IntegerField,
    Max,
    Q,
    UniqueConstraint,
)
from django.db.models.functions import Cast
from django.utils import timezone
from model_utils import FieldTracker
from model_utils.fields import MonitorField
from simple_history.models import HistoricalRecords
from simple_history.utils import bulk_create_with_history, bulk_update_with_history

import app
import events
from app import providers
from app._types import MediaTypes
from app.mixins import CalendarTriggerMixin, disable_fetch_releases

logger = logging.getLogger(__name__)


def _aggregate_dates(seasons, field, agg_fn):
    """Collect non-null date values from seasons and aggregate with agg_fn."""
    dates = [getattr(s, field) for s in seasons if getattr(s, field)]
    return agg_fn(dates) if dates else None


class Sources(models.TextChoices):
    """Choices for the source of the item."""

    TMDB = "tmdb", "The Movie Database"
    MAL = "mal", "MyAnimeList"
    MANGAUPDATES = "mangaupdates", "MangaUpdates"
    IGDB = "igdb", "Internet Game Database"
    OPENLIBRARY = "openlibrary", "Open Library"
    HARDCOVER = "hardcover", "Hardcover"
    COMICVINE = "comicvine", "Comic Vine"
    BGG = "bgg", "BoardGameGeek"
    MANUAL = "manual", "Manual"


class Item(CalendarTriggerMixin, models.Model):
    """Model to store basic information about media items."""

    media_id = models.CharField(max_length=20)
    source = models.CharField(
        max_length=20,
        choices=Sources.choices,
    )
    media_type = models.CharField(
        max_length=10,
        choices=MediaTypes.choices,
        default=MediaTypes.MOVIE.value,
    )
    title = models.TextField()
    english_title = models.TextField(blank=True, default="")
    image = models.URLField()  # if add default, custom media entry will show the value
    synopsis = models.TextField(blank=True, default="")
    season_number = models.PositiveIntegerField(null=True, blank=True)
    episode_number = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        """Meta options for the model."""

        constraints = [
            # Ensures items without season/episode numbers are unique
            UniqueConstraint(
                fields=["media_id", "source", "media_type"],
                condition=Q(season_number__isnull=True, episode_number__isnull=True),
                name="unique_item_without_season_episode",
            ),
            # Ensures seasons are unique within a show
            UniqueConstraint(
                fields=["media_id", "source", "media_type", "season_number"],
                condition=Q(season_number__isnull=False, episode_number__isnull=True),
                name="unique_item_with_season",
            ),
            # Ensures episodes are unique within a season
            UniqueConstraint(
                fields=[
                    "media_id",
                    "source",
                    "media_type",
                    "season_number",
                    "episode_number",
                ],
                condition=Q(season_number__isnull=False, episode_number__isnull=False),
                name="unique_item_with_season_episode",
            ),
            # Enforces that season items must have a season number but no episode number
            CheckConstraint(
                condition=Q(
                    media_type=MediaTypes.SEASON.value,
                    season_number__isnull=False,
                    episode_number__isnull=True,
                )
                | ~Q(media_type=MediaTypes.SEASON.value),
                name="season_number_required_for_season",
            ),
            # Enforces that episode items must have both season and episode numbers
            CheckConstraint(
                condition=Q(
                    media_type=MediaTypes.EPISODE.value,
                    season_number__isnull=False,
                    episode_number__isnull=False,
                )
                | ~Q(media_type=MediaTypes.EPISODE.value),
                name="season_and_episode_required_for_episode",
            ),
            # Prevents season/episode numbers from being set on non-TV media types
            CheckConstraint(
                condition=Q(
                    ~Q(
                        media_type__in=[
                            MediaTypes.SEASON.value,
                            MediaTypes.EPISODE.value,
                        ],
                    ),
                    season_number__isnull=True,
                    episode_number__isnull=True,
                )
                | Q(media_type__in=[MediaTypes.SEASON.value, MediaTypes.EPISODE.value]),
                name="no_season_episode_for_other_types",
            ),
            # Validate source choices
            CheckConstraint(
                condition=Q(source__in=Sources.values),
                name="%(app_label)s_%(class)s_source_valid",
            ),
            # Validate media_type choices
            CheckConstraint(
                condition=Q(media_type__in=MediaTypes.values),
                name="%(app_label)s_%(class)s_media_type_valid",
            ),
        ]
        ordering = ["media_id"]

    def __str__(self):
        """Return the name of the item."""
        name = self.title
        if self.season_number is not None:
            name += f" S{self.season_number}"
            if self.episode_number is not None:
                name += f"E{self.episode_number}"
        return name

    @classmethod
    def generate_manual_id(cls, media_type):
        """Generate a new ID for manual items."""
        latest_item = (
            cls.objects.filter(source=Sources.MANUAL.value, media_type=media_type)
            .annotate(
                media_id_int=Cast("media_id", IntegerField()),
            )
            .order_by("-media_id_int")
            .first()
        )

        if latest_item is None:
            return "1"

        return str(int(latest_item.media_id) + 1)

    def fetch_releases(self, delay):
        """Fetch releases for the item."""
        if self._disable_calendar_triggers:
            return

        if self.media_type == MediaTypes.SEASON.value:
            # Get or create the TV item for this season
            try:
                tv_item = Item.objects.get(
                    media_id=self.media_id,
                    source=self.source,
                    media_type=MediaTypes.TV.value,
                )
            except Item.DoesNotExist:
                # Get metadata for the TV show
                tv_metadata = providers.services.get_media_metadata(
                    MediaTypes.TV.value,
                    self.media_id,
                    self.source,
                )
                tv_item = Item.objects.create(
                    media_id=self.media_id,
                    source=self.source,
                    media_type=MediaTypes.TV.value,
                    title=tv_metadata["title"],
                    image=tv_metadata["image"],
                )
                logger.info("Created TV item %s for season %s", tv_item, self)

            # Process the TV item instead of the season
            items_to_process = [tv_item]
        else:
            items_to_process = [self]

        if delay:
            events.tasks.reload_calendar.delay(items_to_process=items_to_process)
        else:
            events.tasks.reload_calendar(items_to_process=items_to_process)


class RelationType(models.TextChoices):
    """Choices for the directional relationship between two items."""

    SEQUEL = "sequel"
    PREQUEL = "prequel"


class ItemRelationship(models.Model):
    """Directional link between two items (e.g. sequel/prequel)."""

    from_item = models.ForeignKey(
        Item, on_delete=models.CASCADE, related_name="relationships_from"
    )
    to_item = models.ForeignKey(
        Item, on_delete=models.CASCADE, related_name="relationships_to"
    )
    relation_type = models.CharField(max_length=20, choices=RelationType.choices)

    class Meta:
        """Database constraints for ItemRelationship."""

        constraints = [
            models.UniqueConstraint(
                fields=["from_item", "to_item", "relation_type"],
                name="unique_item_relationship",
            ),
        ]

    def __str__(self):
        """Return a human-readable description of the relationship."""
        return f"{self.from_item} -> {self.relation_type} -> {self.to_item}"


from app.managers import MediaManager  # noqa: E402  (circular import workaround)


class Status(models.TextChoices):
    """Choices for item status."""

    COMPLETED = "Completed", "Completed"
    IN_PROGRESS = "In progress", "In Progress"
    PLANNING = "Planning", "Planning"
    PAUSED = "Paused", "Paused"
    DROPPED = "Dropped", "Dropped"


class Media(models.Model):
    """Abstract model for all media types."""

    history = HistoricalRecords(
        cascade_delete_history=True,
        inherit=True,
        excluded_fields=[
            "item",
            "progressed_at",
            "user",
            "related_tv",
            "created_at",
            "link",
            "caught_up",
            "is_rewatch",
            "pin_order",
        ],
    )

    created_at = models.DateTimeField(auto_now_add=True)
    item = models.ForeignKey(Item, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    score = models.DecimalField(
        null=True,
        blank=True,
        max_digits=3,
        decimal_places=1,
        validators=[
            DecimalValidator(3, 1),
            MinValueValidator(0),
            MaxValueValidator(10),
        ],
    )
    progress = models.PositiveIntegerField(default=0)
    progressed_at = MonitorField(monitor="progress")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.COMPLETED.value,
    )
    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    link = models.URLField(blank=True, default="")
    caught_up = models.BooleanField(default=False)
    is_rewatch = models.BooleanField(default=False)
    pin_order = models.PositiveIntegerField(null=True, default=None, blank=True)

    class Meta:
        """Meta options for the model."""

        abstract = True
        ordering = ["user", "item", "-created_at"]

    def __str__(self):
        """Return the title of the media."""
        return str(self.item)

    def save(self, *args, **kwargs):
        """Save the media instance."""
        if self.tracker.has_changed("progress"):
            self.process_progress()

        if self.tracker.has_changed("status"):
            self.process_status()

        super().save(*args, **kwargs)

    def process_progress(self):
        """Update fields depending on the progress of the media."""
        if self.progress < 0:
            self.progress = 0
        elif self.status == Status.IN_PROGRESS.value:
            metadata = getattr(self, "_metadata", None)
            if metadata is None:
                metadata = providers.services.get_media_metadata(
                    self.item.media_type,
                    self.item.media_id,
                    self.item.source,
                )
            max_progress = metadata["max_progress"]

            if max_progress:
                self.progress = min(self.progress, max_progress)

                if self.progress == max_progress:
                    self.status = Status.COMPLETED.value

                    now = timezone.now().replace(second=0, microsecond=0)
                    self.end_date = now

    def process_status(self):
        """Update fields depending on the status of the media."""
        if self.status == Status.COMPLETED.value:
            metadata = getattr(self, "_metadata", None)
            if metadata is None:
                metadata = providers.services.get_media_metadata(
                    self.item.media_type,
                    self.item.media_id,
                    self.item.source,
                )
            self.progress = metadata.get("max_progress") or self.progress
        self.item.fetch_releases(delay=True)

    @property
    def formatted_score(self):
        """Return as int if score is 10.0 or 0.0, otherwise show decimal."""
        if self.score is not None:
            max_score = 10
            min_score = 0
            if self.score in (max_score, min_score):
                return int(self.score)
            return self.score
        return None

    @property
    def formatted_progress(self):
        """Return the progress of the media in a formatted string."""
        return str(self.progress)

    @property
    def is_pinned(self):
        """Whether this item has a pin order set."""
        return self.pin_order is not None

    def _revert_to_ongoing(self):
        """Revert a completed title to in-progress when the content is still ongoing."""
        self.status = Status.IN_PROGRESS.value
        self.caught_up = True

    def increase_progress(self):
        """Increase the progress of the media by one."""
        self.progress += 1
        self.save()
        logger.info("Incresed progress of %s to %s", self, self.progress)

    def decrease_progress(self):
        """Decrease the progress of the media by one."""
        self.progress -= 1
        self.save()
        logger.info("Decreased progress of %s to %s", self, self.progress)


class BasicMedia(Media):
    """Model for basic media types."""

    objects = MediaManager()


class TV(Media):
    """Model for TV shows."""

    tracker = FieldTracker()

    class Meta:
        """Meta options for the model."""

        ordering = ["user", "item"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "item"],
                name="%(app_label)s_%(class)s_unique_item_user",
            ),
        ]

    @tracker  # postpone field reset until after the save
    def save(self, *args, **kwargs):
        """Save the media instance."""
        super(Media, self).save(*args, **kwargs)
        if self.tracker.has_changed("status"):
            self._handle_status_change()

    def _handle_status_change(self):
        """Cascade side effects of a TV status transition."""
        if self.status == Status.COMPLETED.value:
            if self._completed():
                self._revert_to_ongoing()
                bulk_update_with_history([self], TV, fields=["status", "caught_up"])
        elif self.status == Status.DROPPED.value:
            self._mark_in_progress_seasons_as_dropped()
        elif self.status == Status.IN_PROGRESS.value:
            self._maybe_start_next_season()
        self.item.fetch_releases(delay=True)

    def _maybe_start_next_season(self):
        """Start the next available season if none is currently in progress."""
        if not self.seasons.filter(status=Status.IN_PROGRESS.value).exists():
            self._start_next_available_season()

    @property
    def manual_media_id(self):
        """Expose underlying item.media_id for manual entry forms."""
        return self.item.media_id

    @property
    def _non_special_seasons(self):
        if not hasattr(self, "_cached_non_special"):
            self._cached_non_special = [
                s for s in self.seasons.all() if s.item.season_number != 0
            ]
        return self._cached_non_special

    @property
    def progress(self):
        """Return the total episodes watched for the TV show."""
        return sum(s.progress for s in self._non_special_seasons)

    @property
    def last_watched(self):
        """Return the latest watched episode in SxxExx format."""
        watched_episodes = [
            {
                "season": s.item.season_number,
                "episode": ep.item.episode_number,
                "end_date": ep.end_date,
            }
            for s in self._non_special_seasons
            if hasattr(s, "episodes")
            for ep in s.episodes.all()
            if ep.end_date is not None
        ]

        if not watched_episodes:
            return ""

        latest_episode = max(
            watched_episodes,
            key=lambda x: (x["end_date"], x["season"], x["episode"]),
        )

        return f"S{latest_episode['season']:02d}E{latest_episode['episode']:02d}"

    @property
    def progressed_at(self):
        """Return the date when the last episode was watched."""
        return _aggregate_dates(self._non_special_seasons, "progressed_at", max)

    @property
    def start_date(self):
        """Return the date of the first episode watched."""
        return _aggregate_dates(self._non_special_seasons, "start_date", min)

    @property
    def end_date(self):
        """Return the date of the last episode watched."""
        return _aggregate_dates(self._non_special_seasons, "end_date", max)

    def _complete_seasons(self, season_numbers, tv_with_seasons_metadata):
        """Complete given seasons and create their episodes."""
        seasons_to_create = []
        seasons_to_update = []

        for sn in season_numbers:
            season_metadata = tv_with_seasons_metadata[f"season/{sn}"]
            item, _ = Item.objects.get_or_create(
                media_id=self.item.media_id,
                source=self.item.source,
                media_type=MediaTypes.SEASON.value,
                season_number=sn,
                defaults={"title": self.item.title, "image": season_metadata["image"]},
            )
            try:
                season_instance = Season.objects.get(item=item, user=self.user)
                if season_instance.status != Status.COMPLETED.value:
                    season_instance.status = Status.COMPLETED.value
                    seasons_to_update.append(season_instance)
            except Season.DoesNotExist:
                seasons_to_create.append(
                    Season(
                        item=item,
                        score=None,
                        status=Status.COMPLETED.value,
                        notes="",
                        related_tv=self,
                        user=self.user,
                    )
                )

        bulk_create_with_history(seasons_to_create, Season)
        bulk_update_with_history(seasons_to_update, Season, ["status"])

        episodes_to_create = []
        for si in seasons_to_create + seasons_to_update:
            sm = tv_with_seasons_metadata[f"season/{si.item.season_number}"]
            episodes_to_create.extend(si.get_remaining_eps(sm))
        bulk_create_with_history(episodes_to_create, Episode)

    def _completed(self):
        """Create remaining seasons and episodes for a TV show.

        Returns True if the show is ongoing (has unaired seasons).
        """
        tv_metadata = providers.services.get_media_metadata(
            self.item.media_type,
            self.item.media_id,
            self.item.source,
        )
        max_progress = tv_metadata["max_progress"]
        next_episode_season = tv_metadata.get("next_episode_season")

        if not max_progress or self.progress > max_progress:
            return next_episode_season is not None

        season_numbers = [
            season["season_number"]
            for season in tv_metadata["related"]["seasons"]
            if season["season_number"] != 0
            and (
                next_episode_season is None
                or season["season_number"] < next_episode_season
            )
        ]
        tv_with_seasons_metadata = providers.services.get_media_metadata(
            "tv_with_seasons",
            self.item.media_id,
            self.item.source,
            season_numbers,
        )
        with transaction.atomic():
            self._complete_seasons(season_numbers, tv_with_seasons_metadata)

        return next_episode_season is not None

    def _mark_in_progress_seasons_as_dropped(self):
        """Mark all in-progress seasons as dropped."""
        in_progress_seasons = list(
            self.seasons.filter(status=Status.IN_PROGRESS.value),
        )

        for season in in_progress_seasons:
            season.status = Status.DROPPED.value

        if in_progress_seasons:
            bulk_update_with_history(
                in_progress_seasons,
                Season,
                fields=["status"],
            )

    def _start_next_available_season(self):
        """Find the next available season to watch and set it to in-progress."""
        all_seasons = self.seasons.filter(
            item__season_number__gt=0,
        ).order_by("item__season_number")

        next_unwatched_season = all_seasons.exclude(
            status__in=[Status.COMPLETED.value],
        ).first()

        if not next_unwatched_season:
            # If all existing seasons are watched, get the next available season
            tv_metadata = providers.services.get_media_metadata(
                self.item.media_type,
                self.item.media_id,
                self.item.source,
            )

            existing_season_numbers = set(
                all_seasons.values_list("item__season_number", flat=True),
            )

            for season_data in tv_metadata["related"]["seasons"]:
                season_number = season_data["season_number"]
                if season_number > 0 and season_number not in existing_season_numbers:
                    item, _ = Item.objects.get_or_create(
                        media_id=self.item.media_id,
                        source=self.item.source,
                        media_type=MediaTypes.SEASON.value,
                        season_number=season_data["season_number"],
                        defaults={
                            "title": self.item.title,
                            "image": season_data["image"],
                        },
                    )

                    next_unwatched_season = Season(
                        item=item,
                        user=self.user,
                        related_tv=self,
                        status=Status.IN_PROGRESS.value,
                    )
                    bulk_create_with_history([next_unwatched_season], Season)
                    break

        elif next_unwatched_season.status != Status.IN_PROGRESS.value:
            next_unwatched_season.status = Status.IN_PROGRESS.value
            bulk_update_with_history(
                [next_unwatched_season],
                Season,
                fields=["status"],
            )


class Season(Media):
    """Model for seasons of TV shows."""

    related_tv = models.ForeignKey(
        TV,
        on_delete=models.CASCADE,
        related_name="seasons",
    )

    tracker = FieldTracker()

    class Meta:
        """Limit the uniqueness of seasons.

        Only one season per media can have the same season number.
        """

        constraints = [
            models.UniqueConstraint(
                fields=["related_tv", "item"],
                name="%(app_label)s_season_unique_tv_item",
            ),
        ]

    def __str__(self):
        """Return the title of the media and season number."""
        return f"{self.item.title} S{self.item.season_number}"

    @property
    def manual_media_id(self):
        """Expose underlying item.media_id for manual entry forms."""
        return self.item.media_id

    @property
    def manual_season_number(self):
        """Expose underlying item.season_number for manual entry forms."""
        return self.item.season_number

    def _on_completed(self):
        """Handle season completion: backfill, create episodes, auto-advance."""
        season_metadata = providers.services.get_media_metadata(
            MediaTypes.SEASON.value,
            self.item.media_id,
            self.item.source,
            [self.item.season_number],
        )

        with transaction.atomic():
            self._backfill_prior_seasons()

            episodes_to_create = self.get_remaining_eps(season_metadata)
            if episodes_to_create:
                bulk_create_with_history(episodes_to_create, Episode)

            if self.related_tv.status not in (
                Status.COMPLETED.value,
                Status.DROPPED.value,
            ):
                self.related_tv._start_next_available_season()

    def _on_in_progress(self):
        """Handle season starting: backfill and update TV status."""
        self._backfill_prior_seasons()

        if self.related_tv.status != Status.IN_PROGRESS.value:
            self.related_tv.status = Status.IN_PROGRESS.value
            bulk_update_with_history([self.related_tv], TV, fields=["status"])

    def _sync_tv_status(self, target_status):
        """Propagate a status to the parent TV if it differs."""
        if self.related_tv.status != target_status:
            self.related_tv.status = target_status
            bulk_update_with_history([self.related_tv], TV, fields=["status"])

    @tracker  # noqa: DJ012  save kept after status helpers it dispatches into
    def save(self, *args, **kwargs):
        """Save the media instance."""
        if self.related_tv_id is None:
            self.related_tv = self.get_tv()

        super(Media, self).save(*args, **kwargs)

        if self.tracker.has_changed("status"):
            if self.status == Status.COMPLETED.value:
                self._on_completed()
            elif self.status == Status.IN_PROGRESS.value:
                self._on_in_progress()
            elif self.status == Status.PLANNING.value:
                self._forward_fill_planning_seasons()
            elif self.status == Status.DROPPED.value:
                self._sync_tv_status(Status.DROPPED.value)

            self.item.fetch_releases(delay=True)

    @property
    def progress(self):
        """Return the current episode number of the season."""
        episodes = self.episodes.all()
        if not episodes:
            return 0

        if self.status == Status.IN_PROGRESS.value:
            # Calculate repeat counts for each episode number
            episode_counts = {}
            for ep in episodes:
                ep_num = ep.item.episode_number
                episode_counts[ep_num] = episode_counts.get(ep_num, 0) + 1

            # Sort by repeat count then episode_number
            sorted_episodes = sorted(
                episodes,
                key=lambda e: (
                    -episode_counts[e.item.episode_number],
                    -e.item.episode_number,
                ),
            )
        else:
            # Default sorting by episode_number
            sorted_episodes = sorted(
                episodes,
                key=lambda e: -e.item.episode_number,
            )

        return sorted_episodes[0].item.episode_number

    @property
    def _episode_dates(self):
        if not hasattr(self, "_cached_episode_dates"):
            self._cached_episode_dates = [
                ep.end_date for ep in self.episodes.all() if ep.end_date is not None
            ]
        return self._cached_episode_dates

    @property
    def progressed_at(self):
        """Return the date when the last episode was watched."""
        return max(self._episode_dates) if self._episode_dates else None

    @property
    def start_date(self):
        """Return the date of the first episode watched."""
        return min(self._episode_dates) if self._episode_dates else None

    @property
    def end_date(self):
        """Return the date of the last episode watched."""
        return max(self._episode_dates) if self._episode_dates else None

    def increase_progress(self):
        """Watch the next episode of the season."""
        tv_with_seasons = providers.services.get_media_metadata(
            "tv_with_seasons",
            self.item.media_id,
            self.item.source,
            [self.item.season_number],
        )
        season_metadata = tv_with_seasons[f"season/{self.item.season_number}"]
        episodes = season_metadata["episodes"]

        if self.progress == 0:
            # start watching from the first episode
            next_episode_number = episodes[0]["episode_number"]
        else:
            next_episode_number = providers.tmdb.find_next_episode(
                self.progress,
                episodes,
            )

        now = timezone.now().replace(second=0, microsecond=0)

        if next_episode_number:
            self.watch(next_episode_number, now, tv_with_seasons)
        else:
            logger.info("No more episodes to watch.")

    def watch(self, episode_number, end_date, tv_metadata=None):
        """Create or add a repeat to an episode of the season."""
        if tv_metadata is None:
            tv_metadata = providers.services.get_media_metadata(
                "tv_with_seasons",
                self.item.media_id,
                self.item.source,
                [self.item.season_number],
            )

        season_key = f"season/{self.item.season_number}"
        season_data = tv_metadata.get(season_key, tv_metadata)
        item = self.get_episode_item(episode_number, season_data)

        episode = Episode(
            related_season=self,
            item=item,
            end_date=end_date,
        )
        episode._tv_metadata = tv_metadata
        episode.save()

        logger.info(
            "%s created successfully.",
            episode,
        )

    def decrease_progress(self):
        """Unwatch the current episode of the season."""
        self.unwatch(self.progress)

    def unwatch(self, episode_number):
        """Unwatch the episode instance."""
        item = self.get_episode_item(episode_number)

        episodes = Episode.objects.filter(
            related_season=self,
            item=item,
        ).order_by("-end_date")

        episode = episodes.first()

        if episode is None:
            logger.warning(
                "Episode %s does not exist.",
                self.item,
            )
            return

        # Get count before deletion for logging
        remaining_count = episodes.count() - 1

        episode.delete()
        logger.info(
            "Deleted %s S%02dE%02d (%d remaining instances)",
            self.item.title,
            self.item.season_number,
            episode_number,
            remaining_count,
        )

    def get_tv(self):
        """Get related TV instance for a season and create it if it doesn't exist."""
        try:
            tv = TV.objects.get(
                item__media_id=self.item.media_id,
                item__media_type=MediaTypes.TV.value,
                item__season_number=None,
                item__source=self.item.source,
                user=self.user,
            )
        except TV.DoesNotExist:
            tv_metadata = providers.services.get_media_metadata(
                MediaTypes.TV.value,
                self.item.media_id,
                self.item.source,
            )

            # creating tv with multiple seasons from a completed season
            if (
                self.status == Status.COMPLETED.value
                and tv_metadata["details"]["seasons"] > 1
            ):
                status = Status.IN_PROGRESS.value
            else:
                status = self.status

            item, _ = Item.objects.get_or_create(
                media_id=self.item.media_id,
                source=Sources.TMDB.value,
                media_type=MediaTypes.TV.value,
                defaults={
                    "title": tv_metadata["title"],
                    "image": tv_metadata["image"],
                },
            )

            tv = TV(
                item=item,
                score=None,
                status=status,
                notes="",
                user=self.user,
            )

            # save_base to avoid custom save method
            TV.save_base(tv)

            logger.info("%s did not exist, it was created successfully.", tv)

        return tv

    def get_remaining_eps(self, season_metadata):
        """Return episodes needed to complete a season."""
        latest_watched_ep_num = Episode.objects.filter(related_season=self).aggregate(
            latest_watched_ep_num=Max("item__episode_number"),
        )["latest_watched_ep_num"]

        if latest_watched_ep_num is None:
            latest_watched_ep_num = 0

        episodes_to_create = []

        # Calculate current time once before the loop
        now = timezone.now().replace(second=0, microsecond=0)

        # Create Episode objects for the remaining episodes
        for episode in reversed(season_metadata["episodes"]):
            if episode["episode_number"] <= latest_watched_ep_num:
                break

            item = self.get_episode_item(episode["episode_number"], season_metadata)

            # Resolve end_date based on user preference
            end_date = self.user.resolve_watch_date(now, episode.get("air_date"))

            episode_db = Episode(
                related_season=self,
                item=item,
                end_date=end_date,
            )
            episodes_to_create.append(episode_db)

        return episodes_to_create

    def get_episode_item(self, episode_number, season_metadata=None):
        """Get the episode item instance, create it if it doesn't exist."""
        if not season_metadata:
            season_metadata = providers.services.get_media_metadata(
                MediaTypes.SEASON.value,
                self.item.media_id,
                self.item.source,
                [self.item.season_number],
            )

        image = settings.IMG_NONE
        for episode in season_metadata["episodes"]:
            if episode["episode_number"] == int(episode_number):
                if episode.get("still_path"):
                    image = (
                        f"https://image.tmdb.org/t/p/original{episode['still_path']}"
                    )
                elif "image" in episode:
                    # for manual seasons
                    image = episode["image"]
                else:
                    image = settings.IMG_NONE
                break

        item, _ = Item.objects.get_or_create(
            media_id=self.item.media_id,
            source=self.item.source,
            media_type=MediaTypes.EPISODE.value,
            season_number=self.item.season_number,
            episode_number=episode_number,
            defaults={
                "title": self.item.title,
                "image": image,
            },
        )

        return item

    def _backfill_prior_seasons(self):
        """Complete all prior seasons when season N is completed or started."""
        season_number = self.item.season_number
        if season_number <= 1:
            return

        tv_metadata = providers.services.get_media_metadata(
            MediaTypes.TV.value,
            self.item.media_id,
            self.item.source,
        )

        prior_season_numbers = [
            s["season_number"]
            for s in tv_metadata["related"]["seasons"]
            if 0 < s["season_number"] < season_number
        ]
        if not prior_season_numbers:
            return

        tv_with_seasons_metadata = providers.services.get_media_metadata(
            "tv_with_seasons",
            self.item.media_id,
            self.item.source,
            prior_season_numbers,
        )

        with disable_fetch_releases():
            self.related_tv._complete_seasons(
                prior_season_numbers,
                tv_with_seasons_metadata,
            )

    def _forward_fill_planning_seasons(self):
        """Create remaining seasons as PLANNING when a season is set to PLANNING."""
        tv_metadata = providers.services.get_media_metadata(
            MediaTypes.TV.value,
            self.item.media_id,
            self.item.source,
        )
        current_season = self.item.season_number

        with transaction.atomic():
            seasons_to_create = []
            for season_data in tv_metadata["related"]["seasons"]:
                instance = self._build_planning_season_if_missing(
                    season_data,
                    current_season,
                )
                if instance is not None:
                    seasons_to_create.append(instance)
            if seasons_to_create:
                bulk_create_with_history(seasons_to_create, Season)

    def _build_planning_season_if_missing(self, season_data, current_season_number):
        """Build a PLANNING Season for a future season number, or None if it exists."""
        sn = season_data["season_number"]
        if sn <= current_season_number or sn == 0:
            return None
        item, _ = Item.objects.get_or_create(
            media_id=self.item.media_id,
            source=self.item.source,
            media_type=MediaTypes.SEASON.value,
            season_number=sn,
            defaults={"title": self.item.title, "image": season_data["image"]},
        )
        if Season.objects.filter(item=item, user=self.user).exists():
            return None
        return Season(
            item=item,
            user=self.user,
            related_tv=self.related_tv,
            status=Status.PLANNING.value,
        )


class Episode(models.Model):
    """Model for episodes of a season."""

    history = HistoricalRecords(
        cascade_delete_history=True,
        excluded_fields=["item", "related_season", "created_at"],
    )

    created_at = models.DateTimeField(auto_now_add=True)
    item = models.ForeignKey(Item, on_delete=models.CASCADE, null=True)
    related_season = models.ForeignKey(
        Season,
        on_delete=models.CASCADE,
        related_name="episodes",
    )
    end_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        """Meta options for the model."""

        ordering = [
            "related_season",
            "item__episode_number",
            "-end_date",
            "-created_at",
        ]

    def __str__(self):
        """Return the season and episode number."""
        return str(self.item)

    def save(self, *args, **kwargs):
        """Save the episode instance."""
        super().save(*args, **kwargs)
        season_number = self.item.season_number
        tv_metadata = self._get_tv_metadata(season_number)
        max_progress = tv_metadata[f"season/{season_number}"]["max_progress"]

        # clear prefetch cache to get the updated episodes
        self.related_season.refresh_from_db()

        season_just_completed = self._cascade_season_status(max_progress)
        self._cascade_tv_status(tv_metadata, season_number, season_just_completed)

    def _get_tv_metadata(self, season_number):
        """Return cached or freshly-fetched tv_with_seasons metadata."""
        cached = getattr(self, "_tv_metadata", None)
        if cached is not None:
            return cached
        return providers.services.get_media_metadata(
            "tv_with_seasons",
            self.item.media_id,
            self.item.source,
            [season_number],
        )

    def _cascade_season_status(self, max_progress):
        """Update season status; return True if the season just completed."""
        if max_progress and self.item.episode_number == max_progress:
            self.related_season.status = Status.COMPLETED.value
            bulk_update_with_history(
                [self.related_season],
                Season,
                fields=["status"],
            )
            return True
        if self.related_season.status != Status.IN_PROGRESS.value:
            self.related_season.status = Status.IN_PROGRESS.value
            bulk_update_with_history(
                [self.related_season],
                Season,
                fields=["status"],
            )
        return False

    def _cascade_tv_status(self, tv_metadata, season_number, season_just_completed):
        """Update TV status based on whether this completion finished the show."""
        tv = self.related_season.related_tv
        if not season_just_completed:
            if tv.status != Status.IN_PROGRESS.value:
                tv.status = Status.IN_PROGRESS.value
                bulk_update_with_history([tv], TV, fields=["status"])
            return
        last_season = tv_metadata["related"]["seasons"][-1]["season_number"]
        next_episode_season = tv_metadata.get("next_episode_season")
        if season_number == last_season and next_episode_season is None:
            tv.status = Status.COMPLETED.value
            bulk_update_with_history([tv], TV, fields=["status"])


class Manga(Media):
    """Model for manga."""

    tracker = FieldTracker()


class Anime(Media):
    """Model for anime."""

    tracker = FieldTracker()

    def process_status(self):
        """Prevent completion of ongoing/upcoming anime."""
        if self.status == Status.COMPLETED.value:
            metadata = getattr(self, "_metadata", None)
            if metadata is None:
                metadata = providers.services.get_media_metadata(
                    self.item.media_type,
                    self.item.media_id,
                    self.item.source,
                )
            is_ongoing = metadata.get("is_ongoing")
            if is_ongoing is None:
                detail_status = metadata.get("details", {}).get("status", "")
                is_ongoing = detail_status in ("Airing", "Upcoming")

            self.progress = metadata.get("max_progress") or self.progress
            if is_ongoing:
                self._revert_to_ongoing()
        self.item.fetch_releases(delay=True)


class Movie(Media):
    """Model for movies."""

    tracker = FieldTracker()


class Game(Media):
    """Model for games."""

    tracker = FieldTracker()

    @property
    def formatted_progress(self):
        """Return progress in hours:minutes format."""
        return app.helpers.minutes_to_hhmm(self.progress)

    def increase_progress(self):
        """Increase the progress of the media by 30 minutes."""
        self.progress += 30
        self.save()
        logger.info("Changed playtime of %s to %s", self, self.formatted_progress)

    def decrease_progress(self):
        """Decrease the progress of the media by 30 minutes."""
        self.progress -= 30
        self.save()
        logger.info("Changed playtime of %s to %s", self, self.formatted_progress)


class Book(Media):
    """Model for books."""

    tracker = FieldTracker()


class Comic(Media):
    """Model for comics."""

    tracker = FieldTracker()


class BoardGame(Media):
    """Model for board games."""

    tracker = FieldTracker()
