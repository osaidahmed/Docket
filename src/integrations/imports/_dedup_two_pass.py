from collections import defaultdict

from integrations.imports import helpers


class TwoPassDeduplicator:
    """Track media-id occurrences across rows and surface duplicate warnings."""

    def __init__(self):
        self._counts = defaultdict(int)
        self._titles = defaultdict(list)

    def record(self, media_id, title):
        """Note one occurrence of media_id under title (use during the first pass)."""
        self._counts[media_id] += 1
        self._titles[media_id].append(title)

    def is_unique(self, media_id):
        """Return True if media_id appears only once across recorded rows."""
        return self._counts[media_id] == 1

    def duplicate_warnings(self, message_fn):
        """Yield message_fn(titles, media_id) for each duplicate media_id."""
        for media_id, count in self._counts.items():
            if count > 1:
                title_list = helpers.join_with_commas_and(self._titles[media_id])
                yield message_fn(title_list, media_id)
