from dataclasses import dataclass


@dataclass(frozen=True)
class LinkResult:
    """Successful lookup from a link provider."""

    url: str
    site_id: str


class LinkProvider:
    """Base class for site-specific link providers."""

    site_id: str
    label: str
    media_types: tuple
    requires_flaresolverr: bool = False

    def find(self, item):
        """Return a LinkResult for the item, or None if no match was found."""
        del item
        raise NotImplementedError


class LinkProviderError(Exception):
    """Raised when a provider fails to reach or parse its remote source."""
