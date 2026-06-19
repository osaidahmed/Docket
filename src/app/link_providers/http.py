import logging

import requests

from app.link_providers.base import LinkProviderError
from app.providers import services

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15


def get_session():
    """Return the rate-limited session shared with app.providers.services."""
    return services.session


def _request(method, url, **kwargs):
    try:
        response = get_session().request(method, url, **kwargs)
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        logger.warning("link_providers %s failed: %s (%s)", method, url, error)
        raise LinkProviderError(str(error)) from error
    return response


def http_get(url, headers=None, timeout=DEFAULT_TIMEOUT):
    """GET via the shared session; raise LinkProviderError on any network failure."""
    return _request("GET", url, headers=headers, timeout=timeout)


def http_post(url, json_body, headers=None, timeout=DEFAULT_TIMEOUT):
    """POST JSON via the shared session; raise LinkProviderError on failure."""
    return _request("POST", url, json=json_body, headers=headers, timeout=timeout)
