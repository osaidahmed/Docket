import datetime
import json
from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase

from app.services.export import (
    format_csv,
    format_json,
    format_markdown,
    format_txt,
    serialize_media_list,
)


class FormatCsvTests(TestCase):
    """Test CSV formatter."""

    def test_basic(self):
        rows = [
            {"title": "Movie A", "score": "8.5", "status": "Completed"},
            {"title": "Movie B", "score": "", "status": "In Progress"},
        ]
        result = format_csv(rows)
        lines = result.strip().split("\n")
        self.assertEqual(len(lines), 3)
        self.assertIn("title", lines[0])
        self.assertIn("Movie A", lines[1])

    def test_empty_returns_empty_string(self):
        self.assertEqual(format_csv([]), "")

    def test_quotes_all_fields(self):
        rows = [{"title": "Movie A", "score": "8"}]
        result = format_csv(rows)
        self.assertIn('"Movie A"', result)
        self.assertIn('"8"', result)


class FormatJsonTests(TestCase):
    """Test JSON formatter."""

    def test_basic(self):
        rows = [{"title": "Movie A"}, {"title": "Movie B"}]
        result = format_json(rows)
        data = json.loads(result)
        self.assertEqual(len(data), 2)

    def test_empty(self):
        result = format_json([])
        data = json.loads(result)
        self.assertEqual(data, [])

    def test_non_ascii(self):
        rows = [{"title": "進撃の巨人"}]
        result = format_json(rows)
        self.assertIn("進撃の巨人", result)


class FormatMarkdownTests(TestCase):
    """Test Markdown formatter."""

    def test_basic(self):
        rows = [
            {"title": "Movie A", "score": "8"},
            {"title": "Movie B", "score": "9"},
        ]
        result = format_markdown(rows)
        lines = result.strip().split("\n")
        self.assertEqual(len(lines), 4)
        self.assertIn("| title", lines[0])
        self.assertIn("| ---", lines[1])

    def test_empty(self):
        self.assertEqual(format_markdown([]), "")

    def test_escapes_pipe(self):
        rows = [{"title": "Movie | With Pipe", "status": "Done"}]
        result = format_markdown(rows)
        self.assertIn("Movie \\| With Pipe", result)

    def test_newlines_in_cell(self):
        rows = [{"title": "Movie", "notes": "Line 1\nLine 2"}]
        result = format_markdown(rows)
        self.assertNotIn("\n\n", result.split("\n", 2)[-1])


class FormatTxtTests(TestCase):
    """Test TXT formatter."""

    def test_basic(self):
        rows = [
            {"title": "Movie A", "score": "8.5", "status": "Completed"},
            {"title": "Movie B", "score": "", "status": "In Progress"},
        ]
        result = format_txt(rows, "{title} - {score}")
        self.assertIn("Movie A - 8.5", result)
        self.assertIn("Movie B - ", result)

    def test_custom_separator(self):
        rows = [{"title": "A"}, {"title": "B"}]
        result = format_txt(rows, "{title}", separator=", ")
        self.assertEqual(result, "A, B")

    def test_unknown_placeholder_becomes_empty(self):
        rows = [{"title": "Movie A"}]
        result = format_txt(rows, "{title} {nonexistent}")
        self.assertEqual(result, "Movie A ")

    def test_empty_rows(self):
        result = format_txt([], "{title}")
        self.assertEqual(result, "")


class SerializeMediaListTests(TestCase):
    """Tests for serialize_media_list field-level contract."""

    def _make_media(
        self,
        *,
        title="A",
        english_title="B",
        score=Decimal("8.5"),
        formatted_score="8.5",
        progress=10,
        max_progress=12,
        formatted_progress="10",
        status="Completed",
        start_date=datetime.date(2026, 1, 1),
        end_date=datetime.date(2026, 2, 1),
        notes="hi",
        link="http://x",
        is_rewatch=True,
        caught_up=False,
        source="tmdb",
    ):
        media = MagicMock()
        media.score = score
        media.formatted_score = formatted_score
        media.progress = progress
        media.max_progress = max_progress
        media.formatted_progress = formatted_progress
        media.status = status
        media.start_date = start_date
        media.end_date = end_date
        media.notes = notes
        media.link = link
        media.is_rewatch = is_rewatch
        media.caught_up = caught_up
        media.item.title = title
        media.item.english_title = english_title
        media.item.source = source
        return media

    def test_full_field_pin(self):
        rows = serialize_media_list([self._make_media()])
        assert rows == [
            {
                "title": "A",
                "english_title": "B",
                "score": "8.5",
                "progress": "10",
                "max_progress": "12",
                "status": "Completed",
                "start_date": "2026-01-01",
                "end_date": "2026-02-01",
                "notes": "hi",
                "link": "http://x",
                "is_rewatch": "Yes",
                "caught_up": "No",
                "source": "tmdb",
            },
        ]

    def test_score_none_serializes_to_empty_string(self):
        rows = serialize_media_list([self._make_media(score=None)])
        assert rows[0]["score"] == ""

    def test_max_progress_zero_serializes_to_empty_string(self):
        rows = serialize_media_list([self._make_media(max_progress=0)])
        assert rows[0]["max_progress"] == ""

    def test_start_date_none_serializes_to_empty_string(self):
        rows = serialize_media_list([self._make_media(start_date=None)])
        assert rows[0]["start_date"] == ""

    def test_end_date_none_serializes_to_empty_string(self):
        rows = serialize_media_list([self._make_media(end_date=None)])
        assert rows[0]["end_date"] == ""

    def test_notes_none_serializes_to_empty_string(self):
        rows = serialize_media_list([self._make_media(notes=None)])
        assert rows[0]["notes"] == ""

    def test_link_none_serializes_to_empty_string(self):
        rows = serialize_media_list([self._make_media(link=None)])
        assert rows[0]["link"] == ""

    def test_is_rewatch_false_serializes_to_no(self):
        rows = serialize_media_list([self._make_media(is_rewatch=False)])
        assert rows[0]["is_rewatch"] == "No"

    def test_caught_up_true_serializes_to_yes(self):
        rows = serialize_media_list([self._make_media(caught_up=True)])
        assert rows[0]["caught_up"] == "Yes"

    def test_english_title_none_serializes_to_empty_string(self):
        rows = serialize_media_list([self._make_media(english_title=None)])
        assert rows[0]["english_title"] == ""
