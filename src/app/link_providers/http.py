import logging
from dataclasses import dataclass

import requests
from django.conf import settings

from app.link_providers.base import LinkProviderError
from app.providers import services

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15
FLARESOLVERR_TIMEOUT = 60
FLARESOLVERR_SESSION = "yamtrack"
FLARESOLVERR_MAX_TIMEOUT_MS = 30000


@dataclass(frozen=True)
class ScrapedResponse:
    """Result of a flaresolverr-mediated fetch."""

    html: str
    status_code: int
    final_url: str


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


def flaresolverr_get(url):
    """Fetch a URL through flaresolverr, solving Cloudflare challenges as needed.

    Returns a ScrapedResponse. Raises LinkProviderError on transport or
    flaresolverr-side failures (e.g. 5xx, timeout, malformed JSON).

    Bypasses services.session deliberately: when flaresolverr is unreachable
    (typical in local dev without the sidecar) the shared session's 3-retry
    adapter would otherwise spam urllib3 warnings on every task, with no
    chance of recovery within a single backfill batch.
    """
    payload = {
        "cmd": "request.get",
        "url": url,
        "maxTimeout": FLARESOLVERR_MAX_TIMEOUT_MS,
        "session": FLARESOLVERR_SESSION,
    }
    try:
        response = requests.post(
            settings.FLARESOLVERR_URL,
            json=payload,
            timeout=(5, FLARESOLVERR_TIMEOUT),
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as error:
        logger.warning(
            "flaresolverr fetch failed: %s (%s)", url, type(error).__name__,
        )
        msg = str(error)
        raise LinkProviderError(msg) from error
    return _parse_flaresolverr(response)


def _parse_flaresolverr(response):
    try:
        data = response.json()
    except ValueError as error:
        msg = "flaresolverr returned non-JSON"
        raise LinkProviderError(msg) from error
    if data.get("status") != "ok":
        detail = data.get("message", "unknown")
        msg = f"flaresolverr error: {detail}"
        raise LinkProviderError(msg)
    solution = data.get("solution") or {}
    return ScrapedResponse(
        html=solution.get("response", "") or "",
        status_code=int(solution.get("status") or 0),
        final_url=solution.get("url", "") or "",
    )
