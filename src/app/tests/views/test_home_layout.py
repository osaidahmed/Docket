from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app.models import (
    TV,
    Anime,
    Game,
    Item,
    MediaTypes,
    Movie,
    Sources,
    Status,
)
from events.models import Event
from users.models import HomeTruncationChoices


class LayoutGroupToggleTests(TestCase):
    """Test layout/group toggles, all 6 combos, and template rendering safety."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.anime_item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Test Anime",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
            item=cls.anime_item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
            progress=5,
        )
        Event.objects.create(
            item=cls.anime_item,
            content_number=6,
            datetime=timezone.now() + timedelta(days=2),
        )

        cls.tv_item = Item.objects.create(
            media_id="100",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Test TV Show",
            image="http://example.com/image.jpg",
        )
        TV.objects.create(
            item=cls.tv_item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
        )
        Event.objects.create(
            item=cls.tv_item,
            content_number=4,
            datetime=timezone.now() + timedelta(days=1),
        )

        movie_item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=movie_item,
            user=cls.user,
            status=Status.PLANNING.value,
        )

        game_item = Item.objects.create(
            media_id="500",
            source=Sources.TMDB.value,
            media_type=MediaTypes.GAME.value,
            title="Test Game",
            image="http://example.com/image.jpg",
        )
        Game.objects.create(
            item=game_item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
            progress=10,
        )

    def setUp(self):
        self.client.login(**self.credentials)

    # --- Preference persistence ---

    def test_default_layout_is_cards(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.context["current_layout"], "cards")

    def test_default_group_is_type(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.context["current_group"], "type")

    def test_layout_persists_via_url_param(self):
        response = self.client.get(reverse("home") + "?layout=grid")
        self.assertEqual(response.context["current_layout"], "grid")
        self.user.refresh_from_db()
        self.assertEqual(self.user.home_layout, "grid")

    def test_group_persists_via_url_param(self):
        response = self.client.get(reverse("home") + "?group=status")
        self.assertEqual(response.context["current_group"], "status")
        self.user.refresh_from_db()
        self.assertEqual(self.user.home_group, "status")

    def test_invalid_layout_falls_back(self):
        response = self.client.get(reverse("home") + "?layout=kanban")
        self.assertEqual(response.context["current_layout"], "cards")

    def test_invalid_group_falls_back(self):
        response = self.client.get(reverse("home") + "?group=priority")
        self.assertEqual(response.context["current_group"], "type")

    # --- All 6 layout x group combos render without errors ---

    def test_cards_type_renders(self):
        response = self.client.get(reverse("home") + "?layout=cards&group=type")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "backlog-card-")

    def test_cards_status_renders(self):
        response = self.client.get(reverse("home") + "?layout=cards&group=status")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "backlog-card-")

    def test_grid_type_renders(self):
        response = self.client.get(reverse("home") + "?layout=grid&group=type")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "media-grid")

    def test_grid_status_renders(self):
        response = self.client.get(reverse("home") + "?layout=grid&group=status")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "media-grid")

    def test_table_type_renders(self):
        response = self.client.get(reverse("home") + "?layout=table&group=type")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<table")

    def test_table_status_renders(self):
        response = self.client.get(reverse("home") + "?layout=table&group=status")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<table")

    # --- TV with next_event across all layouts (no unit -- was KeyError) ---

    def test_grid_renders_tv_with_next_event(self):
        """Grid card renders next_event badge for TV without crashing."""
        response = self.client.get(reverse("home") + "?layout=grid&group=type")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test TV Show")

    def test_table_renders_tv_with_next_event(self):
        """Table row renders next_event column for TV without crashing."""
        response = self.client.get(reverse("home") + "?layout=table&group=type")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test TV Show")

    def test_cards_renders_tv_with_next_event(self):
        """Card renders next_event for TV without crashing."""
        response = self.client.get(reverse("home") + "?layout=cards&group=type")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test TV Show")

    # --- Grid progress_changer for types without unit ---

    def test_grid_renders_game_progress(self):
        """Grid progress changer works for game (no unit)."""
        response = self.client.get(reverse("home") + "?layout=grid&group=type")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Game")

    def test_grid_renders_movie_in_planning(self):
        """Grid renders movie without progress changer crash."""
        response = self.client.get(reverse("home") + "?layout=grid&group=type")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Movie")

    # --- Status grouping structure ---

    def test_status_grouping_shows_status_headers(self):
        response = self.client.get(reverse("home") + "?group=status")
        groups = response.context["groups"]
        labels = [g["label"] for g in groups]
        self.assertIn("In progress", labels)
        self.assertIn("Planning", labels)

    def test_status_grouping_mixes_media_types(self):
        """Status grouping puts anime and TV in the same 'In progress' group."""
        response = self.client.get(reverse("home") + "?group=status")
        groups = response.context["groups"]
        in_progress = next(g for g in groups if g["label"] == "In progress")
        items = in_progress["status_groups"][0]["items"]
        media_types = {m.item.media_type for m in items}
        self.assertTrue(len(media_types) > 1)

    def test_type_grouping_hides_status_subheader_for_status_mode(self):
        """Status sub-headers should not appear when grouping by status."""
        response = self.client.get(reverse("home") + "?layout=cards&group=status")
        html = response.content.decode()
        self.assertNotIn("uppercase tracking-wider", html)

    # --- Table type column visibility ---

    def test_table_hides_type_column_when_grouped_by_type(self):
        """Type column header should not appear when table is grouped by type."""
        response = self.client.get(reverse("home") + "?layout=table&group=type")
        html = response.content.decode()
        self.assertNotIn("<th", html.split("Type")[0].split("<table")[-1])
        self.assertNotContains(response, "icon media.item.media_type")

    def test_table_shows_type_column_when_grouped_by_status(self):
        """Type column should appear when table is grouped by status."""
        response = self.client.get(reverse("home") + "?layout=table&group=status")
        html = response.content.decode()
        self.assertIn(">Type</th>", html)

    # --- Truncation with status grouping ---

    def test_truncation_skipped_for_status_grouping(self):
        """Truncation is not applied in status grouping mode."""
        self.user.home_truncation = HomeTruncationChoices.THREE
        self.user.save(update_fields=["home_truncation"])
        response = self.client.get(reverse("home") + "?layout=cards&group=status")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "See all")

    @patch("app.providers.services.get_media_metadata")
    def test_truncation_works_for_type_grouping(self, mock_metadata):
        """Truncation 'See all' still appears in type grouping mode."""
        mock_metadata.return_value = {"max_progress": None}
        self.user.home_truncation = HomeTruncationChoices.THREE
        self.user.save(update_fields=["home_truncation"])
        for i in range(3):
            item = Item.objects.create(
                media_id=f"extra_anime_{i}",
                source=Sources.MAL.value,
                media_type=MediaTypes.ANIME.value,
                title=f"Extra Anime {i}",
                image="http://example.com/image.jpg",
            )
            Anime.objects.create(
                item=item,
                user=self.user,
                status=Status.IN_PROGRESS.value,
                progress=1,
            )
        response = self.client.get(reverse("home") + "?layout=cards&group=type")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "See all")

    # --- URL param preservation ---

    def test_type_filter_chips_preserve_layout_and_group(self):
        response = self.client.get(reverse("home") + "?layout=grid&group=status")
        for chip in response.context["type_filter_choices"]:
            self.assertIn("layout=grid", chip["toggle_url"])
            self.assertIn("group=status", chip["toggle_url"])

    def test_sort_links_preserve_layout_and_group(self):
        response = self.client.get(reverse("home") + "?layout=table&group=type")
        html = response.content.decode()
        self.assertIn("layout=table&amp;group=type", html)

    # --- Archive layouts ---

    @patch("app.providers.services.get_media_metadata")
    def test_archive_grid_layout(self, mock_metadata):
        mock_metadata.return_value = {"max_progress": None}
        completed_item = Item.objects.create(
            media_id="999",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Completed Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=completed_item,
            user=self.user,
            status=Status.COMPLETED.value,
        )
        response = self.client.get(reverse("home") + "?view=archive&layout=grid")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "media-grid")

    @patch("app.providers.services.get_media_metadata")
    def test_archive_table_layout(self, mock_metadata):
        mock_metadata.return_value = {"max_progress": None}
        completed_item = Item.objects.create(
            media_id="998",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Another Completed Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=completed_item,
            user=self.user,
            status=Status.COMPLETED.value,
        )
        response = self.client.get(reverse("home") + "?view=archive&layout=table")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "<table")
