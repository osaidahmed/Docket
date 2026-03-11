from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import Anime, Item, MediaTypes, Movie, Sources, Status
from app.tests.views.test_home import _flatten_group_titles


class ArchiveViewTests(TestCase):
    """Tests for the dedicated archive page and archive card editing."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def _archive_url(self):
        return reverse("home") + "?view=archive"

    def _backlog_save_data(self, media, source_context="archive"):
        return {
            "media_id": media.item.media_id,
            "source": media.item.source,
            "media_type": media.item.media_type,
            "instance_id": media.id,
            "score": "",
            "progress": media.progress if media.progress is not None else "",
            "status": media.status,
            "start_date": "",
            "end_date": "",
            "notes": "",
            "link": "",
            "source_context": source_context,
        }

    # --- Archive page layout ---

    def test_archive_page_shows_archive_title(self):
        """Archive view shows 'Archive' as page title, not 'Backlog'."""
        response = self.client.get(self._archive_url())
        self.assertContains(response, ">Archive</h1>")
        self.assertNotContains(response, ">Backlog</h1>")

    def test_archive_page_hides_sort_but_shows_type_filters(self):
        """Archive view hides sort dropdown but shows type filter chips."""
        response = self.client.get(self._archive_url())
        self.assertNotContains(response, "arrows-up-down")
        self.assertContains(response, "rounded-full text-sm font-medium")

    @patch("app.providers.services.get_media_metadata")
    def test_archive_page_shows_completed_items(self, mock_metadata):
        """Completed items appear on the archive page."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="2000",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Archived Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)

        response = self.client.get(self._archive_url())
        self.assertContains(response, "Archived Movie")

    def test_archive_page_empty_state(self):
        """Archive page shows empty state when no completed items."""
        response = self.client.get(self._archive_url())
        self.assertContains(response, "No completed items yet")

    def test_archive_page_excludes_backlog_items(self):
        """In-progress items do not appear on the archive page."""
        item = Item.objects.create(
            media_id="2001",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Active Anime",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(item=item, user=self.user, status=Status.IN_PROGRESS.value)

        response = self.client.get(self._archive_url())
        self.assertNotContains(response, "Active Anime")

    @patch("app.providers.services.get_media_metadata")
    def test_archive_page_no_collapsible_section(self, mock_metadata):
        """Archive view shows items directly, not inside a collapsible."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="2002",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Direct Display Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)

        response = self.client.get(self._archive_url())
        self.assertNotContains(response, "archiveOpen")
        self.assertContains(response, "Direct Display Movie")

    # --- Archive card edit button ---

    @patch("app.providers.services.get_media_metadata")
    def test_archive_card_has_edit_button(self, mock_metadata):
        """Archive cards include an edit button."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="2010",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Editable Archive Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)

        response = self.client.get(self._archive_url())
        self.assertContains(response, 'title="Edit"')

    @patch("app.providers.services.get_media_metadata")
    def test_archive_card_has_edit_form(self, mock_metadata):
        """Archive cards include an inline edit form with source_context."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="2011",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Form Archive Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)

        response = self.client.get(self._archive_url())
        self.assertContains(response, 'name="source_context" value="archive"')
        self.assertContains(response, 'name="score"')
        self.assertContains(response, 'name="notes"')

    # --- Archive edit persistence ---

    @patch("app.providers.services.get_media_metadata")
    def test_archive_edit_score_persists_on_reload(self, mock_metadata):
        """Score edited on archive card persists after page reload."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="2020",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Score Edit Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.COMPLETED.value
        )

        data = self._backlog_save_data(movie)
        data["score"] = "8.5"
        self.client.post(reverse("backlog_save"), data)

        movie.refresh_from_db()
        self.assertEqual(float(movie.score), 8.5)

        response = self.client.get(self._archive_url())
        self.assertContains(response, "8.5")

    @patch("app.providers.services.get_media_metadata")
    def test_archive_edit_notes_persist_on_reload(self, mock_metadata):
        """Notes edited on archive card persist after page reload."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="2021",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Notes Edit Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.COMPLETED.value
        )

        data = self._backlog_save_data(movie)
        data["notes"] = "Great film, would watch again"
        self.client.post(reverse("backlog_save"), data)

        movie.refresh_from_db()
        self.assertEqual(movie.notes, "Great film, would watch again")

    @patch("app.providers.services.get_media_metadata")
    def test_archive_edit_link_persists_on_reload(self, mock_metadata):
        """Link edited on archive card persists after page reload."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="2022",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Link Edit Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.COMPLETED.value
        )

        data = self._backlog_save_data(movie)
        data["link"] = "https://example.com/watch"
        self.client.post(reverse("backlog_save"), data)

        response = self.client.get(self._archive_url())
        self.assertContains(response, "https://example.com/watch")

    # --- Archive edit returns correct template ---

    @patch("app.providers.services.get_media_metadata")
    def test_archive_edit_returns_archived_card(self, mock_metadata):
        """Saving from archive returns the archived card template."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="2030",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Archive Template Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.COMPLETED.value
        )

        data = self._backlog_save_data(movie)
        data["score"] = "9"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertTemplateUsed(response, "app/components/backlog_card_archived.html")
        self.assertContains(response, "archive-card-")
        self.assertContains(response, "Archive Template Movie")

    @patch("app.providers.services.get_media_metadata")
    def test_archive_edit_status_change_triggers_refresh(self, mock_metadata):
        """Changing status from archive triggers HX-Refresh."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="2031",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Status Change Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.COMPLETED.value
        )

        data = self._backlog_save_data(movie)
        data["status"] = Status.PLANNING.value
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response["HX-Refresh"], "true")

    # --- Archive edit consistency (HTMX response vs reload) ---

    @patch("app.providers.services.get_media_metadata")
    def test_archive_edit_score_response_matches_reload(self, mock_metadata):
        """Score in HTMX response matches what appears on archive reload."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="2040",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Score Consistency Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.COMPLETED.value
        )

        data = self._backlog_save_data(movie)
        data["score"] = "7.0"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertContains(response, "7.0")

        page = self.client.get(self._archive_url())
        self.assertContains(page, "7.0")

    @patch("app.providers.services.get_media_metadata")
    def test_archive_edit_link_response_matches_reload(self, mock_metadata):
        """Link in HTMX response matches what appears on archive reload."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="2041",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Link Consistency Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.COMPLETED.value
        )

        data = self._backlog_save_data(movie)
        data["link"] = "https://example.com/consistent"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertContains(response, "https://example.com/consistent")

        page = self.client.get(self._archive_url())
        self.assertContains(page, "https://example.com/consistent")

    @patch("app.providers.services.get_media_metadata")
    def test_archive_status_change_moves_to_backlog(self, mock_metadata):
        """Changing archived item to Planning moves it to backlog on reload."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="2042",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Unarchive Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.COMPLETED.value
        )

        data = self._backlog_save_data(movie)
        data["status"] = Status.PLANNING.value
        self.client.post(reverse("backlog_save"), data)

        archive_page = self.client.get(self._archive_url())
        self.assertNotContains(archive_page, "Unarchive Movie")

        backlog_page = self.client.get(reverse("home"))
        titles = _flatten_group_titles(backlog_page.context["groups"])
        self.assertIn("Unarchive Movie", titles)

    @patch("app.providers.services.get_media_metadata")
    def test_archive_edit_form_errors_keep_form_open(self, mock_metadata):
        """Invalid form submission returns archived card with errors shown."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="2043",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Error Form Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.COMPLETED.value
        )

        data = self._backlog_save_data(movie)
        data["score"] = "999"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertTemplateUsed(response, "app/components/backlog_card_archived.html")

    @patch("app.providers.services.get_media_metadata")
    def test_archive_card_id_present(self, mock_metadata):
        """Archive cards have a unique ID for HTMX targeting."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="2044",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="ID Check Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.COMPLETED.value
        )

        response = self.client.get(self._archive_url())
        self.assertContains(response, f"archive-card-movie-{movie.id}")

    @patch("app.providers.services.get_media_metadata")
    def test_completed_oob_card_has_edit_button(self, mock_metadata):
        """OOB-inserted archive card from quick_complete has edit button."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="2050",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="OOB Edit Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        response = self.client.post(
            reverse("quick_complete"),
            {"media_type": "movie", "instance_id": movie.id},
        )

        self.assertContains(response, 'title="Edit"')
        self.assertContains(response, "archive-card-")

    # --- Archive caught_up checkbox ---

    @patch("app.providers.services.get_media_metadata")
    def test_archive_card_caught_up_checkbox_present(self, mock_metadata):
        """Archive card for anime shows caught_up checkbox."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="2060",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Caught Up Archive Anime",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)
        response = self.client.get(self._archive_url())
        self.assertContains(response, 'name="caught_up"')

    @patch("app.providers.services.get_media_metadata")
    def test_archive_card_caught_up_toggle(self, mock_metadata):
        """Caught up can be toggled from archive card edit form."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="2061",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Toggle Caught Up Anime",
            image="http://example.com/image.jpg",
        )
        anime = Anime.objects.create(
            item=item,
            user=self.user,
            status=Status.COMPLETED.value,
            caught_up=False,
        )
        data = self._backlog_save_data(anime)
        data["caught_up"] = "on"
        self.client.post(reverse("backlog_save"), data)
        anime.refresh_from_db()
        self.assertTrue(anime.caught_up)

    # --- Archive type filtering ---

    @patch("app.providers.services.get_media_metadata")
    def test_archive_filters_by_media_type(self, mock_metadata):
        """Archive page filters items when type parameter is provided."""
        mock_metadata.return_value = {"max_progress": None}
        anime_item = Item.objects.create(
            media_id="2070",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Filtered Anime",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
            item=anime_item,
            user=self.user,
            status=Status.COMPLETED.value,
        )
        movie_item = Item.objects.create(
            media_id="2071",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Filtered Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.COMPLETED.value,
        )

        response = self.client.get(self._archive_url() + "&type=anime")
        self.assertContains(response, "Filtered Anime")
        self.assertNotContains(response, "Filtered Movie")

    @patch("app.providers.services.get_media_metadata")
    def test_archive_shows_all_items_not_capped(self, mock_metadata):
        """Full archive page shows all items, not just 20."""
        mock_metadata.return_value = {"max_progress": None}
        for i in range(25):
            item = Item.objects.create(
                media_id=f"3{i:03d}",
                source=Sources.TMDB.value,
                media_type=MediaTypes.MOVIE.value,
                title=f"Archive Movie {i}",
                image="http://example.com/image.jpg",
            )
            Movie.objects.create(
                item=item,
                user=self.user,
                status=Status.COMPLETED.value,
            )

        response = self.client.get(self._archive_url())
        self.assertEqual(len(response.context["archive"]), 25)

    def test_archive_type_filter_chip_links_preserve_view(self):
        """Type filter chips on archive page keep view=archive in URL."""
        response = self.client.get(self._archive_url())
        self.assertContains(response, "?view=archive&type=all")
