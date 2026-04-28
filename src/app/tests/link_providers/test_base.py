from django.test import SimpleTestCase

from app.link_providers.base import LinkProvider, LinkResult


class LinkProviderBaseTests(SimpleTestCase):
    def test_find_raises_not_implemented(self):
        provider = LinkProvider()
        with self.assertRaises(NotImplementedError):
            provider.find({"any": "item"})

    def test_link_result_dataclass(self):
        result = LinkResult(url="https://example.com/x", site_id="example")
        self.assertEqual(result.url, "https://example.com/x")
        self.assertEqual(result.site_id, "example")
