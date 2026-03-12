from django.test import SimpleTestCase, override_settings
from django.urls import URLResolver


class AdminURLTests(SimpleTestCase):
    """Test admin URL configuration."""

    @override_settings(ADMIN_ENABLED=True)
    def test_admin_url_included_when_enabled(self):
        """Test that admin URL is present when ADMIN_ENABLED=True."""
        import importlib

        import config.urls

        importlib.reload(config.urls)
        admin_found = any(
            getattr(pattern, "app_name", None) == "admin"
            or (
                isinstance(pattern, URLResolver)
                and getattr(pattern, "namespace", None) == "admin"
            )
            for pattern in config.urls.urlpatterns
        )
        self.assertTrue(admin_found)

        # Reload with original settings to avoid side effects
        importlib.reload(config.urls)

    @override_settings(ADMIN_ENABLED=False)
    def test_admin_url_excluded_when_disabled(self):
        """Test that admin URL is absent when ADMIN_ENABLED=False."""
        import importlib

        import config.urls

        importlib.reload(config.urls)
        admin_found = any(
            getattr(pattern, "app_name", None) == "admin"
            or (
                isinstance(pattern, URLResolver)
                and getattr(pattern, "namespace", None) == "admin"
            )
            for pattern in config.urls.urlpatterns
        )
        self.assertFalse(admin_found)

        # Reload with original settings to avoid side effects
        importlib.reload(config.urls)
