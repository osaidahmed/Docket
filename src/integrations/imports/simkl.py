import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass

import requests
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

import app
from app._types import is_anime_media, is_movie_media, is_tv_media
from app.models import MediaTypes, Sources, Status
from app.providers import services
from integrations.imports import _simkl_helpers, helpers
from integrations.imports.helpers import MediaImportError, MediaImportUnexpectedError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ListConfig:
    """Per-media-type configuration for processing a Simkl list."""

    entry_inner_key: str
    id_key: str
    id_label: str
    media_type: str
    source: str
    log_label: str
    instance_class: type
    process_children: Callable | None = None


def get_token(request):
    """View for getting the SIMKL OAuth2 token."""
    code = request.GET["code"]
    url = "https://api.simkl.com/oauth/token"

    headers = {
        "Content-Type": "application/json",
    }

    params = {
        "client_id": settings.SIMKL_ID,
        "client_secret": settings.SIMKL_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": request.build_absolute_uri(reverse("import_simkl_private")),
    }

    try:
        token_response = app.providers.services.api_request(
            "SIMKL",
            "POST",
            url,
            headers=headers,
            params=params,
        )
    except services.ProviderAPIError as error:
        if error.status_code == requests.codes.unauthorized:
            msg = "Invalid SIMKL secret key."
            raise MediaImportError(msg) from error
        raise

    return {
        "access_token": token_response["access_token"],
        "username": get_username(token_response["access_token"]),
    }


def get_username(token):
    """Get the username from SIMKL using the provided token."""
    try:
        user_info = app.providers.services.api_request(
            "SIMKL",
            "POST",
            "https://api.simkl.com/users/settings",
            headers={
                "Authorization": f"Bearer {token}",
                "simkl-api-key": settings.SIMKL_ID,
                "Content-Type": "application/json",
            },
        )
    except services.ProviderAPIError as error:
        if error.status_code == requests.codes.unauthorized:
            msg = "Invalid SIMKL secret key."
            raise MediaImportError(msg) from error
        raise

    return user_info["user"]["name"]


def importer(token, user, mode):
    """Import tv shows, movies and anime from SIMKL."""
    simkl_importer = SimklImporter(token, user, mode)
    return simkl_importer.import_data()


