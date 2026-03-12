import logging
from collections import defaultdict
from datetime import UTC

import requests
from django.apps import apps
from django.conf import settings
from django.urls import reverse
from django.utils import timezone

import app
from app.models import MediaTypes, Sources, Status
from app.providers import services
from integrations.imports import helpers
from integrations.imports.helpers import MediaImportError, MediaImportUnexpectedError

logger = logging.getLogger(__name__)

_ANILIST_IMPORT_QUERY = """
query ($userName: String){
    anime: MediaListCollection(userName: $userName, type: ANIME) {
        lists {
            isCustomList
            entries {
                media{
                    title {
                        userPreferred
                        english
                    }
                    coverImage {
                        large
                    }
                    idMal
                    chapters
                    episodes
                }
                status
                score(format: POINT_10_DECIMAL)
                progress
                startedAt {
                    year
                    month
                    day
                }
                completedAt {
                    year
                    month
                    day
                }
                updatedAt
                repeat
                notes
            }
        }
    }
    manga: MediaListCollection(userName: $userName, type: MANGA) {
        lists {
            isCustomList
            entries {
                media{
                    title {
                        userPreferred
                        english
                    }
                    coverImage {
                        large
                    }
                    idMal
                }
                status
                score(format: POINT_10_DECIMAL)
                progress
                startedAt {
                    year
                    month
                    day
                }
                completedAt {
                    year
                    month
                    day
                }
                updatedAt
                repeat
                notes
            }
        }
    }
}
"""


def get_token(request):
    """View for getting the AniList OAuth2 token."""
    code = request.GET["code"]

    url = "https://anilist.co/api/v2/oauth/token"

    params = {
        "client_id": settings.ANILIST_ID,
        "client_secret": settings.ANILIST_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": request.build_absolute_uri(reverse("import_anilist_private")),
    }

    try:
        token_response = app.providers.services.api_request(
            "ANILIST",
            "POST",
            url,
            params=params,
        )
    except services.ProviderAPIError as error:
        if error.status_code == requests.codes.unauthorized:
            msg = "Invalid AniList secret key."
            raise MediaImportError(msg) from error
        raise

    return {
        "access_token": token_response["access_token"],
        "username": get_username_from_oauth(token_response["access_token"]),
    }


def get_username_from_oauth(access_token):
    """Get AniList username from access token."""
    query = """
    query {
        Viewer {
            name
        }
    }
    """

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    try:
        response = app.providers.services.api_request(
            "ANILIST",
            "POST",
            "https://graphql.anilist.co",
            headers=headers,
            params={"query": query},
        )
    except services.ProviderAPIError as error:
        if error.status_code == requests.codes.unauthorized:
            msg = "Invalid AniList access token."
            raise MediaImportError(msg) from error
        raise

    return response["data"]["Viewer"]["name"]


def importer(token, user, mode, username):
    """Import anime and manga ratings from Anilist."""
    anilist_importer = AniListImporter(token, user, mode, username)
    return anilist_importer.import_data()


