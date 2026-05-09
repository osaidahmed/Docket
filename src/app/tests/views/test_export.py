import json

from defusedxml.ElementTree import fromstring as xml_fromstring
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import Anime, Item, Manga, MediaTypes, Movie, Sources, Status


class ExportMediaViewTests(TestCase):
    """Test the export media views."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        completed_count = 2
        for i in range(1, 4):
            item = Item.objects.create(
                media_id=str(100 + i),
                source=Sources.MANUAL.value,
                media_type=MediaTypes.MOVIE.value,
                title=f"Export Movie {i}",
                image="http://example.com/image.jpg",
            )
            is_completed = i <= completed_count
            Movie.objects.create(
                item=item,
                user=cls.user,
                status=(
                    Status.COMPLETED.value if is_completed else Status.IN_PROGRESS.value
                ),
                progress=1 if is_completed else 0,
                score=i * 3,
            )

    def setUp(self):
        self.client.login(**self.credentials)

    def test_export_csv(self):
        response = self.client.get(
            reverse("export_media", args=["movie"]) + "?format=csv"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("attachment", response["Content-Disposition"])
        self.assertIn(".csv", response["Content-Disposition"])
        content = response.content.decode()
        self.assertIn("title", content)
        self.assertIn("Export Movie 1", content)

    def test_export_json(self):
        response = self.client.get(
            reverse("export_media", args=["movie"]) + "?format=json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = json.loads(response.content)
        self.assertEqual(len(data), 3)
        titles = {row["title"] for row in data}
        self.assertIn("Export Movie 1", titles)

    def test_export_markdown(self):
        response = self.client.get(
            reverse("export_media", args=["movie"]) + "?format=md"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response["Content-Type"])
        content = response.content.decode()
        self.assertIn("| title", content)
        self.assertIn("| ---", content)
        self.assertIn("Export Movie 1", content)

    def test_export_markdown_has_heading(self):
        response = self.client.get(
            reverse("export_media", args=["movie"]) + "?format=md"
        )
        content = response.content.decode()
        self.assertTrue(content.startswith("# Movies"))

    def test_export_invalid_format(self):
        response = self.client.get(
            reverse("export_media", args=["movie"]) + "?format=xml"
        )
        self.assertEqual(response.status_code, 400)

    def test_export_respects_status_filter(self):
        pref = self.user.get_or_create_media_pref("movie")
        pref.status_filter = Status.COMPLETED.value
        pref.save(update_fields=["status_filter"])

        response = self.client.get(
            reverse("export_media", args=["movie"]) + "?format=json"
        )
        data = json.loads(response.content)
        self.assertEqual(len(data), 2)
        for row in data:
            self.assertEqual(row["status"], "Completed")

    def test_export_respects_search(self):
        response = self.client.get(
            reverse("export_media", args=["movie"]) + "?format=json&search=Movie 1"
        )
        data = json.loads(response.content)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["title"], "Export Movie 1")

    def test_export_csv_filename_contains_date(self):
        response = self.client.get(
            reverse("export_media", args=["movie"]) + "?format=csv"
        )
        self.assertRegex(
            response["Content-Disposition"],
            r"movies_\d{4}-\d{2}-\d{2}\.csv",
        )

    def test_export_empty_list(self):
        pref = self.user.get_or_create_media_pref("movie")
        pref.status_filter = Status.PAUSED.value
        pref.save(update_fields=["status_filter"])

        response = self.client.get(
            reverse("export_media", args=["movie"]) + "?format=json"
        )
        data = json.loads(response.content)
        self.assertEqual(len(data), 0)

    def test_export_csv_empty_returns_empty_body(self):
        pref = self.user.get_or_create_media_pref("movie")
        pref.status_filter = Status.PAUSED.value
        pref.save(update_fields=["status_filter"])

        response = self.client.get(
            reverse("export_media", args=["movie"]) + "?format=csv"
        )
        self.assertEqual(response.content.decode(), "")


class ExportMalXmlViewTests(TestCase):
    """Test the MAL XML export branch of export_media."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "malxmluser", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        anime_item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Cowboy Bebop",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
            item=anime_item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
            progress=2,
        )

        manga_item = Item.objects.create(
            media_id="2",
            source=Sources.MAL.value,
            media_type=MediaTypes.MANGA.value,
            title="Berserk",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=manga_item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
            progress=10,
        )

        non_mal_anime = Item.objects.create(
            media_id="999",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Manual Anime",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
            item=non_mal_anime,
            user=cls.user,
            status=Status.COMPLETED.value,
            progress=1,
        )

    def setUp(self):
        self.client.login(**self.credentials)

    def test_anime_mal_xml_200(self):
        response = self.client.get(
            reverse("export_media", args=["anime"]) + "?format=mal_xml"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/xml")
        self.assertRegex(
            response["Content-Disposition"],
            r"animelist_malxmluser_\d{4}-\d{2}-\d{2}\.xml",
        )
        root = xml_fromstring(response.content.decode())
        self.assertEqual(root.tag, "myanimelist")
        self.assertEqual(len(root.findall("anime")), 1)

    def test_manga_mal_xml_200(self):
        response = self.client.get(
            reverse("export_media", args=["manga"]) + "?format=mal_xml"
        )
        self.assertEqual(response.status_code, 200)
        self.assertRegex(
            response["Content-Disposition"],
            r"mangalist_malxmluser_\d{4}-\d{2}-\d{2}\.xml",
        )
        root = xml_fromstring(response.content.decode())
        self.assertEqual(len(root.findall("manga")), 1)

    def test_mal_xml_invalid_media_type_400(self):
        response = self.client.get(
            reverse("export_media", args=["movie"]) + "?format=mal_xml"
        )
        self.assertEqual(response.status_code, 400)

    def test_mal_xml_skips_non_mal_source(self):
        response = self.client.get(
            reverse("export_media", args=["anime"]) + "?format=mal_xml"
        )
        body = response.content.decode()
        self.assertIn("Skipped 1 entries without MAL IDs", body)
        self.assertNotIn("Manual Anime", body)


class ExportTxtViewTests(TestCase):
    """Test the TXT export view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        for i in range(1, 3):
            item = Item.objects.create(
                media_id=str(200 + i),
                source=Sources.MANUAL.value,
                media_type=MediaTypes.MOVIE.value,
                title=f"TXT Movie {i}",
                image="http://example.com/image.jpg",
            )
            Movie.objects.create(
                item=item,
                user=cls.user,
                status=Status.COMPLETED.value,
                score=8,
            )

    def setUp(self):
        self.client.login(**self.credentials)

    def test_export_txt_basic(self):
        response = self.client.post(
            reverse("export_media_txt", args=["movie"]),
            {"template": "{title} ({score})", "separator": "\\n"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/plain")
        content = response.content.decode()
        self.assertIn("TXT Movie 1 (8.0)", content)
        self.assertIn("TXT Movie 2 (8.0)", content)

    def test_export_txt_custom_separator(self):
        response = self.client.post(
            reverse("export_media_txt", args=["movie"]),
            {"template": "{title}", "separator": " | "},
        )
        content = response.content.decode()
        self.assertIn(" | ", content)

    def test_export_txt_saves_config(self):
        self.client.post(
            reverse("export_media_txt", args=["movie"]),
            {"template": "{title} - {status}", "separator": "---"},
        )
        self.user.refresh_from_db()
        self.assertEqual(self.user.export_txt_config["template"], "{title} - {status}")
        self.assertEqual(self.user.export_txt_config["separator"], "---")

    def test_export_txt_newline_escape(self):
        response = self.client.post(
            reverse("export_media_txt", args=["movie"]),
            {"template": "{title}", "separator": "\\n"},
        )
        content = response.content.decode()
        self.assertIn("\n", content)
        self.assertNotIn("\\n", content)

    def test_export_txt_respects_search(self):
        response = self.client.post(
            reverse("export_media_txt", args=["movie"]),
            {"template": "{title}", "separator": "\\n", "search": "Movie 1"},
        )
        content = response.content.decode()
        self.assertIn("TXT Movie 1", content)
        self.assertNotIn("TXT Movie 2", content)

    def test_export_txt_unknown_placeholder(self):
        response = self.client.post(
            reverse("export_media_txt", args=["movie"]),
            {"template": "{title} {nonexistent}", "separator": "\\n"},
        )
        content = response.content.decode()
        self.assertIn("TXT Movie 1 ", content)


class PrintMediaViewTests(TestCase):
    """Test the print media view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        completed_count = 2
        for i in range(1, 4):
            item = Item.objects.create(
                media_id=str(300 + i),
                source=Sources.MANUAL.value,
                media_type=MediaTypes.MOVIE.value,
                title=f"Print Movie {i}",
                image="http://example.com/image.jpg",
            )
            Movie.objects.create(
                item=item,
                user=cls.user,
                status=(
                    Status.COMPLETED.value
                    if i <= completed_count
                    else Status.IN_PROGRESS.value
                ),
            )

    def setUp(self):
        self.client.login(**self.credentials)

    def test_print_media_renders(self):
        response = self.client.get(reverse("print_media", args=["movie"]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/print_media.html")

    def test_print_media_contains_items(self):
        response = self.client.get(reverse("print_media", args=["movie"]))
        self.assertContains(response, "Print Movie 1")
        self.assertContains(response, "Print Movie 2")
        self.assertContains(response, "Print Movie 3")
        self.assertEqual(response.context["total_count"], 3)

    def test_print_media_respects_status_filter(self):
        pref = self.user.get_or_create_media_pref("movie")
        pref.status_filter = Status.COMPLETED.value
        pref.save(update_fields=["status_filter"])

        response = self.client.get(reverse("print_media", args=["movie"]))
        self.assertEqual(response.context["total_count"], 2)

    def test_print_media_respects_search(self):
        response = self.client.get(
            reverse("print_media", args=["movie"]) + "?search=Movie 1"
        )
        self.assertEqual(response.context["total_count"], 1)
        self.assertContains(response, "Print Movie 1")

    def test_print_media_auto_prints(self):
        response = self.client.get(reverse("print_media", args=["movie"]))
        self.assertContains(response, "window.print()")

    def test_print_media_not_extends_base(self):
        response = self.client.get(reverse("print_media", args=["movie"]))
        self.assertNotContains(response, "sidebar")


class ExportAuthTests(TestCase):
    """Test that export views require authentication."""

    def test_export_media_requires_auth(self):
        response = self.client.get(
            reverse("export_media", args=["movie"]) + "?format=csv"
        )
        self.assertEqual(response.status_code, 302)

    def test_export_txt_requires_auth(self):
        response = self.client.post(
            reverse("export_media_txt", args=["movie"]),
            {"template": "{title}"},
        )
        self.assertEqual(response.status_code, 302)

    def test_print_media_requires_auth(self):
        response = self.client.get(reverse("print_media", args=["movie"]))
        self.assertEqual(response.status_code, 302)