class SimklImporter:
    """Class to handle importing user data from Simkl."""

    SIMKL_API_BASE_URL = "https://api.simkl.com"

    def __init__(self, token, user, mode):
        """Initialize the importer with token, user, and mode.

        Args:
            token (str): Simkl OAuth token
            user: Django user object to import data for
            mode (str): Import mode ("new" or "overwrite")
        """
        self.token = helpers.decrypt(token)
        self.user = user
        self.mode = mode
        self.warnings = []

        # Track existing media for "new" mode
        self.existing_media = helpers.get_existing_media(user)

        # Track media IDs to delete in overwrite mode
        self.to_delete = defaultdict(lambda: defaultdict(set))

        # Track bulk creation lists for each media type
        self.bulk_media = defaultdict(list)

        logger.info(
            "Initialized Simkl importer for user %s with mode %s",
            user.username,
            mode,
        )

    def import_data(self):
        """Import all user data from Simkl."""
        data = self._get_user_list()

        if not data:
            return {}, ""

        self._process_media_lists(data)

        helpers.cleanup_existing_media(self.to_delete, self.user)
        helpers.bulk_create_media(self.bulk_media, self.user)

        imported_counts = {
            media_type: len(media_list)
            for media_type, media_list in self.bulk_media.items()
        }

        deduplicated_messages = "\n".join(dict.fromkeys(self.warnings))
        return imported_counts, deduplicated_messages

    def _get_user_list(self):
        """Get the user's list from Simkl."""
        url = f"{self.SIMKL_API_BASE_URL}/sync/all-items/"
        headers = {
            "Authorization": f"Bearer: {self.token}",
            "simkl-api-key": settings.SIMKL_ID,
        }
        params = {
            "extended": "full",
            "episode_watched_at": "yes",
            "memos": "yes",
        }

        return app.providers.services.api_request(
            "SIMKL",
            "GET",
            url,
            headers=headers,
            params=params,
        )

    def _process_media_lists(self, data):
        """Dispatch each Simkl list to the generic processor with the right config."""
        list_specs = (
            (
                "shows",
                _ListConfig(
                    entry_inner_key="show",
                    id_key="tmdb",
                    id_label="TMDB",
                    media_type=MediaTypes.TV.value,
                    source=Sources.TMDB.value,
                    log_label="tv shows",
                    instance_class=app.models.TV,
                    process_children=self._process_seasons_and_episodes,
                ),
            ),
            (
                "movies",
                _ListConfig(
                    entry_inner_key="movie",
                    id_key="tmdb",
                    id_label="TMDB",
                    media_type=MediaTypes.MOVIE.value,
                    source=Sources.TMDB.value,
                    log_label="movies",
                    instance_class=app.models.Movie,
                ),
            ),
            (
                "anime",
                _ListConfig(
                    entry_inner_key="show",
                    id_key="mal",
                    id_label="MyAnimeList",
                    media_type=MediaTypes.ANIME.value,
                    source=Sources.MAL.value,
                    log_label="anime",
                    instance_class=app.models.Anime,
                ),
            ),
        )
        for data_key, config in list_specs:
            if data_key in data:
                self._process_generic_list(data[data_key], config)

    def _extract_entry_id(self, entry_data, id_key, label):
        """Extract media ID from entry, returning None with warning if missing."""
        try:
            return entry_data["ids"][id_key]
        except KeyError:
            self.warnings.append(f"{entry_data['title']}: No {label} ID found")
            return None

    def _check_dedup_and_mode(self, media_id, existing_ids, title, media_type, source):
        """Check for duplicates and mode filtering. Returns False to skip."""
        if media_id in existing_ids:
            self.warnings.append(
                f"{title} ({media_id}) already present in the import list",
            )
            return False
        return helpers.should_process_media(
            self.existing_media,
            self.to_delete,
            media_type,
            source,
            str(media_id),
            self.mode,
        )

    def _fetch_metadata_safe(self, fetch_fn, title, source, media_id):
        """Fetch metadata with not-found handling. Returns None on 404."""
        try:
            return fetch_fn()
        except services.ProviderAPIError as error:
            if error.status_code == requests.codes.not_found:
                self.warnings.append(
                    f"{title}: not found in {source.label} with ID {media_id}.",
                )
                return None
            raise

    @staticmethod
    def _get_memo(entry):
        """Extract memo text from entry."""
        return entry["memo"]["text"] if entry["memo"] != {} else ""

    def _process_generic_list(self, entries, config):
        """Process a Simkl list using a per-media-type config object."""
        logger.info("Processing %s", config.log_label)
        existing_ids = set()
        for entry in entries:
            try:
                self._process_simkl_entry(entry, config, existing_ids)
            except Exception as error:
                msg = f"Error processing entry: {entry}"
                raise MediaImportUnexpectedError(msg) from error
        logger.info("Processed %d %s", len(entries), config.log_label)

    def _process_simkl_entry(self, entry, config, existing_ids):
        """Persist a single Simkl entry; mutates existing_ids and self.bulk_media."""
        entry_data = entry[config.entry_inner_key]
        title = entry_data["title"]
        media_id = self._extract_entry_id(entry_data, config.id_key, config.id_label)
        if not media_id:
            return
        if not self._check_dedup_and_mode(
            media_id,
            existing_ids,
            title,
            config.media_type,
            config.source,
        ):
            return
        metadata = self._fetch_simkl_metadata(config.media_type, entry, media_id, title)
        if not metadata:
            return
        item, _ = app.models.Item.objects.get_or_create(
            media_id=media_id,
            source=config.source,
            media_type=config.media_type,
            defaults={"title": metadata["title"], "image": metadata["image"]},
        )
        status = self._get_status(entry["status"])
        instance = config.instance_class(
            item=item,
            user=self.user,
            status=status,
            score=entry["user_rating"],
            notes=self._get_memo(entry),
            **self._build_extra_kwargs(config.media_type, entry, status),
        )
        instance._history_date = self._get_history_date(entry)
        self.bulk_media[config.media_type].append(instance)
        existing_ids.add(media_id)
        if config.process_children:
            config.process_children(entry, instance, metadata)

    def _fetch_simkl_metadata(self, media_type, entry, media_id, title):
        """Fetch provider metadata for a Simkl entry by media type."""
        if is_tv_media(media_type):
            season_numbers = [s["number"] for s in entry.get("seasons", [])]
            return self._fetch_metadata_safe(
                lambda: app.providers.tmdb.tv_with_seasons(media_id, season_numbers),
                title,
                Sources.TMDB,
                media_id,
            )
        if is_movie_media(media_type):
            return self._fetch_metadata_safe(
                lambda: app.providers.tmdb.movie(media_id),
                title,
                Sources.TMDB,
                media_id,
            )
        return self._fetch_metadata_safe(
            lambda: app.providers.mal.anime(media_id),
            title,
            Sources.MAL,
            media_id,
        )

    def _build_extra_kwargs(self, media_type, entry, status):
        """Build media-type-specific instance kwargs for the model constructor."""
        if is_movie_media(media_type):
            last_watched = self._get_date(entry.get("last_watched_at"))
            return {
                "progress": 1 if status == Status.COMPLETED.value else 0,
                "start_date": last_watched,
                "end_date": last_watched,
            }
        if is_anime_media(media_type):
            return {
                "progress": entry["watched_episodes_count"],
                "start_date": self._get_start_date(entry),
                "end_date": self._get_end_date(status, entry.get("last_watched_at")),
            }
        return {}

    def _process_seasons_and_episodes(self, tv, tv_instance, metadata):
        """Process seasons and episodes for a TV show."""
        tmdb_id = tv["show"]["ids"]["tmdb"]

        for season in tv.get("seasons", []):
            season_number = season["number"]
            episodes = season["episodes"]
            season_metadata = metadata[f"season/{season_number}"]

            season_item, _ = app.models.Item.objects.get_or_create(
                media_id=tmdb_id,
                source=Sources.TMDB.value,
                media_type=MediaTypes.SEASON.value,
                season_number=season_number,
                defaults={
                    "title": metadata["title"],
                    "image": season_metadata["image"],
                },
            )

            if episodes[-1]["number"] == season_metadata["max_progress"]:
                season_status = Status.COMPLETED.value
            else:
                season_status = tv_instance.status

            season_instance = app.models.Season(
                item=season_item,
                user=self.user,
                related_tv=tv_instance,
                status=season_status,
            )
            season_instance._history_date = self._get_history_date(tv)
            self.bulk_media[MediaTypes.SEASON.value].append(season_instance)

            # Process episodes
            for episode in episodes:
                ep_img = self._get_episode_image(episode, season_number, metadata)
                episode_item, _ = app.models.Item.objects.get_or_create(
                    media_id=tmdb_id,
                    source=Sources.TMDB.value,
                    media_type=MediaTypes.EPISODE.value,
                    season_number=season_number,
                    episode_number=episode["number"],
                    defaults={
                        "title": metadata["title"],
                        "image": ep_img,
                    },
                )

                episode_instance = app.models.Episode(
                    item=episode_item,
                    related_season=season_instance,
                    end_date=self._get_date(episode.get("watched_at")),
                )
                episode_instance._history_date = (
                    self._get_date(
                        episode.get("watched_at"),
                    )
                    or timezone.now()
                )
                self.bulk_media[MediaTypes.EPISODE.value].append(episode_instance)

    def _get_episode_image(self, episode, season_number, metadata):
        """Get the image for the episode."""
        return _simkl_helpers.get_episode_image(episode, season_number, metadata)

    def _get_status(self, status):
        """Map Simkl status to internal status."""
        return _simkl_helpers.map_status(status)

    def _get_date(self, date_str):
        """Convert the date from Simkl to a date object."""
        return _simkl_helpers.parse_date(date_str)

    def _get_start_date(self, anime):
        """Get the start date based on earliest watched episode."""
        return _simkl_helpers.get_start_date(anime)

    def _get_end_date(self, anime_status, last_watched_at):
        """Get the end date based on the anime status."""
        return _simkl_helpers.get_end_date(anime_status, last_watched_at)

    def _get_history_date(self, entry):
        """Get the history date from the entry."""
        return _simkl_helpers.get_history_date(entry)
