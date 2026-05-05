from django.test import SimpleTestCase

from app.link_providers.base import LinkProvider, LinkResult


class LinkProviderBaseTests(SimpleTestCase):
    def test_find_is_abstract(self):
        self.assertIn("find", LinkProvider.__abstractmethods__)

    def test_link_result_dataclass(self):
        result = LinkResult(url="https://example.com/x", site_id="example")
        self.assertEqual(result.url, "https://example.com/x")
        self.assertEqual(result.site_id, "example")
