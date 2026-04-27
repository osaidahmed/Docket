from app.link_providers.providers.allmanga import AllMangaProvider
from app.link_providers.providers.anikai import AnikaiProvider
from app.link_providers.providers.fastflix import FastFlixProvider

PROVIDERS = {
    AllMangaProvider.site_id: AllMangaProvider,
    AnikaiProvider.site_id: AnikaiProvider,
    FastFlixProvider.site_id: FastFlixProvider,
}


def get_provider(site_id):
    """Return the provider class registered under ``site_id``, or None."""
    return PROVIDERS.get(site_id)


def get_providers_for(media_type):
    """Return all provider classes that handle the given media_type."""
    return [cls for cls in PROVIDERS.values() if media_type in cls.media_types]
