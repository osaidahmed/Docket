from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LinkResult:
    """Successful lookup from a link provider."""

    url: str
    site_id: str


class LinkProvider(ABC):
    """Base class for site-specific link providers."""

    site_id: str
    label: str
    media_types: tuple
    requires_flaresolverr: bool = False

    @abstractmethod
    def find(self, item):
        """Return a LinkResult for the item, or None if no match was found."""


class LinkProviderError(Exception):
    """Raised when a provider fails to reach or parse its remote source."""
