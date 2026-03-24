from django.test import TestCase

from users.templatetags.user_tags import get_attr, source_display


class GetAttrTests(TestCase):
    def test_existing_attribute(self):
        obj = type("Obj", (), {"name": "test"})()
        self.assertEqual(get_attr(obj, "name"), "test")

    def test_missing_attribute_returns_none(self):
        obj = type("Obj", (), {})()
        self.assertIsNone(get_attr(obj, "nonexistent"))


class SourceDisplayTests(TestCase):
    def test_known_source_renders_html(self):
        result = source_display("trakt")
        self.assertIn("Trakt", result)
        self.assertIn("img", result)

    def test_unknown_source_returns_empty(self):
        self.assertEqual(source_display("nonexistent_source"), "")
