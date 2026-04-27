from datetime import date
from types import SimpleNamespace

from django.test import SimpleTestCase

from app.link_providers.templates import fill_template


def _item(**kwargs):
    defaults = {"title": "", "english_title": "", "release_date": None}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class FillTemplateTests(SimpleTestCase):
    """Unit tests for fill_template URL substitution."""

    def test_substitutes_title(self):
        url = fill_template("https://x.test/?q={title}", _item(title="Frieren"))
        self.assertEqual(url, "https://x.test/?q=Frieren")

    def test_substitutes_english_title(self):
        item = _item(title="Shingeki no Kyojin", english_title="Attack on Titan")
        url = fill_template("https://x.test/{english_title}", item)
        self.assertEqual(url, "https://x.test/Attack%20on%20Titan")

    def test_url_encodes_special_chars(self):
        url = fill_template("https://x.test/?q={title}", _item(title="A & B"))
        self.assertEqual(url, "https://x.test/?q=A%20%26%20B")

    def test_extracts_year_from_release_date(self):
        item = _item(title="Inception", release_date=date(2010, 7, 16))
        url = fill_template("https://x.test/{title}-{year}", item)
        self.assertEqual(url, "https://x.test/Inception-2010")

    def test_missing_year_substitutes_empty(self):
        url = fill_template("https://x.test/{title}-{year}", _item(title="X"))
        self.assertEqual(url, "https://x.test/X-")

    def test_empty_template_returns_empty_string(self):
        self.assertEqual(fill_template("", _item(title="X")), "")
        self.assertEqual(fill_template(None, _item(title="X")), "")

    def test_missing_attributes_substitute_empty(self):
        url = fill_template("https://x.test/{english_title}", _item(title="X"))
        self.assertEqual(url, "https://x.test/")
