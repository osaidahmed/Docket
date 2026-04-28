from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase

from app.link_providers import registry, tasks
from app.link_providers.base import LinkProvider, LinkProviderError, LinkResult
from app.models import Item, Manga, MediaTypes, Sources, Status


class RegistryTests(SimpleTestCase):
    def test_get_provider_unknown_returns_none(self):
        self.assertIsNone(registry.get_provider("does-not-exist"))

    def test_get_providers_for_filters_by_media_type(self):
        providers = registry.get_providers_for(MediaTypes.ANIME.value)
        self.assertTrue(all(MediaTypes.ANIME.value in p.media_types for p in providers))


class _StubProvider(LinkProvider):
    site_id = "stub"
    media_types = ("manga",)
    next_result = None
    raise_exception = False
    calls = 0

    def find(self, item):
        type(self).calls += 1
        if type(self).raise_exception:
            msg = "boom"
            raise LinkProviderError(msg)
        return type(self).next_result


def _reset_stub():
    _StubProvider.next_result = None
    _StubProvider.raise_exception = False
    _StubProvider.calls = 0


class GenerateLinkTaskTests(TestCase):
    """Tests for the generate_link Celery task orchestration."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(username="t", password="x")
        cls.item = Item.objects.create(
            media_id="m1",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Test Manga",
            english_title="Test Manga EN",
            image="https://x.test/i.jpg",
        )

    def setUp(self):
        _reset_stub()
        self.instance = Manga.objects.create(
            item=self.item,
            user=self.user,
            status=Status.PLANNING.value,
        )

    def _set_prefs(self, **prefs):
        self.user.link_preferences = {MediaTypes.MANGA.value: prefs}
        self.user.save(update_fields=["link_preferences"])

    @patch("app.link_providers.tasks.registry.get_provider")
    def test_provider_hit_writes_link(self, mock_get_provider):
        _StubProvider.next_result = LinkResult(url="https://x.test/abc", site_id="stub")
        mock_get_provider.return_value = _StubProvider
        self._set_prefs(provider="stub")

        tasks.generate_link(self.instance.pk, MediaTypes.MANGA.value)

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.link, "https://x.test/abc")

    @patch("app.link_providers.tasks.registry.get_provider")
    def test_provider_miss_falls_back_to_template(self, mock_get_provider):
        _StubProvider.next_result = None
        mock_get_provider.return_value = _StubProvider
        self._set_prefs(provider="stub", template="https://fb.test/?q={title}")

        tasks.generate_link(self.instance.pk, MediaTypes.MANGA.value)

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.link, "https://fb.test/?q=Test%20Manga")

    @patch("app.link_providers.tasks.registry.get_provider")
    def test_provider_exception_falls_back_to_template(self, mock_get_provider):
        _StubProvider.raise_exception = True
        mock_get_provider.return_value = _StubProvider
        self._set_prefs(provider="stub", template="https://fb.test/{title}")

        tasks.generate_link(self.instance.pk, MediaTypes.MANGA.value)

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.link, "https://fb.test/Test%20Manga")

    def test_manual_override_is_never_overwritten(self):
        Manga.objects.filter(pk=self.instance.pk).update(link="https://manual.test/")
        self._set_prefs(provider="stub", template="https://fb.test/{title}")

        tasks.generate_link(self.instance.pk, MediaTypes.MANGA.value)

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.link, "https://manual.test/")
        self.assertEqual(_StubProvider.calls, 0)

    def test_no_preferences_is_noop(self):
        tasks.generate_link(self.instance.pk, MediaTypes.MANGA.value)
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.link, "")

    @patch("app.link_providers.tasks.registry.get_provider", return_value=None)
    def test_unknown_provider_falls_back_to_template(self, _mock):
        self._set_prefs(provider="ghost", template="https://fb.test/{title}")

        tasks.generate_link(self.instance.pk, MediaTypes.MANGA.value)

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.link, "https://fb.test/Test%20Manga")

    def test_template_only_writes_link(self):
        self._set_prefs(template="https://only.test/?q={english_title}")

        tasks.generate_link(self.instance.pk, MediaTypes.MANGA.value)

        self.instance.refresh_from_db()
        self.assertEqual(self.instance.link, "https://only.test/?q=Test%20Manga%20EN")

    def test_unknown_media_type_is_noop(self):
        tasks.generate_link(self.instance.pk, "not_a_real_type")
        self.instance.refresh_from_db()
        self.assertEqual(self.instance.link, "")

    def test_missing_instance_is_noop(self):
        tasks.generate_link(99999999, MediaTypes.MANGA.value)
