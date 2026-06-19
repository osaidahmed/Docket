import json
import logging

from .base import ItemPayloadWebhookProcessor

logger = logging.getLogger(__name__)


class JellyfinWebhookProcessor(ItemPayloadWebhookProcessor):
    """Processor for Jellyfin webhook events."""

    def process_payload(self, payload, user):
        """Process the incoming Jellyfin webhook payload."""
        logger.debug(
            "Processing Jellyfin webhook payload: %s",
            json.dumps(payload, indent=2),
        )

        event_type = payload.get("Event")
        if not self._is_supported_event(event_type):
            logger.debug("Ignoring Jellyfin webhook event type: %s", event_type)
            return

        ids = self._extract_external_ids(payload)
        logger.info("Extracted IDs from payload: %s", ids)

        if not any(ids.values()):
            logger.warning("Ignoring Jellyfin webhook call because no ID was found.")
            return

        self._process_media(payload, user, ids)

    def _is_supported_event(self, event_type):
        return event_type in ("Play", "Stop")

    def _is_played(self, payload):
        return payload["Item"]["UserData"]["Played"]
