from collections.abc import Callable
from dataclasses import dataclass, field

import requests
from django.core.cache import cache as _cache

from app.providers import services


@dataclass
class ProviderClient:
    """Per-provider wrapper around services.api_request and the cache."""

    provider: str
    base_url: str
    base_params: dict = field(default_factory=dict)
    base_headers: dict = field(default_factory=dict)
    error_handler: Callable | None = None

    def request(self, method, path, params=None, headers=None, **kwargs):
        merged_params = {**self.base_params, **(params or {})}
        merged_headers = {**self.base_headers, **(headers or {})}
        url = f"{self.base_url}{path}" if path.startswith("/") else path
        try:
            return services.api_request(
                self.provider,
                method,
                url,
                params=merged_params,
                headers=merged_headers,
                **kwargs,
            )
        except requests.exceptions.HTTPError as error:
            if self.error_handler:
                self.error_handler(error)
            raise

    def cached(self, cache_key, ttl, compute_fn):
        data = _cache.get(cache_key)
        if data is not None:
            return data
        data = compute_fn()
        _cache.set(cache_key, data, timeout=ttl)
        return data
