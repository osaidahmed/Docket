import json
import logging

from .base import ItemPayloadWebhookProcessor

logger = logging.getLogger(__name__)


class EmbyWebhookProcessor(ItemPayloadWebhookProcessor):
    """Processor for Emby webhook events."""

    def process_payload(self, payload, user):
        """Process the incoming Emby webhook payload."""
        logger.debug(
            "Processing Emby webhook payload: %s",
            json.dumps(payload, indent=2),
        )

        event_type = payload.get("Event")
        if not self._is_supported_event(event_type):
            logger.debug("Ignoring Emby webhook event type: %s", event_type)
            return

        ids = self._extract_external_ids(payload)
        logger.info("Extracted IDs from payload: %s", ids)

        if not any(ids.values()):
            logger.warning("Ignoring Emby webhook call because no ID was found.")
            return

        self._process_media(payload, user, ids)

    def _is_supported_event(self, event_type):
        return event_type in ("playback.start", "playback.stop")

    def _is_played(self, payload):
        return payload.get("PlaybackInfo", {}).get("PlayedToCompletion", False) is True
