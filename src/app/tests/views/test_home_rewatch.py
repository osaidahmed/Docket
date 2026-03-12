from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import Anime, MediaTypes, Movie, Sources, Status
from app.tests.views._home_helpers import backlog_save_data, create_item
from app.tests.views.test_home import _flatten_group_titles


class RewatchSectionTests(TestCase):
    """Tests for the Rewatches section in the backlog."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    @patch("app.providers.services.get_media_metadata")
    def test_rewatch_in_dedicated_section_all_mode(self, mock_metadata):
        """Rewatch items appear in a Rewatches group, not in type groups."""
        mock_metadata.return_value = {"max_progress": None}
        item = create_item(
            "5000", Sources.TMDB.value, MediaTypes.MOVIE.value, "Rewatch Movie"
        )
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)
        Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value, is_rewatch=True
        )

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        type_titles, rewatch_titles = _collect_type_and_special_titles(
            groups, "rewatch"
        )

        self.assertIn("Rewatch Movie", rewatch_titles)
        self.assertNotIn("Rewatch Movie", type_titles)

    def test_rewatch_inline_in_type_filter(self):
        """Rewatch items appear in type group when filtering by type."""
        item = create_item(
            "5001", Sources.MAL.value, MediaTypes.ANIME.value, "Rewatch Anime"
        )
        Anime.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value, is_rewatch=True
        )

        response = self.client.get(reverse("home") + "?type=anime")
        groups = response.context["groups"]

        media_types = {g["media_type"] for g in groups}
        self.assertNotIn("rewatch", media_types)

        titles = _flatten_group_titles(groups)
        self.assertIn("Rewatch Anime", titles)

    def test_no_rewatch_section_when_empty(self):
        """No Rewatches group when no items have is_rewatch=True."""
        item = create_item(
            "5002", Sources.TMDB.value, MediaTypes.MOVIE.value, "Normal Movie"
        )
        Movie.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]
        media_types = {g["media_type"] for g in groups}
        self.assertNotIn("rewatch", media_types)
        self.assertNotContains(response, "Rewatches")

    def test_rewatch_manual_flag_no_history(self):
        """Single instance with is_rewatch=True appears in Rewatches group."""
        item = create_item(
            "5003", Sources.TMDB.value, MediaTypes.MOVIE.value, "Manual Rewatch"
        )
        Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value, is_rewatch=True
        )

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]
        rewatch_group = [g for g in groups if g["media_type"] == "rewatch"]
        self.assertEqual(len(rewatch_group), 1)

        titles = []
        for sg in rewatch_group[0]["status_groups"]:
            titles.extend(m.item.title for m in sg["items"])
        self.assertIn("Manual Rewatch", titles)

    def test_quick_rewatch_sets_is_rewatch(self):
        """quick_rewatch creates an instance with is_rewatch=True."""
        item = create_item(
            "5004", Sources.TMDB.value, MediaTypes.MOVIE.value, "Quick Rewatch Movie"
        )
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)

        self.client.post(
            reverse("quick_rewatch"),
            {
                "media_id": "5004",
                "source": Sources.TMDB.value,
                "media_type": "movie",
                "source_context": "archive",
            },
        )

        rewatch = Movie.objects.filter(
            user=self.user, item=item, status=Status.PLANNING.value
        ).first()
        self.assertIsNotNone(rewatch)
        self.assertTrue(rewatch.is_rewatch)

    def test_backlog_save_rewatch_toggle(self):
        """Saving with is_rewatch=on sets the flag on the instance."""
        item = create_item(
            "5005", Sources.TMDB.value, MediaTypes.MOVIE.value, "Toggle Rewatch"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        data = backlog_save_data(movie)
        data["is_rewatch"] = "on"
        self.client.post(reverse("backlog_save"), data)

        movie.refresh_from_db()
        self.assertTrue(movie.is_rewatch)

    @patch("app.providers.services.get_media_metadata")
    def test_rewatch_section_has_status_subgroups(self, mock_metadata):
        """Rewatches group has correct status subgroups."""
        mock_metadata.return_value = {"max_progress": None}
        for mid, status in [
            ("5010", Status.IN_PROGRESS.value),
            ("5011", Status.PLANNING.value),
            ("5012", Status.PAUSED.value),
        ]:
            item = create_item(
                mid, Sources.TMDB.value, MediaTypes.MOVIE.value, f"Rewatch {status}"
            )
            Movie.objects.create(
                item=item, user=self.user, status=status, is_rewatch=True
            )

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]
        rewatch_group = [g for g in groups if g["media_type"] == "rewatch"]
        self.assertEqual(len(rewatch_group), 1)

        statuses = [sg["status"] for sg in rewatch_group[0]["status_groups"]]
        self.assertEqual(
            statuses,
            [Status.IN_PROGRESS.value, Status.PLANNING.value, Status.PAUSED.value],
        )

    def test_backlog_save_rewatch_toggle_triggers_refresh(self):
        """Toggling is_rewatch on via backlog_save triggers HX-Refresh."""
        item = create_item(
            "5030", Sources.TMDB.value, MediaTypes.MOVIE.value, "Refresh Toggle Movie"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        data = backlog_save_data(movie)
        data["is_rewatch"] = "on"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response["HX-Refresh"], "true")

    def test_backlog_save_rewatch_untoggle_triggers_refresh(self):
        """Toggling is_rewatch off via backlog_save triggers HX-Refresh."""
        item = create_item(
            "5031", Sources.TMDB.value, MediaTypes.MOVIE.value, "Unrefresh Toggle Movie"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value, is_rewatch=True
        )

        data = backlog_save_data(movie)
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response["HX-Refresh"], "true")

    @patch("app.providers.services.get_media_metadata")
    def test_backlog_save_rewatch_unchanged_no_refresh(self, mock_metadata):
        """Saving without changing is_rewatch does not trigger HX-Refresh."""
        mock_metadata.return_value = {"max_progress": None}
        item = create_item(
            "5032", Sources.TMDB.value, MediaTypes.MOVIE.value, "No Refresh Movie"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        data = backlog_save_data(movie)
        data["score"] = "8.0"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertNotIn("HX-Refresh", response)

    def test_archive_save_rewatch_toggle_triggers_refresh(self):
        """Toggling is_rewatch on archive card triggers HX-Refresh."""
        item = create_item(
            "5033", Sources.TMDB.value, MediaTypes.MOVIE.value, "Archive Rewatch Toggle"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.COMPLETED.value
        )

        data = backlog_save_data(movie)
        data["source_context"] = "archive"
        data["is_rewatch"] = "on"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response["HX-Refresh"], "true")

    def test_rewatch_toggle_moves_item_on_reload(self):
        """Toggling is_rewatch moves item to Rewatches group on reload."""
        item = create_item(
            "5034", Sources.TMDB.value, MediaTypes.MOVIE.value, "Move To Rewatch"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        page_before = self.client.get(reverse("home"))
        groups_before = page_before.context["groups"]
        rewatch_groups = [g for g in groups_before if g["media_type"] == "rewatch"]
        self.assertEqual(len(rewatch_groups), 0)

        data = backlog_save_data(movie)
        data["is_rewatch"] = "on"
        self.client.post(reverse("backlog_save"), data)

        page_after = self.client.get(reverse("home"))
        groups_after = page_after.context["groups"]
        rewatch_group = [g for g in groups_after if g["media_type"] == "rewatch"]
        self.assertEqual(len(rewatch_group), 1)
        titles = []
        for sg in rewatch_group[0]["status_groups"]:
            titles.extend(m.item.title for m in sg["items"])
        self.assertIn("Move To Rewatch", titles)

    def test_rewatch_section_after_type_groups(self):
        """Rewatches group appears after all type groups."""
        item_normal = create_item(
            "5020", Sources.TMDB.value, MediaTypes.MOVIE.value, "Normal Movie"
        )
        Movie.objects.create(
            item=item_normal, user=self.user, status=Status.PLANNING.value
        )

        item_rewatch = create_item(
            "5021", Sources.TMDB.value, MediaTypes.MOVIE.value, "Rewatch Movie"
        )
        Movie.objects.create(
            item=item_rewatch,
            user=self.user,
            status=Status.PLANNING.value,
            is_rewatch=True,
        )

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]
        self.assertGreaterEqual(len(groups), 2)
        self.assertEqual(groups[-1]["media_type"], "rewatch")
        self.assertEqual(groups[-1]["label"], "Rewatches")

    def test_edit_form_has_is_rewatch_checkbox(self):
        """The backlog card edit form contains an is_rewatch checkbox."""
        item = create_item(
            "5040", Sources.TMDB.value, MediaTypes.MOVIE.value, "Checkbox Form Movie"
        )
        Movie.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        response = self.client.get(reverse("home"))
        self.assertContains(response, 'name="is_rewatch"')

    def test_is_rewatch_checkbox_checked_when_true(self):
        """The is_rewatch checkbox is checked when the field is True."""
        item = create_item(
            "5041", Sources.TMDB.value, MediaTypes.MOVIE.value, "Checked Rewatch Movie"
        )
        Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
            is_rewatch=True,
        )

        response = self.client.get(reverse("home"))
        content = response.content.decode()
        rewatch_pos = content.find('name="is_rewatch"')
        checkbox_context = content[rewatch_pos : rewatch_pos + 200]
        self.assertIn("checked", checkbox_context)

    def test_backlog_save_is_rewatch_uncheck_persists(self):
        """Unchecking is_rewatch via edit form persists on reload."""
        item = create_item(
            "5042", Sources.TMDB.value, MediaTypes.MOVIE.value, "Uncheck Rewatch Movie"
        )
        movie = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
            is_rewatch=True,
        )

        data = backlog_save_data(movie)
        self.client.post(reverse("backlog_save"), data)

        movie.refresh_from_db()
        self.assertFalse(movie.is_rewatch)

    @patch("app.providers.services.get_media_metadata")
    def test_archive_save_is_rewatch_untoggle_triggers_refresh(self, mock_metadata):
        """Toggling is_rewatch off on archive card triggers HX-Refresh."""
        mock_metadata.return_value = {"max_progress": None}
        item = create_item(
            "5043", Sources.TMDB.value, MediaTypes.MOVIE.value, "Archive Untoggle Movie"
        )
        movie = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.COMPLETED.value,
            is_rewatch=True,
        )

        data = backlog_save_data(movie)
        data["source_context"] = "archive"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response["HX-Refresh"], "true")

    @patch("app.providers.services.get_media_metadata")
    def test_archive_save_is_rewatch_unchanged_no_refresh(self, mock_metadata):
        """Archive edit without is_rewatch change has no refresh."""
        mock_metadata.return_value = {"max_progress": None}
        item = create_item(
            "5044",
            Sources.TMDB.value,
            MediaTypes.MOVIE.value,
            "Archive No Refresh Movie",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.COMPLETED.value
        )

        data = backlog_save_data(movie)
        data["source_context"] = "archive"
        data["score"] = "9.0"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertNotIn("HX-Refresh", response)

    def test_is_rewatch_combined_with_status_change(self):
        """Both status and is_rewatch change in one save triggers refresh."""
        item = create_item(
            "5045", Sources.TMDB.value, MediaTypes.MOVIE.value, "Combined Change Movie"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        data = backlog_save_data(movie)
        data["status"] = Status.IN_PROGRESS.value
        data["is_rewatch"] = "on"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response["HX-Refresh"], "true")
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.IN_PROGRESS.value)
        self.assertTrue(movie.is_rewatch)

    def test_is_rewatch_with_caught_up_both_toggled(self):
        """Both is_rewatch and caught_up save correctly together."""
        item = create_item(
            "5046", Sources.MAL.value, MediaTypes.ANIME.value, "Both Flags Anime"
        )
        anime = Anime.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        data = backlog_save_data(anime)
        data["is_rewatch"] = "on"
        data["caught_up"] = "on"
        self.client.post(reverse("backlog_save"), data)

        anime.refresh_from_db()
        self.assertTrue(anime.is_rewatch)
        self.assertTrue(anime.caught_up)

    def test_type_group_disappears_when_all_items_are_rewatches(self):
        """Type group is removed when all its items are rewatches."""
        item = create_item(
            "5047", Sources.TMDB.value, MediaTypes.MOVIE.value, "Only Rewatch Movie"
        )
        Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
            is_rewatch=True,
        )

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]
        type_groups = [g for g in groups if g["media_type"] == MediaTypes.MOVIE.value]
        self.assertEqual(len(type_groups), 0)

        rewatch_groups = [g for g in groups if g["media_type"] == "rewatch"]
        self.assertEqual(len(rewatch_groups), 1)

    def test_quick_rewatch_archive_response_has_hx_refresh(self):
        """quick_rewatch from archive context returns HX-Refresh header."""
        item = create_item(
            "5048", Sources.TMDB.value, MediaTypes.MOVIE.value, "HX Refresh Rewatch"
        )
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)

        response = self.client.post(
            reverse("quick_rewatch"),
            {
                "media_id": "5048",
                "source": Sources.TMDB.value,
                "media_type": "movie",
                "source_context": "archive",
            },
        )

        self.assertEqual(response["HX-Refresh"], "true")

    def test_rewatch_untoggle_moves_back_to_type_group(self):
        """Untoggling is_rewatch moves item back to type group on reload."""
        normal_item = create_item(
            "5049", Sources.TMDB.value, MediaTypes.MOVIE.value, "Keep In Type"
        )
        Movie.objects.create(
            item=normal_item, user=self.user, status=Status.PLANNING.value
        )

        item = create_item(
            "5050", Sources.TMDB.value, MediaTypes.MOVIE.value, "Back To Type Movie"
        )
        movie = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
            is_rewatch=True,
        )

        page_before = self.client.get(reverse("home"))
        rewatch_groups = [
            g for g in page_before.context["groups"] if g["media_type"] == "rewatch"
        ]
        self.assertEqual(len(rewatch_groups), 1)

        data = backlog_save_data(movie)
        self.client.post(reverse("backlog_save"), data)

        page_after = self.client.get(reverse("home"))
        groups_after = page_after.context["groups"]
        rewatch_groups = [g for g in groups_after if g["media_type"] == "rewatch"]
        self.assertEqual(len(rewatch_groups), 0)

        type_titles = _flatten_group_titles(groups_after)
        self.assertIn("Back To Type Movie", type_titles)


def _collect_type_and_special_titles(groups, special_media_type):
    """Split backlog groups into type-group titles and special-group titles."""
    type_titles = []
    special_titles = []
    for group in groups:
        target = (
            special_titles if group["media_type"] == special_media_type else type_titles
        )
        for sg in group["status_groups"]:
            target.extend(m.item.title for m in sg["items"])
    return type_titles, special_titles
