import logging

from celery import shared_task
from django.apps import apps

from app.link_providers import registry, templates
from app.link_providers.base import LinkProviderError

logger = logging.getLogger(__name__)


@shared_task(name="Generate Link")
def generate_link(instance_pk, media_type):
    """Auto-populate BasicMedia.link from the user's preferred provider/template.

    Manual edits always win: never overwrite a non-empty link. Falls through
    provider -> template -> noop. Failures in any step are logged and treated
    as a miss so the next fallback runs.
    """
    instance = _load_instance(media_type, instance_pk)
    if instance is None or instance.link:
        return

    prefs = (instance.user.link_preferences or {}).get(media_type) or {}
    url = _resolve_url(instance, prefs)
    if not url:
        return

    instance.link = url
    instance.save(update_fields=["link"])


def _load_instance(media_type, instance_pk):
    try:
        model = apps.get_model("app", media_type)
    except LookupError:
        logger.warning("generate_link: unknown media_type %r", media_type)
        return None
    return model.objects.select_related("item", "user").filter(pk=instance_pk).first()


def _resolve_url(instance, prefs):
    site_id = prefs.get("provider")
    if site_id:
        url = _try_provider(site_id, instance.item)
        if url:
            return url
    return templates.fill_template(prefs.get("template", ""), instance.item)


def _try_provider(site_id, item):
    provider_cls = registry.get_provider(site_id)
    if provider_cls is None:
        logger.warning("generate_link: provider %r not in registry", site_id)
        return ""
    try:
        result = provider_cls().find(item)
    except LinkProviderError:
        logger.exception("generate_link: provider %r raised", site_id)
        return ""
    return result.url if result else ""
