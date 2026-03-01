import json

from django.test import TestCase

from app.services.export import format_csv, format_json, format_markdown, format_txt


class FormatCsvTests(TestCase):
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
