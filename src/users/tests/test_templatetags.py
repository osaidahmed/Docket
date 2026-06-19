from django.test import TestCase

from users.templatetags.user_tags import source_display


class SourceDisplayTests(TestCase):
    def test_known_source_renders_html(self):
        result = source_display("trakt")
        self.assertIn("Trakt", result)
        self.assertIn("img", result)

    def test_unknown_source_returns_empty(self):
        self.assertEqual(source_display("nonexistent_source"), "")