class AniListImporter:
    """Class to handle importing user data from AniList."""

    def __init__(self, token, user, mode, username):
        """Initialize the importer with username, user, and mode.

        Args:
            username (str): AniList username to import from
            token (str): Encrypted access token for private imports (optional)
            user: Django user object to import data for
            mode (str): Import mode ("new" or "overwrite")
        """
        self.username = username
        self.token = token
        self.user = user
        self.mode = mode
        self.warnings = []

        if self.token is not None:
            self.token = helpers.decrypt(self.token)

        # Track existing media for "new" mode
        self.existing_media = helpers.get_existing_media(user)

        # Track media IDs to delete in overwrite mode
        self.to_delete = defaultdict(lambda: defaultdict(set))

        # Track bulk creation lists for each media type
        self.bulk_media = defaultdict(list)

        logger.info(
            "Initialized AniList importer for user %s with mode %s",
            username,
            mode,
        )

    def import_data(self):
        """Import all user data from AniList."""
        response = self._fetch_user_lists()

        self._process_media_data(response["data"]["anime"], MediaTypes.ANIME.value)
        self._process_media_data(response["data"]["manga"], MediaTypes.MANGA.value)

        helpers.cleanup_existing_media(self.to_delete, self.user)
        helpers.bulk_create_media(self.bulk_media, self.user)

        imported_counts = {
            media_type: len(media_list)
            for media_type, media_list in self.bulk_media.items()
        }

        deduplicated_messages = "\n".join(dict.fromkeys(self.warnings))
        return imported_counts, deduplicated_messages

    def _fetch_user_lists(self):
        """Fetch anime and manga lists from AniList API."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        logger.info("Fetching anime and manga from AniList account")

        try:
            return app.providers.services.api_request(
                "ANILIST",
                "POST",
                "https://graphql.anilist.co",
                params={
                    "query": _ANILIST_IMPORT_QUERY,
                    "variables": {"userName": self.username},
                },
                headers=headers,
            )
        except requests.exceptions.HTTPError as error:
            self._handle_http_error(error)

    def _handle_http_error(self, error):
        """Map AniList HTTP errors to user-friendly messages."""
        error_message = error.response.json()["errors"][0].get("message")
        if error_message == "User not found":
            msg = f"User {self.username} not found."
            raise MediaImportError(msg) from error
        if error_message == "Private User":
            msg = f"User {self.username} is private."
            raise MediaImportError(msg) from error
        raise error

    def _process_media_data(self, media_data, media_type):
        """Process media data for a specific type (anime/manga)."""
        logger.info("Processing %s from AniList", media_type)

        entries = [
            content
            for status_list in media_data["lists"]
            if not status_list["isCustomList"]
            for content in status_list["entries"]
        ]

        for content in entries:
            try:
                self._process_entry(content, media_type)
            except Exception as e:
                msg = f"Error processing history entry: {content}"
                raise MediaImportUnexpectedError(msg) from e

    def _process_entry(self, content, media_type):
        """Process a single entry from AniList."""
        if content["media"]["idMal"] is None:
            title = content["media"]["title"]["userPreferred"]
            self.warnings.append(f"{title}: No matching MAL ID.")
            return

        if not helpers.should_process_media(
            self.existing_media,
            self.to_delete,
            media_type,
            Sources.MAL.value,
            str(content["media"]["idMal"]),
            self.mode,
        ):
            return

        item = self._get_or_create_item(content, media_type)
        status = self._get_status(content["status"])
        self._create_media_instances(content, media_type, item, status)

    def _get_or_create_item(self, content, media_type):
        """Create or get an Item from AniList entry data."""
        en_title = content["media"]["title"].get("english") or ""
        if en_title == content["media"]["title"]["userPreferred"]:
            en_title = ""

        item, _ = app.models.Item.objects.get_or_create(
            media_id=str(content["media"]["idMal"]),
            source=Sources.MAL.value,
            media_type=media_type,
            defaults={
                "title": content["media"]["title"]["userPreferred"],
                "english_title": en_title,
                "image": content["media"]["coverImage"]["large"],
            },
        )
        return item

    @staticmethod
    def _get_status(status):
        """Convert AniList status to internal status."""
        if status in ("CURRENT", "REPEATING"):
            return Status.IN_PROGRESS.value
        return status.capitalize()

    def _create_media_instances(self, content, media_type, item, status):
        """Create media instances for repeats and current status."""
        model = apps.get_model(app_label="app", model_name=media_type)
        updated_at = self._get_updated_at(content["updatedAt"])
        repeats_count = self._get_repeats_count(content)
        max_progress = (
            content["media"].get("episodes") or content["media"].get("chapters") or 0
        )

        for _ in range(repeats_count):
            instance = model(
                item=item,
                user=self.user,
                score=content["score"],
                progress=max_progress,
                status=Status.COMPLETED.value,
                start_date=self._get_date(content["startedAt"]),
                end_date=None,
                notes=content["notes"] or "",
                is_rewatch=True,
            )
            instance._history_date = updated_at
            self.bulk_media[media_type].append(instance)

        instance = model(
            item=item,
            user=self.user,
            score=content["score"],
            progress=content["progress"] or 0,
            status=status,
            start_date=self._get_date(content["startedAt"]),
            end_date=self._get_date(content["completedAt"]),
            notes=content["notes"] or "",
        )
        instance._history_date = updated_at
        self.bulk_media[media_type].append(instance)

    @staticmethod
    def _get_updated_at(updated_at_value):
        """Parse the updatedAt timestamp."""
        if updated_at_value == 0:
            return timezone.now()
        return timezone.datetime.fromtimestamp(updated_at_value, tz=UTC)

    @staticmethod
    def _get_repeats_count(content):
        """Get the number of repeats, adjusting for REPEATING status."""
        repeats = content["repeat"]
        if content["status"] == "REPEATING" and repeats == 0:
            return 1
        return repeats

    def _get_date(self, date_dict):
        """Return date object from date dict."""
        if not date_dict["year"]:
            return None

        month = date_dict["month"] or 1
        day = date_dict["day"] or 1

        return timezone.datetime(
            year=date_dict["year"],
            month=month,
            day=day,
            hour=0,
            minute=0,
            second=0,
            tzinfo=timezone.get_current_timezone(),
        )
