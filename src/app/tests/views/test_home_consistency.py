from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app.models import Anime, MediaTypes, Movie, Sources, Status
from app.tests.views._home_helpers import backlog_save_data, create_item
from app.tests.views.test_home import _flatten_group_titles
from events.models import Event


class HomeViewConsistencyTests(TestCase):
    """Test that HTMX partial responses match full page reloads."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    # --- quick_complete consistency ---

    @patch("app.providers.services.get_media_metadata")
    def test_quick_complete_item_leaves_backlog_on_reload(self, mock_metadata):
        """Completing an item removes it from backlog groups on reload."""
        mock_metadata.return_value = {"max_progress": None}
        item = create_item(
            "1000", Sources.TMDB.value, MediaTypes.MOVIE.value, "Will Complete"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        self.client.post(
            reverse("quick_complete"),
            {"media_type": "movie", "instance_id": movie.id},
        )

        page = self.client.get(reverse("home"))
        titles = _flatten_group_titles(page.context["groups"])
        self.assertNotIn("Will Complete", titles)

    @patch("app.providers.services.get_media_metadata")
    def test_quick_complete_item_in_archive_on_reload(self, mock_metadata):
        """Completed item appears in archive on reload."""
        mock_metadata.return_value = {"max_progress": None}
        item = create_item(
            "1001", Sources.TMDB.value, MediaTypes.MOVIE.value, "Archive Me"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        self.client.post(
            reverse("quick_complete"),
            {"media_type": "movie", "instance_id": movie.id},
        )

        page = self.client.get(reverse("home"))
        archive_titles = [m.item.title for m in page.context["archive"]]
        self.assertIn("Archive Me", archive_titles)

    @patch("app.providers.services.get_media_metadata")
    def test_quick_complete_sequential_archive_count(self, mock_metadata):
        """Two quick_completes in a row: final OOB count matches reload."""
        mock_metadata.return_value = {"max_progress": None}
        movies = []
        for mid in ["1010", "1011"]:
            item = create_item(
                mid, Sources.TMDB.value, MediaTypes.MOVIE.value, f"Seq Movie {mid}"
            )
            movies.append(
                Movie.objects.create(
                    item=item,
                    user=self.user,
                    status=Status.IN_PROGRESS.value,
                )
            )

        self.client.post(
            reverse("quick_complete"),
            {"media_type": "movie", "instance_id": movies[0].id},
        )

        response = self.client.post(
            reverse("quick_complete"),
            {"media_type": "movie", "instance_id": movies[1].id},
        )
        oob_count = int(
            response.content.decode()
            .split('id="archive-count"')[1]
            .split("(")[1]
            .split(")")[0]
        )

        page = self.client.get(reverse("home"))
        self.assertEqual(oob_count, page.context["archive_count"])

    # --- quick_drop consistency ---

    def test_quick_drop_absent_from_backlog_and_archive_on_reload(self):
        """Dropped item appears in neither backlog nor archive on reload."""
        item = create_item(
            "1020", Sources.TMDB.value, MediaTypes.MOVIE.value, "Drop Me Fully"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        self.client.post(
            reverse("quick_drop"),
            {"media_type": "movie", "instance_id": movie.id},
        )

        page = self.client.get(reverse("home"))
        backlog_titles = _flatten_group_titles(page.context["groups"])
        archive_titles = [m.item.title for m in page.context["archive"]]
        self.assertNotIn("Drop Me Fully", backlog_titles)
        self.assertNotIn("Drop Me Fully", archive_titles)

    # --- quick_status_transition consistency ---

    def test_quick_start_item_moves_to_in_progress_on_reload(self):
        """Started item appears in In Progress group on reload."""
        item = create_item(
            "1050", Sources.TMDB.value, MediaTypes.MOVIE.value, "Start Me"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        self.client.post(
            reverse("quick_status_transition"),
            {
                "media_type": "movie",
                "instance_id": movie.id,
                "target_status": "In progress",
            },
        )

        page = self.client.get(reverse("home"))
        groups = page.context["groups"]
        for group in groups:
            for sg in group["status_groups"]:
                titles = [m.item.title for m in sg["items"]]
                if "Start Me" in titles:
                    self.assertEqual(sg["status"], Status.IN_PROGRESS.value)
                    return
        self.fail("'Start Me' not found in any backlog group")

    def test_quick_plan_item_moves_to_planning_on_reload(self):
        """Planned item appears in Planning group on reload."""
        item = create_item(
            "1051", Sources.TMDB.value, MediaTypes.MOVIE.value, "Plan Me"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PAUSED.value
        )

        self.client.post(
            reverse("quick_status_transition"),
            {
                "media_type": "movie",
                "instance_id": movie.id,
                "target_status": "Planning",
            },
        )

        page = self.client.get(reverse("home"))
        groups = page.context["groups"]
        for group in groups:
            for sg in group["status_groups"]:
                titles = [m.item.title for m in sg["items"]]
                if "Plan Me" in titles:
                    self.assertEqual(sg["status"], Status.PLANNING.value)
                    return
        self.fail("'Plan Me' not found in any backlog group")

    def test_quick_start_sets_start_date_on_reload(self):
        """Started item has start_date set on reload."""
        item = create_item(
            "1052", Sources.TMDB.value, MediaTypes.MOVIE.value, "Start Date Check"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        self.client.post(
            reverse("quick_status_transition"),
            {
                "media_type": "movie",
                "instance_id": movie.id,
                "target_status": "In progress",
            },
        )

        movie.refresh_from_db()
        self.assertIsNotNone(movie.start_date)

    # --- quick_catch_up consistency ---

    @patch("app.providers.services.get_media_metadata")
    def test_quick_catch_up_state_matches_reload(self, mock_metadata):
        """After catch_up, response and reload both show 'Caught Up'."""
        mock_metadata.return_value = {"max_progress": 24}
        anime_item = create_item(
            "1030", Sources.MAL.value, MediaTypes.ANIME.value, "Catch Up Consistency"
        )
        anime = Anime.objects.create(
            item=anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=5,
        )
        Event.objects.create(
            item=anime_item,
            content_number=11,
            datetime=timezone.now() + timedelta(days=2),
        )

        response = self.client.post(
            reverse("quick_catch_up"),
            {"media_type": "anime", "instance_id": anime.id},
        )

        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "Caught Up?")

        page = self.client.get(reverse("home") + "?type=anime")
        self.assertContains(page, "Caught Up")
        self.assertNotContains(page, "Caught Up?")

        anime.refresh_from_db()
        self.assertEqual(anime.progress, 10)

    # --- backlog_save field persistence ---

    @patch("app.providers.services.get_media_metadata")
    def test_backlog_save_score_persists_on_reload(self, mock_metadata):
        """Score saved via inline edit appears on page reload."""
        mock_metadata.return_value = {"max_progress": None}
        item = create_item(
            "1040", Sources.TMDB.value, MediaTypes.MOVIE.value, "Score Persist Movie"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        data = backlog_save_data(movie)
        data["score"] = "8.5"
        self.client.post(reverse("backlog_save"), data)

        movie.refresh_from_db()
        self.assertEqual(float(movie.score), 8.5)

        page = self.client.get(reverse("home"))
        self.assertContains(page, "8.5")

    @patch("app.providers.services.get_media_metadata")
    def test_backlog_save_notes_persist_on_reload(self, mock_metadata):
        """Notes saved via inline edit appear on page reload."""
        mock_metadata.return_value = {"max_progress": None}
        item = create_item(
            "1041", Sources.TMDB.value, MediaTypes.MOVIE.value, "Notes Persist Movie"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        data = backlog_save_data(movie)
        data["notes"] = "Great movie so far"
        self.client.post(reverse("backlog_save"), data)

        movie.refresh_from_db()
        self.assertEqual(movie.notes, "Great movie so far")

    @patch("app.providers.services.get_media_metadata")
    def test_backlog_save_link_persists_on_reload(self, mock_metadata):
        """Link saved via inline edit persists in DB."""
        mock_metadata.return_value = {"max_progress": None}
        item = create_item(
            "1042", Sources.TMDB.value, MediaTypes.MOVIE.value, "Link Persist Movie"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        data = backlog_save_data(movie)
        data["link"] = "https://example.com/watch"
        self.client.post(reverse("backlog_save"), data)

        movie.refresh_from_db()
        self.assertEqual(movie.link, "https://example.com/watch")

        page = self.client.get(reverse("home"))
        self.assertContains(page, "https://example.com/watch")

    # --- backlog_save status transitions on reload ---

    @patch("app.providers.services.get_media_metadata")
    def test_backlog_save_complete_in_archive_on_reload(self, mock_metadata):
        """Completing via inline edit puts item in archive on reload."""
        mock_metadata.return_value = {"max_progress": None}
        item = create_item(
            "1050b", Sources.TMDB.value, MediaTypes.MOVIE.value, "Save Complete Movie"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        data = backlog_save_data(movie)
        data["status"] = Status.COMPLETED.value
        self.client.post(reverse("backlog_save"), data)

        page = self.client.get(reverse("home"))
        backlog_titles = _flatten_group_titles(page.context["groups"])
        archive_titles = [m.item.title for m in page.context["archive"]]
        self.assertNotIn("Save Complete Movie", backlog_titles)
        self.assertIn("Save Complete Movie", archive_titles)

    def test_backlog_save_drop_gone_on_reload(self):
        """Dropping via inline edit removes item from everything on reload."""
        item = create_item(
            "1051b", Sources.TMDB.value, MediaTypes.MOVIE.value, "Save Drop Movie"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        data = backlog_save_data(movie)
        data["status"] = Status.DROPPED.value
        self.client.post(reverse("backlog_save"), data)

        page = self.client.get(reverse("home"))
        backlog_titles = _flatten_group_titles(page.context["groups"])
        archive_titles = [m.item.title for m in page.context["archive"]]
        self.assertNotIn("Save Drop Movie", backlog_titles)
        self.assertNotIn("Save Drop Movie", archive_titles)

    def test_backlog_save_status_change_correct_group_on_reload(self):
        """Changing status via inline edit places item in correct group on reload."""
        item = create_item(
            "1052b", Sources.TMDB.value, MediaTypes.MOVIE.value, "Regroup Movie"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        data = backlog_save_data(movie)
        data["status"] = Status.IN_PROGRESS.value
        self.client.post(reverse("backlog_save"), data)

        page = self.client.get(reverse("home") + "?type=movie")
        groups = page.context["groups"]
        for group in groups:
            for sg in group["status_groups"]:
                titles = [m.item.title for m in sg["items"]]
                if "Regroup Movie" in titles:
                    self.assertEqual(sg["status"], Status.IN_PROGRESS.value)
                    return
        self.fail("Regroup Movie not found in any status group")

    def test_backlog_save_paused_correct_group_on_reload(self):
        """Pausing via inline edit places item in Paused group on reload."""
        item = create_item(
            "1053", Sources.MAL.value, MediaTypes.ANIME.value, "Pause Me Anime"
        )
        anime = Anime.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        data = backlog_save_data(anime)
        data["status"] = Status.PAUSED.value
        self.client.post(reverse("backlog_save"), data)

        page = self.client.get(reverse("home") + "?type=anime")
        groups = page.context["groups"]
        for group in groups:
            for sg in group["status_groups"]:
                titles = [m.item.title for m in sg["items"]]
                if "Pause Me Anime" in titles:
                    self.assertEqual(sg["status"], Status.PAUSED.value)
                    return
        self.fail("Pause Me Anime not found in any status group")

    # --- quick_rewatch consistency ---

    @patch("app.providers.services.get_media_metadata")
    def test_quick_rewatch_creates_planning_in_backlog_on_reload(self, mock_metadata):
        """Rewatching from archive creates a Planning item in backlog on reload."""
        mock_metadata.return_value = {"max_progress": None}
        item = create_item(
            "1060", Sources.TMDB.value, MediaTypes.MOVIE.value, "Rewatch Target"
        )
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)

        self.client.post(
            reverse("quick_rewatch"),
            {
                "media_id": "1060",
                "source": Sources.TMDB.value,
                "media_type": "movie",
                "source_context": "archive",
            },
        )

        page = self.client.get(reverse("home") + "?type=movie")
        groups = page.context["groups"]
        for group in groups:
            for sg in group["status_groups"]:
                titles = [m.item.title for m in sg["items"]]
                if "Rewatch Target" in titles:
                    self.assertEqual(sg["status"], Status.PLANNING.value)
                    return
        self.fail("Rewatch Target not found in backlog after rewatch")

    @patch("app.providers.services.get_media_metadata")
    def test_quick_rewatch_does_not_duplicate_if_active_exists(self, mock_metadata):
        """Rewatching when an active instance exists doesn't create a new one."""
        mock_metadata.return_value = {"max_progress": None}
        item = create_item(
            "1061", Sources.TMDB.value, MediaTypes.MOVIE.value, "Already Active Movie"
        )
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)
        Movie.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        count_before = Movie.objects.filter(user=self.user, item=item).count()

        self.client.post(
            reverse("quick_rewatch"),
            {
                "media_id": "1061",
                "source": Sources.TMDB.value,
                "media_type": "movie",
                "source_context": "archive",
            },
        )

        count_after = Movie.objects.filter(user=self.user, item=item).count()
        self.assertEqual(count_after, count_before)

    # --- Full lifecycle consistency ---

    @patch("app.providers.services.get_media_metadata")
    def test_complete_then_rewatch_lifecycle(self, mock_metadata):
        """Complete -> rewatch -> verify backlog and archive are both correct."""
        mock_metadata.return_value = {"max_progress": None}
        item = create_item(
            "1070", Sources.TMDB.value, MediaTypes.MOVIE.value, "Lifecycle Movie"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        self.client.post(
            reverse("quick_complete"),
            {"media_type": "movie", "instance_id": movie.id},
        )

        mid_page = self.client.get(reverse("home"))
        self.assertNotIn(
            "Lifecycle Movie",
            _flatten_group_titles(mid_page.context["groups"]),
        )

        self.client.post(
            reverse("quick_rewatch"),
            {
                "media_id": "1070",
                "source": Sources.TMDB.value,
                "media_type": "movie",
                "source_context": "archive",
            },
        )

        final_page = self.client.get(reverse("home"))
        backlog_titles = _flatten_group_titles(final_page.context["groups"])
        self.assertIn("Lifecycle Movie", backlog_titles)

    @patch("app.providers.services.get_media_metadata")
    def test_complete_rewatch_complete_archive_count(self, mock_metadata):
        """Complete -> rewatch -> complete again: archive count increases by 1."""
        mock_metadata.return_value = {"max_progress": None}
        item = create_item(
            "1071", Sources.TMDB.value, MediaTypes.MOVIE.value, "Double Complete Movie"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        self.client.post(
            reverse("quick_complete"),
            {"media_type": "movie", "instance_id": movie.id},
        )

        page_after_first = self.client.get(reverse("home"))
        count_after_first = page_after_first.context["archive_count"]

        self.client.post(
            reverse("quick_rewatch"),
            {
                "media_id": "1071",
                "source": Sources.TMDB.value,
                "media_type": "movie",
                "source_context": "archive",
            },
        )

        page_mid = self.client.get(reverse("home"))
        count_mid = page_mid.context["archive_count"]
        self.assertEqual(
            count_mid,
            count_after_first - 1,
            "Rewatch makes newest instance Planning, removing from archive",
        )

        rewatch = Movie.objects.filter(
            user=self.user, item=item, status=Status.PLANNING.value
        ).first()
        self.client.post(
            reverse("quick_complete"),
            {"media_type": "movie", "instance_id": rewatch.id},
        )

        page_final = self.client.get(reverse("home"))
        count_final = page_final.context["archive_count"]
        self.assertEqual(count_final, count_after_first)

    # --- Card content consistency ---

    @patch("app.providers.services.get_media_metadata")
    def test_backlog_save_response_shows_updated_score(self, mock_metadata):
        """The HTMX card response includes the updated score value."""
        mock_metadata.return_value = {"max_progress": None}
        item = create_item(
            "1080", Sources.TMDB.value, MediaTypes.MOVIE.value, "Score Response Movie"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        data = backlog_save_data(movie)
        data["score"] = "7.5"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertContains(response, "7.5")

    @patch("app.providers.services.get_media_metadata")
    def test_backlog_save_response_shows_updated_link(self, mock_metadata):
        """The HTMX card response includes the external link icon when saved."""
        mock_metadata.return_value = {"max_progress": None}
        item = create_item(
            "1081", Sources.TMDB.value, MediaTypes.MOVIE.value, "Link Response Movie"
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        data = backlog_save_data(movie)
        data["link"] = "https://example.com/stream"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertContains(response, "https://example.com/stream")

    @patch("app.providers.services.get_media_metadata")
    def test_backlog_save_progress_response_matches_reload(self, mock_metadata):
        """Progress value in HTMX response matches page reload."""
        mock_metadata.return_value = {"max_progress": 24}
        item = create_item(
            "1082",
            Sources.MAL.value,
            MediaTypes.ANIME.value,
            "Progress Consistency Anime",
        )
        anime = Anime.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=3,
        )

        data = backlog_save_data(anime)
        data["progress"] = "7"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertContains(response, 'value="7"')

        anime.refresh_from_db()
        self.assertEqual(anime.progress, 7)
