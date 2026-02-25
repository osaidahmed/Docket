import logging

from fakeredis import FakeConnection

from .settings import *  # noqa: F403

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,  # noqa: F405
        "TIMEOUT": 18000,  # 5 hours
        "OPTIONS": {
            "CONNECTION_POOL_KWARGS": {"connection_class": FakeConnection},
        },
    },
}

CELERY_TASK_ALWAYS_EAGER = True

TESTING = True

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Steam API key for testing
STEAM_API_KEY = "test_steam_api_key"

# strip apps that are unnecessary for tests
INSTALLED_APPS = [  # noqa: F405
    app
    for app in INSTALLED_APPS  # noqa: F405
    if not app.startswith("health_check")
    and app != "debug_toolbar"
]

MIDDLEWARE = [  # noqa: F405
    m
    for m in MIDDLEWARE  # noqa: F405
    if m != "debug_toolbar.middleware.DebugToolbarMiddleware"
]

logging.disable(logging.CRITICAL)
