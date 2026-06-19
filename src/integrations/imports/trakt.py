import logging
from collections import defaultdict

import requests
from django.conf import settings
from django.utils.dateparse import parse_datetime

import app
from app._types import is_season_media
from app.models import MediaTypes, Sources, Status
from app.providers import services
from integrations.imports import _trakt_helpers, helpers
from integrations.imports.helpers import MediaImportUnexpectedError
from integrations.imports.trakt_auth import (
    get_access_token,
    handle_oauth_callback,  # noqa: F401 - re-exported for views
)

logger = logging.getLogger(__name__)

TRAKT_API_BASE_URL = "https://api.trakt.tv"
BULK_PAGE_SIZE = 1000


def importer(token, user, mode, username):
    """Import the user's data from Trakt.

    Can import using either OAuth (token provided) or public username.
    When using OAuth, username should be the authenticated user's username.
    When using public import, username is the Trakt username and token should be None.

    Args:
        token (str, optional): Encrypted OAuth2 refresh token if using OAuth else None
        user: Django user object to import data for
        mode (str): Import mode ("new" or "overwrite")
        username (str): Trakt username to import from
    """
    trakt_importer = TraktImporter(username, user, mode, refresh_token=token)
    return trakt_importer.import_data()


class TraktImporter(helpers.BaseImporter):
    """Class to handle importing user data from Trakt."""

    def __init__(self, username, user, mode, refresh_token=None):
        """Initialize the importer with user details and mode.

        Args:
            username (str): Trakt username to import from
            user: Django user object to import data for
            mode (str): Import mode ("new" or "overwrite")
            refresh_token (str, optional): Encrypted OAuth2 refresh token if
                using OAuth, None for public import
        """
        self.username = username
        self.user = user
        self.mode = mode
        self.refresh_token = refresh_token
        self.user_base_url = f"{TRAKT_API_BASE_URL}/users/{username}"
        self.warnings = []

        # Track existing media to handle "new" mode correctly
        self.existing_media = helpers.get_existing_media(user)

        # Track media IDs to delete in overwrite mode
        self.to_delete = defaultdict(lambda: defaultdict(set))

        # Track bulk creation lists for each media type
        self.bulk_media = defaultdict(list)

        # Track media instances being created
        self.media_instances = defaultdict(lambda: defaultdict(list))

        logger.info(
            "Initialized Trakt importer for user %s with mode %s",
            username,
            mode,
        )

    def import_data(self):
        """Import all user data from Trakt."""
        self.process_history()
        self.process_watchlist()
        self.process_ratings()
        self.process_comments()

        return self.finalize()

    def _make_api_request(self, url):
        """Make a request to the Trakt API with proper headers."""
        headers = {
            "Content-Type": "application/json",
            "trakt-api-version": "2",
            "trakt-api-key": settings.TRAKT_API,
        }
        if self.refresh_token:
            try:
                # already made api_request before, so access_token is set
                headers["Authorization"] = f"Bearer {self.access_token}"
            except AttributeError:
                self.access_token = get_access_token(self.refresh_token)
                headers["Authorization"] = f"Bearer {self.access_token}"
        return services.api_request(
            "TRAKT",
            "GET",
            url,
            headers=headers,
        )

    def _handle_api_error(self, error):
        """Translate common HTTP errors into user-facing messages."""
        _trakt_helpers.translate_api_error(error, self.username)

    def _get_paginated_data(self, endpoint, item_type="items"):
        """Get paginated data from Trakt API."""
        page = 1
        all_data = []

        while True:
            url = f"{endpoint}?page={page}&limit={BULK_PAGE_SIZE}"

            try:
                page_data = self._make_api_request(url)
            except requests.exceptions.HTTPError as error:
                self._handle_api_error(error)

            if not page_data:
                break

            all_data.extend(page_data)
            page += 1
            logger.info(
                "Retrieved page %s of %s for user %s (%s items)",
                page - 1,
                item_type,
                self.username,
                len(page_data),
            )

        logger.info(
            "Retrieved %s total %s for user %s",
            len(all_data),
            item_type,
            self.username,
        )
        return all_data

    def process_history(self):
        """Process watch history from Trakt."""
        logger.info("Importing watch history for user %s", self.username)
        history_endpoint = f"{self.user_base_url}/history"
        full_history = self._get_paginated_data(history_endpoint, "history entries")

        # Process in chronological order (oldest first)
        for entry in reversed(full_history):
            watched_at = entry["watched_at"]
            try:
                if entry["type"] == "movie":
                    logger.info(
                        "Processing movie %s watched at %s",
                        entry["movie"]["title"],
                        watched_at,
                    )
                    self.process_watched_movie(entry)
                elif entry["type"] == "episode":
                    logger.info(
                        "Processing episode %s S%sE%s watched at %s",
                        entry["show"]["title"],
                        entry["episode"]["season"],
                        entry["episode"]["number"],
                        watched_at,
                    )
                    self.process_watched_episode(entry)
            except Exception as e:
                msg = f"Error processing history entry: {entry}"
                raise MediaImportUnexpectedError(msg) from e

    def _get_tmdb_id(self, entry_data):
        """Extract TMDB ID from entry data."""
        return _trakt_helpers.get_tmdb_id_or_warn(entry_data, self.warnings)

    def _get_metadata(self, media_type, tmdb_id, title, season_number=None):
        """Get metadata for a media item."""
        try:
            kwargs = {}
            if season_number is not None:
                kwargs["season_numbers"] = [season_number]

            return services.get_media_metadata(
                media_type,
                tmdb_id,
                Sources.TMDB.value,
                **kwargs,
            )
        except services.ProviderAPIError as error:
            if error.status_code == requests.codes.not_found:
                if is_season_media(media_type):
                    title = f"{title} S{season_number}"
                self.warnings.append(
                    f"{title}: not found in {Sources.TMDB.label} with ID {tmdb_id}.",
                )
                return None
            raise

    def _get_or_create_item(
        self,
        media_type,
        tmdb_id,
        metadata,
        season_number=None,
        episode_number=None,
    ):
        """Get or create an item in the database."""
        item_kwargs = {
            "media_id": tmdb_id,
            "source": Sources.TMDB.value,
            "media_type": media_type,
        }

        if season_number is not None:
            item_kwargs["season_number"] = season_number

        if episode_number is not None:
            item_kwargs["episode_number"] = episode_number

        defaults = {
            "title": metadata["title"],
            "image": metadata["image"],
        }

        item, _ = app.models.Item.objects.get_or_create(
            **item_kwargs,
            defaults=defaults,
        )

        return item

    def process_watched_movie(self, entry):
        """Process a single movie watch event."""
        movie = entry["movie"]
        tmdb_id = self._get_tmdb_id(movie)
        if not tmdb_id:
            return

        # Check if we should process this movie based on mode
        if not helpers.should_process_media(
            self.existing_media,
            self.to_delete,
            MediaTypes.MOVIE.value,
            Sources.TMDB.value,
            tmdb_id,
            self.mode,
        ):
            return

        metadata = self._get_metadata(MediaTypes.MOVIE.value, tmdb_id, movie["title"])
        if not metadata:
            return

        item = self._get_or_create_item(MediaTypes.MOVIE.value, tmdb_id, metadata)
        watched_at = entry["watched_at"]

        key = f"{tmdb_id}"

        movie_obj = app.models.Movie(
            item=item,
            user=self.user,
            end_date=watched_at,
            status=Status.COMPLETED.value,
            progress=1,
        )
        movie_obj._history_date = parse_datetime(watched_at)

        self.media_instances[MediaTypes.MOVIE.value][key].append(movie_obj)
        self.bulk_media[MediaTypes.MOVIE.value].append(movie_obj)

    def _get_episode_image(self, episode_number, season_metadata):
        """Extract episode image URL from season metadata."""
        return _trakt_helpers.get_episode_image(episode_number, season_metadata)

    def process_watched_episode(self, entry):
        """Process a single episode watch event."""
        show = entry["show"]
        tv_result = self._validate_and_fetch_metadata(show, MediaTypes.TV.value)
        if not tv_result:
            return
        tmdb_id, tv_metadata = tv_result

        season_number = entry["episode"]["season"]
        episode_number = entry["episode"]["number"]
        season_metadata = self._get_metadata(
            MediaTypes.SEASON.value,
            tmdb_id,
            show["title"],
            season_number,
        )
        if not season_metadata:
            return
        if not self._validate_episode(
            show["title"],
            tmdb_id,
            season_number,
            episode_number,
            season_metadata,
        ):
            return

        watched_at = entry["watched_at"]
        tv_obj = self._ensure_tv_obj(tmdb_id, tv_metadata, watched_at)
        season_obj = self._ensure_season_obj(
            tmdb_id,
            season_number,
            season_metadata,
            tv_obj,
            watched_at,
        )
        self._create_episode(
            tmdb_id,
            season_number,
            episode_number,
            tv_metadata,
            season_metadata,
            season_obj,
            watched_at,
        )
        self._update_completion_status(
            season_obj,
            tv_obj,
            season_number,
            episode_number,
            season_metadata,
            tv_metadata,
        )

    def _validate_and_fetch_metadata(self, media_data, media_type, season_number=None):
        """Validate tmdb_id, check should_process, and fetch metadata.

        For SEASON media_type, the should_process check uses TV as the parent type.
        Returns (tmdb_id, metadata) tuple or None to skip.
        """
        tmdb_id = self._get_tmdb_id(media_data)
        if not tmdb_id:
            return None
        parent_type = MediaTypes.TV.value if is_season_media(media_type) else media_type
        if not helpers.should_process_media(
            self.existing_media,
            self.to_delete,
            parent_type,
            Sources.TMDB.value,
            tmdb_id,
            self.mode,
        ):
            return None
        metadata = self._get_metadata(
            media_type,
            tmdb_id,
            media_data["title"],
            season_number,
        )
        if not metadata:
            return None
        return tmdb_id, metadata

    def _validate_episode(
        self,
        title,
        tmdb_id,
        season_number,
        episode_number,
        season_metadata,
    ):
        """Validate that an episode exists in TMDB metadata."""
        if _trakt_helpers.episode_exists_in_metadata(episode_number, season_metadata):
            return True
        self.warnings.append(
            f"{title} S{season_number}E{episode_number}: "
            f"not found in {Sources.TMDB.label} with ID {tmdb_id}.",
        )
        return False

    def _ensure_tv_obj(self, tmdb_id, tv_metadata, watched_at):
        """Get existing or create new TV object for episode tracking."""
        tv_key = str(tmdb_id)
        if tv_key in self.media_instances[MediaTypes.TV.value]:
            return self.media_instances[MediaTypes.TV.value][tv_key][0]

        tv_item = self._get_or_create_item(
            MediaTypes.TV.value,
            tmdb_id,
            tv_metadata,
        )
        tv_obj = app.models.TV(
            item=tv_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        tv_obj._history_date = parse_datetime(watched_at)
        self.bulk_media[MediaTypes.TV.value].append(tv_obj)
        self.media_instances[MediaTypes.TV.value][tv_key] = [tv_obj]
        return tv_obj

    def _ensure_season_obj(
        self,
        tmdb_id,
        season_number,
        season_metadata,
        tv_obj,
        watched_at,
    ):
        """Get existing or create new Season object for episode tracking."""
        season_key = f"{tmdb_id}:{season_number}"
        if season_key in self.media_instances[MediaTypes.SEASON.value]:
            return self.media_instances[MediaTypes.SEASON.value][season_key][0]

        season_item = self._get_or_create_item(
            MediaTypes.SEASON.value,
            tmdb_id,
            season_metadata,
            season_number,
        )
        season_obj = app.models.Season(
            item=season_item,
            user=self.user,
            related_tv=tv_obj,
            status=Status.IN_PROGRESS.value,
        )
        season_obj._history_date = parse_datetime(watched_at)
        self.bulk_media[MediaTypes.SEASON.value].append(season_obj)
        self.media_instances[MediaTypes.SEASON.value][season_key] = [season_obj]
        return season_obj

    def _create_episode(
        self,
        tmdb_id,
        season_number,
        episode_number,
        tv_metadata,
        season_metadata,
        season_obj,
        watched_at,
    ):
        """Create an Episode item and object."""
        episode_image = self._get_episode_image(episode_number, season_metadata)
        episode_item = self._get_or_create_item(
            MediaTypes.EPISODE.value,
            tmdb_id,
            {"title": tv_metadata["title"], "image": episode_image},
            season_number,
            episode_number,
        )
        ep_key = f"{tmdb_id}:{season_number}:{episode_number}"
        episode_obj = app.models.Episode(
            item=episode_item,
            related_season=season_obj,
            end_date=watched_at,
        )
        episode_obj._history_date = parse_datetime(watched_at)
        self.media_instances[MediaTypes.EPISODE.value][ep_key].append(episode_obj)
        self.bulk_media[MediaTypes.EPISODE.value].append(episode_obj)

    def _update_completion_status(
        self,
        season_obj,
        tv_obj,
        season_number,
        episode_number,
        season_metadata,
        tv_metadata,
    ):
        """Update completion status for season and TV show if applicable."""
        if episode_number != season_metadata["max_progress"]:
            return
        season_obj.status = Status.COMPLETED.value
        last_season = tv_metadata.get("last_episode_season")
        if last_season and last_season == season_number:
            tv_obj.status = Status.COMPLETED.value

    def _fetch_and_process(
        self, endpoint, entry_type, attr_fn, *, paginated=False, pagination_key=None
    ):
        """Fetch data from a Trakt endpoint and process entries."""
        logger.info("Importing %s for user %s", entry_type, self.username)
        url = f"{self.user_base_url}/{endpoint}"
        data = (
            self._get_paginated_data(url, pagination_key)
            if paginated
            else self._make_api_request(url)
        )
        self._process_entries(data, entry_type, attr_fn)

    def process_watchlist(self):
        """Process watchlist from Trakt."""
        self._fetch_and_process(
            "watchlist", "watchlist", lambda _e: {"status": Status.PLANNING.value}
        )

    def process_ratings(self):
        """Process ratings from Trakt."""
        self._fetch_and_process("ratings", "rating", lambda e: {"score": e["rating"]})

    def process_comments(self):
        """Process comments from Trakt."""
        self._fetch_and_process(
            "comments",
            "comment",
            lambda e: {"notes": e["comment"]["comment"]},
            paginated=True,
            pagination_key="comments",
        )

    def _process_entries(self, entries, entry_type, get_attrs):
        """Process a list of entries with shared error handling."""
        for entry in entries:
            try:
                self._process_generic_entry(entry, entry_type, get_attrs(entry))
            except Exception as e:
                msg = f"Error processing {entry_type} entry: {entry}"
                raise MediaImportUnexpectedError(msg) from e

    def _process_generic_entry(self, entry, entry_type, attribute_updates):
        """Process a generic entry (watchlist, rating, or comment)."""
        if entry["type"] == "movie":
            logger.info(
                "Processing movie %s for %s",
                entry["movie"]["title"],
                entry_type,
            )
            # Movies with Completed status (from ratings and comments)
            # should have progress=1
            status = attribute_updates.get("status", Status.COMPLETED.value)
            if status == Status.COMPLETED.value:
                attribute_updates["progress"] = 1

            self._process_media_item(
                entry,
                entry["movie"],
                MediaTypes.MOVIE.value,
                app.models.Movie,
                attribute_updates,
            )
        elif entry["type"] == "show":
            logger.info(
                "Processing show %s for %s",
                entry["show"]["title"],
                entry_type,
            )
            self._process_media_item(
                entry,
                entry["show"],
                MediaTypes.TV.value,
                app.models.TV,
                attribute_updates,
            )
        elif entry["type"] == "season":
            logger.info(
                "Processing season %s S%s for %s",
                entry["show"]["title"],
                entry["season"]["number"],
                entry_type,
            )
            self._process_media_item(
                entry,
                entry["show"],
                MediaTypes.SEASON.value,
                app.models.Season,
                attribute_updates,
                entry["season"]["number"],
            )

    def _process_media_item(
        self,
        entry,
        media_data,
        media_type,
        model_class,
        defaults,
        season_number=None,
    ):
        """Process media items for watchlist, ratings, and comments."""
        result = self._validate_and_fetch_metadata(
            media_data,
            media_type,
            season_number,
        )
        if not result:
            return
        tmdb_id, metadata = result

        updated_at = self._get_entry_timestamp(entry)

        if is_season_media(media_type):
            tv_obj = self._get_tv_obj(tmdb_id, media_data, updated_at)
            if not tv_obj:
                return
            defaults["related_tv"] = tv_obj

        key = f"{tmdb_id}:{season_number}" if season_number else str(tmdb_id)
        item = self._get_or_create_item(media_type, tmdb_id, metadata, season_number)

        if key in self.media_instances[media_type]:
            self._update_instance(media_type, key, defaults)
        else:
            media_obj = model_class(item=item, user=self.user, **defaults)
            media_obj._history_date = updated_at
            self.bulk_media[media_type].append(media_obj)
            self.media_instances[media_type][key] = [media_obj]

    @staticmethod
    def _get_entry_timestamp(entry):
        """Extract the timestamp from a Trakt entry."""
        return parse_datetime(
            entry.get("listed_at")
            or entry.get("rated_at")
            or entry["comment"].get("updated_at"),
        )

    def _get_tv_obj(self, tmdb_id, media_data, updated_at):
        """Get or create a TV object for the given season."""
        tv_metadata = self._get_metadata(
            MediaTypes.TV.value,
            tmdb_id,
            media_data["title"],
        )
        if not tv_metadata:
            return None

        tv_item = self._get_or_create_item(
            MediaTypes.TV.value,
            tmdb_id,
            tv_metadata,
        )

        tv_key = f"{tmdb_id}"

        # Create or get the TV object
        if tv_key in self.media_instances[MediaTypes.TV.value]:
            tv_obj = self.media_instances[MediaTypes.TV.value][tv_key][0]
        else:
            tv_obj = app.models.TV(
                item=tv_item,
                user=self.user,
                status=Status.IN_PROGRESS.value,
            )
            tv_obj._history_date = updated_at
            self.bulk_media[MediaTypes.TV.value].append(tv_obj)
            self.media_instances[MediaTypes.TV.value][tv_key] = [tv_obj]
        return tv_obj

    def _update_instance(self, media_type, key, defaults):
        """Update the instance with new attributes."""
        for media_obj in self.media_instances[media_type][key]:
            for attr, value in defaults.items():
                setattr(media_obj, attr, value)
