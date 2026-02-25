import re
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from app.helpers import enrich_items_with_user_data
from app.models import (
    TV,
    Anime,
    Episode,
    Item,
    Manga,
    MediaTypes,
    Movie,
    Season,
    Sources,
    Status,
)
from app.providers.mal import get_english_title
from app.urls import urlpatterns
from events.models import Event
from users.models import HomeSortChoices

TESTED_BACKLOG_ACTIONS = {
    "quick_add",
    "quick_archive",
    "quick_complete",
    "quick_drop",
    "quick_catch_up",
    "quick_rewatch",
    "quick_status_transition",
    "backlog_save",
}


def _flatten_group_titles(groups):
    """Extract all item titles from grouped backlog structure."""
    titles = []
    for group in groups:
        for sg in group["status_groups"]:
            titles.extend(m.item.title for m in sg["items"])
    return titles


class HomeViewTests(TestCase):
    """Test the home view."""

    @classmethod
    def setUpTestData(cls):
        """Create a user and test data."""
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        season_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test TV Show",
            image="http://example.com/image.jpg",
            season_number=1,
        )
        season = Season.objects.create(
            item=season_item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
        )

        for i in range(1, 6):
            episode_item = Item.objects.create(
                media_id="1668",
                source=Sources.TMDB.value,
                media_type=MediaTypes.EPISODE.value,
                title="Test TV Show",
                image="http://example.com/image.jpg",
                season_number=1,
                episode_number=i,
            )
            Episode.objects.create(
                item=episode_item,
                related_season=season,
                end_date=timezone.now() - timezone.timedelta(days=i),
            )

        anime_item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Test Anime",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
            item=anime_item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
            progress=10,
        )

    def setUp(self):
        self.client.login(**self.credentials)

    def test_home_view(self):
        """Test that backlog shows grouped Planning and In Progress items."""
        planning_item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Planning Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=planning_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/home.html")

        self.assertIn("groups", response.context)
        self.assertIn("archive", response.context)
        self.assertIn("sort_choices", response.context)
        self.assertEqual(response.context["sort_choices"], HomeSortChoices.choices)

        titles = _flatten_group_titles(response.context["groups"])
        self.assertIn("Test Anime", titles)
        self.assertIn("Planning Movie", titles)

    def test_xdata_attributes_no_newlines_in_js_strings(self):
        """Rendered x-data attributes must not contain newlines inside JS strings."""
        response = self.client.get(reverse("home"))
        html = response.content.decode()

        xdata_pattern = re.compile(r'x-data="([^"]*)"', re.DOTALL)
        for match in xdata_pattern.finditer(html):
            expr = match.group(1)
            in_string = False
            quote_char = None
            for char in expr:
                if in_string:
                    if char == quote_char:
                        in_string = False
                    elif char == "\n":
                        start = max(0, expr.index(quote_char) - 20)
                        end = expr.index(quote_char) + 40
                        self.fail(
                            "Newline inside JS string in x-data: "
                            f"...{expr[start:end]}..."
                        )
                elif char in ("'", '"'):
                    in_string = True
                    quote_char = char

    def test_home_view_with_sort(self):
        """Test the home view with sorting parameter."""
        response = self.client.get(reverse("home") + "?sort=completion")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_sort"], "completion")

        self.user.refresh_from_db()
        self.assertEqual(self.user.home_sort, "completion")

    @patch("app.providers.services.get_media_metadata")
    def test_home_completed_in_archive(self, mock_metadata):
        """Test that completed items appear in archive, not in groups."""
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

        response = self.client.get(reverse("home"))

        group_titles = _flatten_group_titles(response.context["groups"])
        self.assertNotIn("Completed Movie", group_titles)

        archive_titles = [m.item.title for m in response.context["archive"]]
        self.assertIn("Completed Movie", archive_titles)

    def test_home_type_filter(self):
        """Test that type filter chips restrict results."""
        movie_item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.get(reverse("home") + "?type=anime")

        media_types_in_groups = {
            group["media_type"] for group in response.context["groups"]
        }
        self.assertNotIn(MediaTypes.MOVIE.value, media_types_in_groups)
        self.assertEqual(response.context["current_type_filter"], "anime")

    def test_home_status_group_order(self):
        """Test that status groups appear in fixed order."""
        paused_item = Item.objects.create(
            media_id="500",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Paused Anime",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
            item=paused_item,
            user=self.user,
            status=Status.PAUSED.value,
        )

        planning_item = Item.objects.create(
            media_id="501",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Planning Anime",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
            item=planning_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.get(reverse("home") + "?type=anime")

        groups = response.context["groups"]
        self.assertEqual(len(groups), 1)
        statuses = [sg["status"] for sg in groups[0]["status_groups"]]
        self.assertEqual(
            statuses,
            [Status.IN_PROGRESS.value, Status.PLANNING.value, Status.PAUSED.value],
        )

    def test_archive_opens_with_view_param(self):
        """Test that ?view=archive sets archive_open in context."""
        response = self.client.get(reverse("home") + "?view=archive")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context.get("archive_open"))

    def test_tv_show_appears_in_backlog(self):
        """Test that TV shows added via quick_add appear in the backlog."""
        tv_item = Item.objects.create(
            media_id="1399",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Breaking Bad",
            image="http://example.com/image.jpg",
        )
        TV.objects.create(
            item=tv_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.get(reverse("home"))
        titles = _flatten_group_titles(response.context["groups"])
        self.assertIn("Breaking Bad", titles)

    def test_tv_filter_includes_seasons(self):
        """Test that filtering by TV shows both TV and Season items."""
        tv_item = Item.objects.create(
            media_id="1399",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Breaking Bad",
            image="http://example.com/image.jpg",
        )
        TV.objects.create(
            item=tv_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.get(reverse("home") + "?type=tv")
        media_types_in_groups = {
            group["media_type"] for group in response.context["groups"]
        }
        self.assertIn(MediaTypes.TV.value, media_types_in_groups)
        self.assertIn(MediaTypes.SEASON.value, media_types_in_groups)

    def test_episodes_excluded_from_backlog(self):
        """Test that episode items do not appear as standalone backlog entries."""
        response = self.client.get(reverse("home"))
        media_types_in_groups = {
            group["media_type"] for group in response.context["groups"]
        }
        self.assertNotIn(MediaTypes.EPISODE.value, media_types_in_groups)

    def test_dropped_items_excluded_from_backlog(self):
        """Test that dropped items do not appear in backlog groups."""
        dropped_item = Item.objects.create(
            media_id="700",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Dropped Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=dropped_item,
            user=self.user,
            status=Status.DROPPED.value,
        )

        response = self.client.get(reverse("home"))
        titles = _flatten_group_titles(response.context["groups"])
        self.assertNotIn("Dropped Movie", titles)

        archive_titles = [m.item.title for m in response.context["archive"]]
        self.assertNotIn("Dropped Movie", archive_titles)

    @patch("app.providers.services.get_media_metadata")
    def test_archive_deduplicates_rewatches(self, mock_metadata):
        """Test that rewatched media appears once in archive, not per instance."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="800",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Rewatched Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)

        response = self.client.get(reverse("home"))
        archive = response.context["archive"]
        archive_titles = [m.item.title for m in archive]
        self.assertEqual(archive_titles.count("Rewatched Movie"), 1)

    @patch("app.providers.services.get_media_metadata")
    def test_archive_count_after_quick_complete(self, mock_metadata):
        """Test that completing an item updates archive count correctly."""
        mock_metadata.return_value = {"max_progress": None}

        item = Item.objects.create(
            media_id="820",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Complete Me",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        # item with prior rewatches (count should still increase by exactly 1)
        rewatch_item = Item.objects.create(
            media_id="830",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Multi Rewatch Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=rewatch_item, user=self.user, status=Status.COMPLETED.value
        )
        Movie.objects.create(
            item=rewatch_item, user=self.user, status=Status.COMPLETED.value
        )

        page_before = self.client.get(reverse("home"))
        count_before = page_before.context["archive_count"]

        response = self.client.post(
            reverse("quick_complete"),
            {"media_type": "movie", "instance_id": movie.id},
        )
        oob_count = int(
            response.content.decode()
            .split('id="archive-count"')[1]
            .split("(")[1]
            .split(")")[0]
        )

        page_after = self.client.get(reverse("home"))
        count_after = page_after.context["archive_count"]

        self.assertEqual(oob_count, count_after)
        self.assertEqual(count_after, count_before + 1)

    @patch("app.providers.services.get_media_metadata")
    def test_archive_count_excludes_active_rewatches(self, mock_metadata):
        """Test that items with active rewatches aren't counted in archive."""
        mock_metadata.return_value = {"max_progress": None}

        # item with an active (non-completed) rewatch should not be in archive count
        item_a = Item.objects.create(
            media_id="860",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Active Rewatch Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=item_a, user=self.user, status=Status.COMPLETED.value
        )
        Movie.objects.create(
            item=item_a, user=self.user, status=Status.PLANNING.value
        )

        item_b = Item.objects.create(
            media_id="861",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Fresh Complete Movie",
            image="http://example.com/image.jpg",
        )
        movie_b = Movie.objects.create(
            item=item_b, user=self.user, status=Status.IN_PROGRESS.value
        )

        page_before = self.client.get(reverse("home"))
        count_before = page_before.context["archive_count"]

        # quick_complete: OOB count should match page and increase by 1
        response = self.client.post(
            reverse("quick_complete"),
            {"media_type": "movie", "instance_id": movie_b.id},
        )
        oob_count = int(
            response.content.decode()
            .split('id="archive-count"')[1]
            .split("(")[1]
            .split(")")[0]
        )

        page_after = self.client.get(reverse("home"))
        count_after = page_after.context["archive_count"]

        self.assertEqual(oob_count, count_after)
        self.assertEqual(count_after, count_before + 1)

        # backlog_save path: also excludes active rewatches
        item_c = Item.objects.create(
            media_id="871",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Complete Via Save",
            image="http://example.com/image.jpg",
        )
        movie_c = Movie.objects.create(
            item=item_c, user=self.user, status=Status.IN_PROGRESS.value
        )

        count_before_save = count_after

        data = self._backlog_save_data(movie_c)
        data["status"] = Status.COMPLETED.value
        response = self.client.post(reverse("backlog_save"), data)

        save_oob_count = int(
            response.content.decode()
            .split('id="archive-count"')[1]
            .split("(")[1]
            .split(")")[0]
        )

        page_final = self.client.get(reverse("home"))
        self.assertEqual(save_oob_count, page_final.context["archive_count"])
        self.assertEqual(
            page_final.context["archive_count"], count_before_save + 1
        )

    def test_ongoing_caught_up_when_progress_matches(self):
        """Test that caught-up users see 'Caught Up' (no question mark)."""
        anime_item = Item.objects.get(media_id="1", source=Sources.MAL.value)
        Event.objects.create(
            item=anime_item,
            content_number=11,
            datetime=timezone.now() + timedelta(days=2),
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "Caught Up?")

    @patch("app.providers.services.get_media_metadata")
    def test_ongoing_caught_up_uncertain_when_behind(self, mock_metadata):
        """Test that users behind on progress see 'Caught Up?' button."""
        mock_metadata.return_value = {"max_progress": 24}
        anime_item = Item.objects.create(
            media_id="2",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Behind Anime",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
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

        response = self.client.get(reverse("home") + "?type=anime")
        self.assertContains(response, "Caught Up?")
        self.assertContains(response, "quick_catch_up")

    @patch("app.providers.services.get_media_metadata")
    def test_quick_catch_up_updates_progress(self, mock_metadata):
        """Test that quick_catch_up sets progress to latest aired episode."""
        mock_metadata.return_value = {"max_progress": 24}
        anime_item = Item.objects.create(
            media_id="3",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Catch Up Anime",
            image="http://example.com/image.jpg",
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

        self.assertEqual(response.status_code, 200)
        anime.refresh_from_db()
        self.assertEqual(anime.progress, 10)
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "Caught Up?")

    def test_in_progress_item_shows_done(self):
        """Test that In Progress items with no future events show Done button."""
        movie_item = Item.objects.create(
            media_id="300",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="In Progress Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        response = self.client.get(reverse("home") + "?type=movie")
        self.assertContains(response, "quick_complete")

    def test_sentinel_event_shows_done(self):
        """Test that sentinel-date events don't suppress the Done button."""
        anime_item = Item.objects.get(media_id="1", source=Sources.MAL.value)
        Event.objects.create(
            item=anime_item,
            content_number=11,
            datetime=datetime(9999, 12, 31, 23, 59, 59, 999999, tzinfo=UTC),
        )

        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "quick_catch_up")
        self.assertContains(response, "quick_complete")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_manga_ongoing_shows_caught_up(self, _mock_releases, mock_metadata):
        """Test that ongoing manga with undated events shows Caught Up."""
        mock_metadata.return_value = {"max_progress": 100}
        manga_item = Item.objects.create(
            media_id="66296374554",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Ongoing Manga",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=50,
        )
        Event.objects.create(
            item=manga_item,
            content_number=50,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.get(reverse("home") + "?type=manga")
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "quick_complete")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_manga_ongoing_no_next_info(self, _mock_releases, mock_metadata):
        """Test that ongoing manga with undated events does not show Next: info."""
        mock_metadata.return_value = {"max_progress": 100}
        manga_item = Item.objects.create(
            media_id="66296374555",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Ongoing Manga No Next",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        Event.objects.create(
            item=manga_item,
            content_number=10,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.get(reverse("home") + "?type=manga")
        self.assertNotContains(response, "Next:")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_manga_no_events_shows_catch_up_button(self, _mock_releases, mock_metadata):
        """Test that manga with no events shows Caught Up? button."""
        mock_metadata.return_value = {"max_progress": None}
        manga_item = Item.objects.create(
            media_id="66296374556",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="No Events Manga",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        response = self.client.get(reverse("home") + "?type=manga")
        self.assertContains(response, "quick_catch_up")
        self.assertNotContains(response, "quick_complete")

    def test_season_ongoing_shows_caught_up(self):
        """Test that TV season with undated events shows Caught Up."""
        season_item = Item.objects.get(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
        )
        Event.objects.create(
            item=season_item,
            content_number=6,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.get(reverse("home") + "?type=tv")
        self.assertContains(response, "Caught Up")

    def test_anime_min_datetime_shows_caught_up(self):
        """Test that anime with datetime.min events shows Caught Up."""
        anime_item = Item.objects.get(media_id="1", source=Sources.MAL.value)
        Event.objects.create(
            item=anime_item,
            content_number=11,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.get(reverse("home") + "?type=anime")
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "quick_complete")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_paused_manga_no_caught_up(self, _mock_releases, mock_metadata):
        """Test that paused manga with events shows neither Caught Up nor Done."""
        mock_metadata.return_value = {"max_progress": 100}
        manga_item = Item.objects.create(
            media_id="66296374557",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Paused Manga",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.PAUSED.value,
        )
        Event.objects.create(
            item=manga_item,
            content_number=10,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.get(reverse("home") + "?type=manga")
        self.assertNotContains(response, "quick_catch_up")
        self.assertNotContains(response, "quick_complete")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_backlog_save_preserves_manga_caught_up(
        self, _mock_releases, mock_metadata
    ):
        """Test that saving ongoing manga preserves Caught Up badge."""
        mock_metadata.return_value = {"max_progress": 100}
        manga_item = Item.objects.create(
            media_id="66296374558",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Save Manga",
            image="http://example.com/image.jpg",
        )
        manga = Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=20,
        )
        Event.objects.create(
            item=manga_item,
            content_number=20,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.post(
            reverse("backlog_save"), self._backlog_save_data(manga)
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "quick_complete")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_mal_manga_ongoing_no_chapters_shows_catch_up_button(
        self, _mock_releases, mock_metadata
    ):
        """Test MAL manga with unknown chapters shows Caught Up? button."""
        mock_metadata.return_value = {"max_progress": None}
        manga_item = Item.objects.create(
            media_id="66296374559",
            source=Sources.MAL.value,
            media_type=MediaTypes.MANGA.value,
            title="MAL Ongoing Manga",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        Event.objects.create(
            item=manga_item,
            content_number=None,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.get(reverse("home") + "?type=manga")
        self.assertContains(response, "quick_catch_up")
        self.assertNotContains(response, "quick_complete")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_manga_caught_up_field_shows_badge(self, _mock_releases, mock_metadata):
        """Test that caught_up=True on model shows Caught Up badge."""
        mock_metadata.return_value = {"max_progress": None}
        manga_item = Item.objects.create(
            media_id="66296374570",
            source=Sources.MAL.value,
            media_type=MediaTypes.MANGA.value,
            title="Manual Caught Up Manga",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            caught_up=True,
        )

        response = self.client.get(reverse("home") + "?type=manga")
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "quick_catch_up")
        self.assertNotContains(response, "quick_complete")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_quick_catch_up_unknown_progress_sets_caught_up(
        self, _mock_releases, mock_metadata
    ):
        """Test quick_catch_up sets caught_up=True when max_progress unknown."""
        mock_metadata.return_value = {"max_progress": None}
        manga_item = Item.objects.create(
            media_id="66296374571",
            source=Sources.MAL.value,
            media_type=MediaTypes.MANGA.value,
            title="Unknown Progress Manga",
            image="http://example.com/image.jpg",
        )
        manga = Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        Event.objects.create(
            item=manga_item,
            content_number=None,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.post(
            reverse("quick_catch_up"),
            {
                "media_type": MediaTypes.MANGA.value,
                "instance_id": manga.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        manga.refresh_from_db()
        self.assertTrue(manga.caught_up)
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "quick_catch_up")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_manga_ongoing_behind_shows_catch_up_button(
        self, _mock_releases, mock_metadata
    ):
        """Test ongoing manga where user is behind shows Caught Up? button."""
        mock_metadata.return_value = {"max_progress": 100}
        manga_item = Item.objects.create(
            media_id="66296374560",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Behind Manga",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=20,
        )
        Event.objects.create(
            item=manga_item,
            content_number=50,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.get(reverse("home") + "?type=manga")
        self.assertContains(response, "quick_catch_up")
        self.assertNotContains(response, "quick_complete")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_manga_ongoing_zero_progress_shows_catch_up_button(
        self, _mock_releases, mock_metadata
    ):
        """Test ongoing manga at progress 0 shows Caught Up? button."""
        mock_metadata.return_value = {"max_progress": 100}
        manga_item = Item.objects.create(
            media_id="66296374561",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Zero Progress Manga",
            image="http://example.com/image.jpg",
        )
        Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=0,
        )
        Event.objects.create(
            item=manga_item,
            content_number=30,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.get(reverse("home") + "?type=manga")
        self.assertContains(response, "quick_catch_up")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_quick_catch_up_ongoing_manga(self, _mock_releases, mock_metadata):
        """Test quick_catch_up sets progress to max_progress for ongoing."""
        mock_metadata.return_value = {"max_progress": 100}
        manga_item = Item.objects.create(
            media_id="66296374562",
            source=Sources.MANGAUPDATES.value,
            media_type=MediaTypes.MANGA.value,
            title="Catch Up Manga",
            image="http://example.com/image.jpg",
        )
        manga = Manga.objects.create(
            item=manga_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=10,
        )
        Event.objects.create(
            item=manga_item,
            content_number=50,
            datetime=datetime.min.replace(tzinfo=UTC),
        )

        response = self.client.post(
            reverse("quick_catch_up"),
            {
                "media_type": MediaTypes.MANGA.value,
                "instance_id": manga.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        manga.refresh_from_db()
        self.assertEqual(manga.progress, 50)
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "quick_catch_up")

    def test_planning_item_no_done_button(self):
        """Test that Planning items don't show a Done button."""
        movie_item = Item.objects.create(
            media_id="400",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Planning Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.get(reverse("home") + "?type=movie")
        self.assertNotContains(response, "quick_complete")

    def test_quick_drop(self):
        """Test that quick_drop sets status to Dropped and removes card."""
        movie_item = Item.objects.create(
            media_id="401",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Movie To Drop",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.post(
            reverse("quick_drop"),
            {"media_type": "movie", "instance_id": movie.id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dropped")
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.DROPPED.value)

        response = self.client.get(reverse("home"))
        titles = _flatten_group_titles(response.context["groups"])
        self.assertNotIn("Movie To Drop", titles)

    def test_drop_uses_inline_confirmation_not_browser_confirm(self):
        """Test that drop button uses inline confirmation instead of hx-confirm."""
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "hx-confirm")
        self.assertContains(response, "confirmDrop")
        self.assertContains(response, "Drop this?")

    def test_quick_start_planning_to_in_progress(self):
        """Test that quick_status_transition moves Planning to In Progress."""
        item = Item.objects.create(
            media_id="501",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Movie To Start",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.post(
            reverse("quick_status_transition"),
            {
                "media_type": "movie",
                "instance_id": movie.id,
                "target_status": "In progress",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Refresh"], "true")
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.IN_PROGRESS.value)
        self.assertIsNotNone(movie.start_date)

    def test_quick_plan_paused_to_planning(self):
        """Test that quick_status_transition moves Paused to Planning."""
        item = Item.objects.create(
            media_id="502",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Movie To Plan",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.PAUSED.value,
        )

        response = self.client.post(
            reverse("quick_status_transition"),
            {
                "media_type": "movie",
                "instance_id": movie.id,
                "target_status": "Planning",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["HX-Refresh"], "true")
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.PLANNING.value)

    def test_quick_status_transition_invalid_source_status(self):
        """Test that In Progress items cannot use quick_status_transition."""
        item = Item.objects.create(
            media_id="503",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="In Progress Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        response = self.client.post(
            reverse("quick_status_transition"),
            {
                "media_type": "movie",
                "instance_id": movie.id,
                "target_status": "Planning",
            },
        )

        self.assertEqual(response.status_code, 400)
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.IN_PROGRESS.value)

    def test_quick_status_transition_wrong_target(self):
        """Test that Planning cannot transition to Completed."""
        item = Item.objects.create(
            media_id="504",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Planning Movie Wrong Target",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.post(
            reverse("quick_status_transition"),
            {
                "media_type": "movie",
                "instance_id": movie.id,
                "target_status": "Completed",
            },
        )

        self.assertEqual(response.status_code, 400)
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.PLANNING.value)

    def test_start_button_on_planning_card(self):
        """Test that Planning cards show the Start button."""
        Item.objects.create(
            media_id="505",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Planning Card Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=Item.objects.get(media_id="505"),
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.get(reverse("home"))
        content = response.content.decode()
        self.assertIn("Start", content)
        self.assertIn("quick_status_transition", content)

    def test_plan_button_on_paused_card(self):
        """Test that Paused cards show the Plan button."""
        Item.objects.create(
            media_id="506",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Paused Card Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=Item.objects.get(media_id="506"),
            user=self.user,
            status=Status.PAUSED.value,
        )

        response = self.client.get(reverse("home"))
        content = response.content.decode()
        self.assertIn("Plan", content)
        self.assertIn("quick_status_transition", content)

    def test_no_transition_button_on_in_progress_card(self):
        """Test that In Progress cards don't show Start or Plan buttons."""
        response = self.client.get(reverse("home"))
        content = response.content.decode()
        self.assertNotIn("quick_status_transition", content)

    def test_next_event_info_displayed(self):
        """Test that next event info appears on ongoing backlog cards."""
        anime_item = Item.objects.get(media_id="1", source=Sources.MAL.value)
        Event.objects.create(
            item=anime_item,
            content_number=11,
            datetime=timezone.now() + timedelta(days=1),
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, "Next:")
        self.assertContains(response, "11")

    def _backlog_save_data(self, media):
        """Build POST data for backlog_save from a media instance."""
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
        }

    def test_backlog_save_preserves_caught_up(self):
        """Test that saving an ongoing In Progress item still shows Caught Up."""
        anime_item = Item.objects.get(media_id="1", source=Sources.MAL.value)
        anime = Anime.objects.get(item=anime_item, user=self.user)
        Event.objects.create(
            item=anime_item,
            content_number=11,
            datetime=timezone.now() + timedelta(days=2),
        )

        response = self.client.post(
            reverse("backlog_save"), self._backlog_save_data(anime)
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "quick_complete")

    def test_backlog_save_preserves_next_event_info(self):
        """Test that saving preserves the next event info line."""
        anime_item = Item.objects.get(media_id="1", source=Sources.MAL.value)
        anime = Anime.objects.get(item=anime_item, user=self.user)
        Event.objects.create(
            item=anime_item,
            content_number=11,
            datetime=timezone.now() + timedelta(days=2),
        )

        response = self.client.post(
            reverse("backlog_save"), self._backlog_save_data(anime)
        )

        self.assertContains(response, "Next:")

    @patch("app.providers.services.get_media_metadata")
    def test_backlog_save_complete_moves_to_archive(self, mock_metadata):
        """Test that saving with Completed status returns archive response."""
        mock_metadata.return_value = {"max_progress": None}
        movie_item = Item.objects.create(
            media_id="900",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Movie To Complete",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        data = self._backlog_save_data(movie)
        data["status"] = Status.COMPLETED.value
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/backlog_completed.html")
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.COMPLETED.value)

    def test_backlog_save_drop_removes_card(self):
        """Test that saving with Dropped status returns dropped response."""
        movie_item = Item.objects.create(
            media_id="901",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Movie To Drop Via Save",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        data = self._backlog_save_data(movie)
        data["status"] = Status.DROPPED.value
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/backlog_dropped.html")
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.DROPPED.value)

    def test_backlog_save_in_progress_no_events_shows_done(self):
        """Test that saving keeps Done button for In Progress items without events."""
        movie_item = Item.objects.create(
            media_id="902",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="IP Movie No Events",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        response = self.client.post(
            reverse("backlog_save"), self._backlog_save_data(movie)
        )

        self.assertContains(response, "quick_complete")

    def test_backlog_save_planning_no_done_button(self):
        """Test that saving a Planning item does not show Done button."""
        movie_item = Item.objects.create(
            media_id="903",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Planning Movie Save",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.post(
            reverse("backlog_save"), self._backlog_save_data(movie)
        )

        self.assertNotContains(response, "quick_complete")
        self.assertNotContains(response, "quick_catch_up")

    def test_backlog_save_status_change_triggers_refresh(self):
        """Test that changing status via inline edit triggers a page refresh."""
        movie_item = Item.objects.create(
            media_id="904",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Was Planning Now IP",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        data = self._backlog_save_data(movie)
        data["status"] = Status.IN_PROGRESS.value
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response["HX-Refresh"], "true")
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.IN_PROGRESS.value)

    def test_backlog_save_same_status_no_refresh(self):
        """Test that saving without status change does not trigger a refresh."""
        movie_item = Item.objects.create(
            media_id="906",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Same Status Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        data = self._backlog_save_data(movie)
        data["score"] = "8.5"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertNotIn("HX-Refresh", response)
        self.assertTemplateUsed(response, "app/components/backlog_card.html")

    def test_backlog_save_in_progress_to_paused_triggers_refresh(self):
        """Test that In Progress to Paused triggers refresh to regroup."""
        anime_item = Item.objects.create(
            media_id="907",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="IP to Paused Anime",
            image="http://example.com/image.jpg",
        )
        anime = Anime.objects.create(
            item=anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        data = self._backlog_save_data(anime)
        data["status"] = Status.PAUSED.value
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response["HX-Refresh"], "true")
        anime.refresh_from_db()
        self.assertEqual(anime.status, Status.PAUSED.value)

    def test_backlog_save_paused_no_done_button(self):
        """Test that saving a Paused item does not show Done button."""
        anime_item = Item.objects.create(
            media_id="905",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Paused Anime Save",
            image="http://example.com/image.jpg",
        )
        anime = Anime.objects.create(
            item=anime_item,
            user=self.user,
            status=Status.PAUSED.value,
        )

        response = self.client.post(
            reverse("backlog_save"), self._backlog_save_data(anime)
        )

        self.assertNotContains(response, "quick_complete")
        self.assertNotContains(response, "quick_catch_up")


class RewatchSectionTests(TestCase):
    """Tests for the Rewatches section in the backlog."""

    @classmethod
    def setUpTestData(cls):  # noqa: D102
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def _backlog_save_data(self, media):
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
        }

    @patch("app.providers.services.get_media_metadata")
    def test_rewatch_in_dedicated_section_all_mode(self, mock_metadata):
        """Rewatch items appear in a Rewatches group, not in type groups."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="5000",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Rewatch Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)
        Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value, is_rewatch=True
        )

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        type_titles = []
        rewatch_titles = []
        for group in groups:
            for sg in group["status_groups"]:
                for m in sg["items"]:
                    if group["media_type"] == "rewatch":
                        rewatch_titles.append(m.item.title)
                    else:
                        type_titles.append(m.item.title)

        self.assertIn("Rewatch Movie", rewatch_titles)
        self.assertNotIn("Rewatch Movie", type_titles)

    def test_rewatch_inline_in_type_filter(self):
        """Rewatch items appear in type group when filtering by type."""
        item = Item.objects.create(
            media_id="5001",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Rewatch Anime",
            image="http://example.com/image.jpg",
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
        item = Item.objects.create(
            media_id="5002",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Normal Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]
        media_types = {g["media_type"] for g in groups}
        self.assertNotIn("rewatch", media_types)
        self.assertNotContains(response, "Rewatches")

    def test_rewatch_manual_flag_no_history(self):
        """Single instance with is_rewatch=True appears in Rewatches group."""
        item = Item.objects.create(
            media_id="5003",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Manual Rewatch",
            image="http://example.com/image.jpg",
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
        item = Item.objects.create(
            media_id="5004",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Quick Rewatch Movie",
            image="http://example.com/image.jpg",
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
        item = Item.objects.create(
            media_id="5005",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Toggle Rewatch",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        data = self._backlog_save_data(movie)
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
            item = Item.objects.create(
                media_id=mid,
                source=Sources.TMDB.value,
                media_type=MediaTypes.MOVIE.value,
                title=f"Rewatch {status}",
                image="http://example.com/image.jpg",
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
        item = Item.objects.create(
            media_id="5030",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Refresh Toggle Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        data = self._backlog_save_data(movie)
        data["is_rewatch"] = "on"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response["HX-Refresh"], "true")

    def test_backlog_save_rewatch_untoggle_triggers_refresh(self):
        """Toggling is_rewatch off via backlog_save triggers HX-Refresh."""
        item = Item.objects.create(
            media_id="5031",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Unrefresh Toggle Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value, is_rewatch=True
        )

        data = self._backlog_save_data(movie)
        # checkbox unchecked = field absent from POST
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response["HX-Refresh"], "true")

    @patch("app.providers.services.get_media_metadata")
    def test_backlog_save_rewatch_unchanged_no_refresh(self, mock_metadata):
        """Saving without changing is_rewatch does not trigger HX-Refresh."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="5032",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="No Refresh Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        data = self._backlog_save_data(movie)
        data["score"] = "8.0"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertNotIn("HX-Refresh", response)

    def test_archive_save_rewatch_toggle_triggers_refresh(self):
        """Toggling is_rewatch on archive card triggers HX-Refresh."""
        item = Item.objects.create(
            media_id="5033",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Archive Rewatch Toggle",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.COMPLETED.value
        )

        data = self._backlog_save_data(movie)
        data["source_context"] = "archive"
        data["is_rewatch"] = "on"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response["HX-Refresh"], "true")

    def test_rewatch_toggle_moves_item_on_reload(self):
        """Toggling is_rewatch moves item to Rewatches group on reload."""
        item = Item.objects.create(
            media_id="5034",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Move To Rewatch",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        page_before = self.client.get(reverse("home"))
        groups_before = page_before.context["groups"]
        rewatch_groups = [g for g in groups_before if g["media_type"] == "rewatch"]
        self.assertEqual(len(rewatch_groups), 0)

        data = self._backlog_save_data(movie)
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
        item_normal = Item.objects.create(
            media_id="5020",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Normal Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=item_normal, user=self.user, status=Status.PLANNING.value
        )

        item_rewatch = Item.objects.create(
            media_id="5021",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Rewatch Movie",
            image="http://example.com/image.jpg",
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
        item = Item.objects.create(
            media_id="5040",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Checkbox Form Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        response = self.client.get(reverse("home"))
        self.assertContains(response, 'name="is_rewatch"')

    def test_is_rewatch_checkbox_checked_when_true(self):
        """The is_rewatch checkbox is checked when the field is True."""
        item = Item.objects.create(
            media_id="5041",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Checked Rewatch Movie",
            image="http://example.com/image.jpg",
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
        item = Item.objects.create(
            media_id="5042",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Uncheck Rewatch Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
            is_rewatch=True,
        )

        data = self._backlog_save_data(movie)
        # checkbox unchecked = field absent from POST
        self.client.post(reverse("backlog_save"), data)

        movie.refresh_from_db()
        self.assertFalse(movie.is_rewatch)

    @patch("app.providers.services.get_media_metadata")
    def test_archive_save_is_rewatch_untoggle_triggers_refresh(self, mock_metadata):
        """Toggling is_rewatch off on archive card triggers HX-Refresh."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="5043",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Archive Untoggle Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.COMPLETED.value,
            is_rewatch=True,
        )

        data = self._backlog_save_data(movie)
        data["source_context"] = "archive"
        # checkbox unchecked = absent from POST
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response["HX-Refresh"], "true")

    @patch("app.providers.services.get_media_metadata")
    def test_archive_save_is_rewatch_unchanged_no_refresh(self, mock_metadata):
        """Archive edit without is_rewatch change has no refresh."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="5044",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Archive No Refresh Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.COMPLETED.value
        )

        data = self._backlog_save_data(movie)
        data["source_context"] = "archive"
        data["score"] = "9.0"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertNotIn("HX-Refresh", response)

    def test_is_rewatch_combined_with_status_change(self):
        """Both status and is_rewatch change in one save triggers refresh."""
        item = Item.objects.create(
            media_id="5045",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Combined Change Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        data = self._backlog_save_data(movie)
        data["status"] = Status.IN_PROGRESS.value
        data["is_rewatch"] = "on"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertEqual(response["HX-Refresh"], "true")
        movie.refresh_from_db()
        self.assertEqual(movie.status, Status.IN_PROGRESS.value)
        self.assertTrue(movie.is_rewatch)

    def test_is_rewatch_with_caught_up_both_toggled(self):
        """Both is_rewatch and caught_up save correctly together."""
        item = Item.objects.create(
            media_id="5046",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Both Flags Anime",
            image="http://example.com/image.jpg",
        )
        anime = Anime.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        data = self._backlog_save_data(anime)
        data["is_rewatch"] = "on"
        data["caught_up"] = "on"
        self.client.post(reverse("backlog_save"), data)

        anime.refresh_from_db()
        self.assertTrue(anime.is_rewatch)
        self.assertTrue(anime.caught_up)

    def test_type_group_disappears_when_all_items_are_rewatches(self):
        """Type group is removed when all its items are rewatches."""
        item = Item.objects.create(
            media_id="5047",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Only Rewatch Movie",
            image="http://example.com/image.jpg",
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
        item = Item.objects.create(
            media_id="5048",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="HX Refresh Rewatch",
            image="http://example.com/image.jpg",
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
        normal_item = Item.objects.create(
            media_id="5049",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Keep In Type",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=normal_item, user=self.user, status=Status.PLANNING.value
        )

        item = Item.objects.create(
            media_id="5050",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Back To Type Movie",
            image="http://example.com/image.jpg",
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

        data = self._backlog_save_data(movie)
        # checkbox unchecked = absent
        self.client.post(reverse("backlog_save"), data)

        page_after = self.client.get(reverse("home"))
        groups_after = page_after.context["groups"]
        rewatch_groups = [g for g in groups_after if g["media_type"] == "rewatch"]
        self.assertEqual(len(rewatch_groups), 0)

        type_titles = _flatten_group_titles(groups_after)
        self.assertIn("Back To Type Movie", type_titles)


class NotYetAiringTests(TestCase):
    """Test the 'Not Yet Airing' backlog section."""

    @classmethod
    def setUpTestData(cls):
        """Create a user."""
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def _create_anime_with_future_events(self, media_id, title, days_ahead=30):
        item = Item.objects.create(
            media_id=media_id,
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title=title,
            image="http://example.com/image.jpg",
        )
        Event.objects.create(
            item=item,
            content_number=1,
            datetime=timezone.now() + timedelta(days=days_ahead),
        )
        return item

    def test_not_yet_airing_in_dedicated_section_all_mode(self):
        """Not-yet-airing anime appears in a dedicated group, not in type groups."""
        item = self._create_anime_with_future_events("6000", "Future Anime")
        Anime.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        type_titles = []
        nya_titles = []
        for group in groups:
            for sg in group["status_groups"]:
                for m in sg["items"]:
                    if group["media_type"] == "not_yet_airing":
                        nya_titles.append(m.item.title)
                    else:
                        type_titles.append(m.item.title)

        self.assertIn("Future Anime", nya_titles)
        self.assertNotIn("Future Anime", type_titles)

    def test_not_yet_airing_separated_in_type_filter(self):
        """Not-yet-airing items get their own group even when filtering by type."""
        item = self._create_anime_with_future_events("6001", "Filtered Future Anime")
        Anime.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        response = self.client.get(reverse("home") + "?type=anime")
        groups = response.context["groups"]

        media_types = {g["media_type"] for g in groups}
        self.assertIn("not_yet_airing", media_types)

    def test_not_yet_airing_only_tv_anime(self):
        """Movies with future events are NOT extracted to Not Yet Airing."""
        item = Item.objects.create(
            media_id="6002",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Future Movie",
            image="http://example.com/image.jpg",
        )
        Event.objects.create(
            item=item,
            content_number=None,
            datetime=timezone.now() + timedelta(days=30),
        )
        Movie.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        media_types = {g["media_type"] for g in groups}
        self.assertNotIn("not_yet_airing", media_types)

        titles = _flatten_group_titles(groups)
        self.assertIn("Future Movie", titles)

    def test_not_yet_airing_mixed_events_stays_in_group(self):
        """Anime with past AND future events stays in regular group."""
        item = Item.objects.create(
            media_id="6003",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Airing Anime",
            image="http://example.com/image.jpg",
        )
        Event.objects.create(
            item=item,
            content_number=1,
            datetime=timezone.now() - timedelta(days=7),
        )
        Event.objects.create(
            item=item,
            content_number=2,
            datetime=timezone.now() + timedelta(days=7),
        )
        Anime.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        media_types = {g["media_type"] for g in groups}
        self.assertNotIn("not_yet_airing", media_types)

        titles = _flatten_group_titles(groups)
        self.assertIn("Airing Anime", titles)

    def test_not_yet_airing_sorted_by_release_date(self):
        """Items in Not Yet Airing are sorted by earliest release date."""
        item_far = self._create_anime_with_future_events(
            "6004", "Far Future Anime", days_ahead=90
        )
        Anime.objects.create(
            item=item_far, user=self.user, status=Status.PLANNING.value
        )

        item_near = self._create_anime_with_future_events(
            "6005", "Near Future Anime", days_ahead=10
        )
        Anime.objects.create(
            item=item_near, user=self.user, status=Status.PLANNING.value
        )

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        nya_group = [g for g in groups if g["media_type"] == "not_yet_airing"]
        self.assertEqual(len(nya_group), 1)

        titles = []
        for sg in nya_group[0]["status_groups"]:
            titles.extend(m.item.title for m in sg["items"])

        self.assertEqual(titles, ["Near Future Anime", "Far Future Anime"])

    def test_no_not_yet_airing_section_when_empty(self):
        """No Not Yet Airing group when no items meet criteria."""
        item = Item.objects.create(
            media_id="6006",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Normal Anime",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]
        media_types = {g["media_type"] for g in groups}
        self.assertNotIn("not_yet_airing", media_types)
        self.assertNotContains(response, "Not Yet Airing")

    def test_min_datetime_planning_is_not_yet_airing(self):
        """Anime with only datetime.min events in Planning is not-yet-airing."""
        item = Item.objects.create(
            media_id="6007",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Upcoming Unknown Anime",
            image="http://example.com/image.jpg",
        )
        Event.objects.create(
            item=item,
            content_number=None,
            datetime=datetime.min.replace(tzinfo=UTC),
        )
        Anime.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value, progress=0
        )

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        nya_titles = []
        type_titles = []
        for group in groups:
            for sg in group["status_groups"]:
                for m in sg["items"]:
                    if group["media_type"] == "not_yet_airing":
                        nya_titles.append(m.item.title)
                    else:
                        type_titles.append(m.item.title)

        self.assertIn("Upcoming Unknown Anime", nya_titles)
        self.assertNotIn("Upcoming Unknown Anime", type_titles)

    def test_min_datetime_in_progress_stays_in_regular_group(self):
        """Anime with only datetime.min events in In Progress stays in regular group."""
        item = Item.objects.create(
            media_id="6008",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Airing Long Runner",
            image="http://example.com/image.jpg",
        )
        Event.objects.create(
            item=item,
            content_number=None,
            datetime=datetime.min.replace(tzinfo=UTC),
        )
        Anime.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value, progress=0
        )

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        media_types = {g["media_type"] for g in groups}
        self.assertNotIn("not_yet_airing", media_types)

        titles = _flatten_group_titles(groups)
        self.assertIn("Airing Long Runner", titles)

    def test_not_yet_airing_future_plus_min_datetime(self):
        """Anime with future real dates + datetime.min events is not-yet-airing."""
        item = Item.objects.create(
            media_id="6009",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Partial Schedule Anime",
            image="http://example.com/image.jpg",
        )
        Event.objects.create(
            item=item,
            content_number=1,
            datetime=timezone.now() + timedelta(days=30),
        )
        Event.objects.create(
            item=item,
            content_number=12,
            datetime=datetime.min.replace(tzinfo=UTC),
        )
        Anime.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value, progress=0
        )

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        nya_titles = []
        type_titles = []
        for group in groups:
            for sg in group["status_groups"]:
                for m in sg["items"]:
                    if group["media_type"] == "not_yet_airing":
                        nya_titles.append(m.item.title)
                    else:
                        type_titles.append(m.item.title)

        self.assertIn("Partial Schedule Anime", nya_titles)
        self.assertNotIn("Partial Schedule Anime", type_titles)


class HomeViewConsistencyTests(TestCase):
    """Test that HTMX partial responses match full page reloads."""

    @classmethod
    def setUpTestData(cls):
        """Create a user."""
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def _backlog_save_data(self, media):
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
        }

    # --- quick_complete consistency ---

    @patch("app.providers.services.get_media_metadata")
    def test_quick_complete_item_leaves_backlog_on_reload(self, mock_metadata):
        """Completing an item removes it from backlog groups on reload."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="1000",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Will Complete",
            image="http://example.com/image.jpg",
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
        item = Item.objects.create(
            media_id="1001",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Archive Me",
            image="http://example.com/image.jpg",
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
        items = []
        movies = []
        for mid in ["1010", "1011"]:
            item = Item.objects.create(
                media_id=mid,
                source=Sources.TMDB.value,
                media_type=MediaTypes.MOVIE.value,
                title=f"Seq Movie {mid}",
                image="http://example.com/image.jpg",
            )
            items.append(item)
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
        item = Item.objects.create(
            media_id="1020",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Drop Me Fully",
            image="http://example.com/image.jpg",
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
        item = Item.objects.create(
            media_id="1050",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Start Me",
            image="http://example.com/image.jpg",
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
        item = Item.objects.create(
            media_id="1051",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Plan Me",
            image="http://example.com/image.jpg",
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
        item = Item.objects.create(
            media_id="1052",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Start Date Check",
            image="http://example.com/image.jpg",
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
        anime_item = Item.objects.create(
            media_id="1030",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Catch Up Consistency",
            image="http://example.com/image.jpg",
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
        item = Item.objects.create(
            media_id="1040",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Score Persist Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        data = self._backlog_save_data(movie)
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
        item = Item.objects.create(
            media_id="1041",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Notes Persist Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        data = self._backlog_save_data(movie)
        data["notes"] = "Great movie so far"
        self.client.post(reverse("backlog_save"), data)

        movie.refresh_from_db()
        self.assertEqual(movie.notes, "Great movie so far")

    @patch("app.providers.services.get_media_metadata")
    def test_backlog_save_link_persists_on_reload(self, mock_metadata):
        """Link saved via inline edit persists in DB."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="1042",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Link Persist Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        data = self._backlog_save_data(movie)
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
        item = Item.objects.create(
            media_id="1050",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Save Complete Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        data = self._backlog_save_data(movie)
        data["status"] = Status.COMPLETED.value
        self.client.post(reverse("backlog_save"), data)

        page = self.client.get(reverse("home"))
        backlog_titles = _flatten_group_titles(page.context["groups"])
        archive_titles = [m.item.title for m in page.context["archive"]]
        self.assertNotIn("Save Complete Movie", backlog_titles)
        self.assertIn("Save Complete Movie", archive_titles)

    def test_backlog_save_drop_gone_on_reload(self):
        """Dropping via inline edit removes item from everything on reload."""
        item = Item.objects.create(
            media_id="1051",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Save Drop Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        data = self._backlog_save_data(movie)
        data["status"] = Status.DROPPED.value
        self.client.post(reverse("backlog_save"), data)

        page = self.client.get(reverse("home"))
        backlog_titles = _flatten_group_titles(page.context["groups"])
        archive_titles = [m.item.title for m in page.context["archive"]]
        self.assertNotIn("Save Drop Movie", backlog_titles)
        self.assertNotIn("Save Drop Movie", archive_titles)

    def test_backlog_save_status_change_correct_group_on_reload(self):
        """Changing status via inline edit places item in correct group on reload."""
        item = Item.objects.create(
            media_id="1052",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Regroup Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        data = self._backlog_save_data(movie)
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
        item = Item.objects.create(
            media_id="1053",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Pause Me Anime",
            image="http://example.com/image.jpg",
        )
        anime = Anime.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        data = self._backlog_save_data(anime)
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
        item = Item.objects.create(
            media_id="1060",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Rewatch Target",
            image="http://example.com/image.jpg",
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
        item = Item.objects.create(
            media_id="1061",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Already Active Movie",
            image="http://example.com/image.jpg",
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
        """Complete → rewatch → verify backlog and archive are both correct."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="1070",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Lifecycle Movie",
            image="http://example.com/image.jpg",
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
        """Complete → rewatch → complete again: archive count increases by 1."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="1071",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Double Complete Movie",
            image="http://example.com/image.jpg",
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
        item = Item.objects.create(
            media_id="1080",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Score Response Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        data = self._backlog_save_data(movie)
        data["score"] = "7.5"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertContains(response, "7.5")

    @patch("app.providers.services.get_media_metadata")
    def test_backlog_save_response_shows_updated_link(self, mock_metadata):
        """The HTMX card response includes the external link icon when saved."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="1081",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Link Response Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value
        )

        data = self._backlog_save_data(movie)
        data["link"] = "https://example.com/stream"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertContains(response, "https://example.com/stream")

    @patch("app.providers.services.get_media_metadata")
    def test_backlog_save_progress_response_matches_reload(self, mock_metadata):
        """Progress value in HTMX response matches page reload."""
        mock_metadata.return_value = {"max_progress": 24}
        item = Item.objects.create(
            media_id="1082",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Progress Consistency Anime",
            image="http://example.com/image.jpg",
        )
        anime = Anime.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=3,
        )

        data = self._backlog_save_data(anime)
        data["progress"] = "7"
        response = self.client.post(reverse("backlog_save"), data)

        self.assertContains(response, 'value="7"')

        anime.refresh_from_db()
        self.assertEqual(anime.progress, 7)


class CaughtUpToggleTests(TestCase):
    """Tests for manual caught_up toggle on backlog cards."""

    @classmethod
    def setUpTestData(cls):  # noqa: D102
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.anime_item = Item.objects.create(
            media_id="3000",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Ongoing Anime",
            image="http://example.com/image.jpg",
        )

    def setUp(self):
        self.client.login(**self.credentials)

    def _backlog_save_data(self, media):
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
        }

    def test_manual_caught_up_overrides_auto_detection(self):
        """Manual caught_up=True shows 'Caught Up' even when progress is behind."""
        anime = Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=3,
            caught_up=True,
        )
        Event.objects.create(
            item=self.anime_item,
            content_number=10,
            datetime=timezone.now() + timedelta(days=2),
        )

        response = self.client.get(reverse("home"))
        content = response.content.decode()

        card_id = f"backlog-card-anime-{anime.id}"
        card_start = content.find(card_id)
        self.assertNotEqual(card_start, -1)
        card_section = content[card_start : card_start + 8000]

        self.assertIn("Caught Up", card_section)
        self.assertNotIn("Caught Up?", card_section)

    def test_manual_caught_up_false_uses_auto_detection(self):
        """With caught_up=False and progress behind, shows 'Caught Up?'."""
        Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=3,
            caught_up=False,
        )
        Event.objects.create(
            item=self.anime_item,
            content_number=10,
            datetime=timezone.now() + timedelta(days=2),
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, "Caught Up?")

    def test_auto_caught_up_works_without_manual_flag(self):
        """Progress matching next event shows 'Caught Up' even without flag."""
        Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=9,
            caught_up=False,
        )
        Event.objects.create(
            item=self.anime_item,
            content_number=10,
            datetime=timezone.now() + timedelta(days=2),
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "Caught Up?")

    def test_caught_up_toggle_persists_via_backlog_save(self):
        """Setting caught_up via edit form persists on reload."""
        anime = Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=3,
        )
        Event.objects.create(
            item=self.anime_item,
            content_number=10,
            datetime=timezone.now() + timedelta(days=2),
        )

        data = self._backlog_save_data(anime)
        data["caught_up"] = "on"
        self.client.post(reverse("backlog_save"), data)

        anime.refresh_from_db()
        self.assertTrue(anime.caught_up)

    def test_caught_up_uncheck_persists_via_backlog_save(self):
        """Unchecking caught_up via edit form persists on reload."""
        anime = Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=3,
            caught_up=True,
        )
        Event.objects.create(
            item=self.anime_item,
            content_number=10,
            datetime=timezone.now() + timedelta(days=2),
        )

        data = self._backlog_save_data(anime)
        # checkbox unchecked = field absent from POST
        self.client.post(reverse("backlog_save"), data)

        anime.refresh_from_db()
        self.assertFalse(anime.caught_up)

    def test_edit_form_has_caught_up_checkbox(self):
        """The backlog card edit form contains a caught_up checkbox."""
        Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=3,
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, 'name="caught_up"')

    @patch("app.providers.services.get_media_metadata")
    def test_caught_up_no_effect_without_next_event(self, mock_metadata):
        """caught_up=True on finished content still shows 'Done' button."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="3001",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Finished Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            caught_up=True,
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, "Done")

    def test_caught_up_response_matches_reload(self):
        """HTMX response after toggling caught_up matches page reload."""
        anime = Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=3,
        )
        Event.objects.create(
            item=self.anime_item,
            content_number=10,
            datetime=timezone.now() + timedelta(days=2),
        )

        data = self._backlog_save_data(anime)
        data["caught_up"] = "on"
        response = self.client.post(reverse("backlog_save"), data)
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "Caught Up?")

        page = self.client.get(reverse("home"))
        content = page.content.decode()
        card_id = f"backlog-card-anime-{anime.id}"
        card_start = content.find(card_id)
        card_section = content[card_start : card_start + 8000]
        self.assertIn("Caught Up", card_section)
        self.assertNotIn("Caught Up?", card_section)

    def test_caught_up_checkbox_checked_when_true(self):
        """The caught_up checkbox is checked when the field is True."""
        Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=3,
            caught_up=True,
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, 'name="caught_up"')
        content = response.content.decode()
        caught_up_pos = content.find('name="caught_up"')
        checkbox_context = content[caught_up_pos : caught_up_pos + 200]
        self.assertIn("checked", checkbox_context)


class ArchiveViewTests(TestCase):
    """Tests for the dedicated archive page and archive card editing."""

    @classmethod
    def setUpTestData(cls):  # noqa: D102
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

    def test_archive_page_hides_sort_and_filters(self):
        """Archive view does not show sort dropdown or type filter chips."""
        response = self.client.get(self._archive_url())
        self.assertNotContains(response, "arrows-up-down")
        self.assertNotContains(response, "rounded-full text-sm font-medium")

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


class EnrichmentTests(TestCase):
    """Test the enrich_items_with_user_data helper."""

    @classmethod
    def setUpTestData(cls):
        """Create a user and test data."""
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )

    def setUp(self):
        self.factory = RequestFactory()

    def _make_request(self):
        request = self.factory.get("/")
        request.user = self.user
        return request

    def _search_items(self):
        return [
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        ]

    @patch("app.providers.services.get_media_metadata")
    def test_enrichment_prefers_completed_over_active(self, mock_metadata):
        """Test that completed/dropped instances are preferred over active."""
        mock_metadata.return_value = {"max_progress": None}
        completed = Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
        )
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        results = enrich_items_with_user_data(
            self._make_request(), self._search_items(), "search"
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["media"].id, completed.id)
        self.assertEqual(results[0]["media"].status, Status.COMPLETED.value)
        self.assertTrue(results[0]["has_active"])

    @patch("app.providers.services.get_media_metadata")
    def test_enrichment_has_active_true(self, mock_metadata):
        """Test that has_active is True when an active instance exists."""
        mock_metadata.return_value = {"max_progress": None}
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
        )
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        results = enrich_items_with_user_data(
            self._make_request(), self._search_items(), "search"
        )

        self.assertTrue(results[0]["has_active"])

    @patch("app.providers.services.get_media_metadata")
    def test_enrichment_has_active_false(self, mock_metadata):
        """Test that has_active is False with only completed instances."""
        mock_metadata.return_value = {"max_progress": None}
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
        )

        results = enrich_items_with_user_data(
            self._make_request(), self._search_items(), "search"
        )

        self.assertFalse(results[0]["has_active"])

    @patch("app.providers.services.get_media_metadata")
    def test_enrichment_prefers_completed_over_dropped(self, mock_metadata):
        """After canceling a rewatch, enrichment shows Completed not Dropped."""
        mock_metadata.return_value = {"max_progress": None}
        completed = Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
        )
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.DROPPED.value,
        )

        results = enrich_items_with_user_data(
            self._make_request(), self._search_items(), "search"
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["media"].id, completed.id)
        self.assertEqual(results[0]["media"].status, Status.COMPLETED.value)
        self.assertFalse(results[0]["has_active"])


class EnglishTitleTests(TestCase):
    """Test English title display and search."""

    @classmethod
    def setUpTestData(cls):
        """Create anime item with English title for testing."""
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.item = Item.objects.create(
            media_id="16498",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Shingeki no Kyojin",
            english_title="Attack on Titan",
            image="http://example.com/image.jpg",
        )
        Anime.objects.create(
            item=cls.item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
        )

    def setUp(self):
        self.client.login(**self.credentials)

    def test_english_title_displayed_on_backlog_card(self):
        """Test that English title subtitle appears on home backlog cards."""
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Attack on Titan")

    def test_english_title_not_shown_when_empty(self):
        """Test that no subtitle is rendered when english_title is empty."""
        self.item.english_title = ""
        self.item.save()
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "Attack on Titan")

    @patch("app.providers.services.get_media_metadata")
    def test_english_title_on_media_details(self, mock_metadata):
        """Test that English title subtitle appears on media details page."""
        mock_metadata.return_value = {
            "media_id": "16498",
            "source": Sources.MAL.value,
            "source_url": "https://myanimelist.net/anime/16498",
            "media_type": MediaTypes.ANIME.value,
            "title": "Shingeki no Kyojin",
            "english_title": "Attack on Titan",
            "image": "http://example.com/image.jpg",
            "synopsis": "Test synopsis",
            "genres": [],
            "score": None,
            "score_count": 0,
            "max_progress": 25,
            "details": {},
            "related": {},
        }
        response = self.client.get(
            reverse(
                "media_details",
                kwargs={
                    "source": Sources.MAL.value,
                    "media_type": MediaTypes.ANIME.value,
                    "media_id": "16498",
                    "title": "shingeki-no-kyojin",
                },
            )
        )
        self.assertContains(response, "Attack on Titan")

    def test_search_matches_english_title(self):
        """Test that in-library search finds items by English title."""
        response = self.client.get(
            reverse("medialist", kwargs={"media_type": MediaTypes.ANIME.value})
            + "?search=Attack"
        )
        self.assertContains(response, "Shingeki no Kyojin")

    def test_search_matches_original_title(self):
        """Test that in-library search still finds items by original title."""
        response = self.client.get(
            reverse("medialist", kwargs={"media_type": MediaTypes.ANIME.value})
            + "?search=Shingeki"
        )
        self.assertContains(response, "Shingeki no Kyojin")

    def test_search_no_match(self):
        """Test that search returns no results for unrelated queries."""
        response = self.client.get(
            reverse("medialist", kwargs={"media_type": MediaTypes.ANIME.value})
            + "?search=Naruto"
        )
        self.assertNotContains(response, "Shingeki no Kyojin")


class GetEnglishTitleTests(TestCase):
    """Test the get_english_title helper from MAL provider."""

    def test_returns_english_title(self):
        """Test extraction of English title from alternative_titles."""
        response = {
            "title": "Shingeki no Kyojin",
            "alternative_titles": {"en": "Attack on Titan", "ja": "進撃の巨人"},
        }
        self.assertEqual(get_english_title(response), "Attack on Titan")

    def test_returns_empty_when_same_as_title(self):
        """Test that empty string is returned when English title matches main title."""
        response = {
            "title": "Attack on Titan",
            "alternative_titles": {"en": "Attack on Titan"},
        }
        self.assertEqual(get_english_title(response), "")

    def test_returns_empty_when_no_alternative_titles(self):
        """Test graceful handling when alternative_titles field is missing."""
        response = {"title": "Some Anime"}
        self.assertEqual(get_english_title(response), "")

    def test_returns_empty_when_en_is_empty_string(self):
        """Test that empty English title string is treated as no title."""
        response = {
            "title": "Some Anime",
            "alternative_titles": {"en": "", "ja": "何かのアニメ"},
        }
        self.assertEqual(get_english_title(response), "")

    def test_returns_empty_when_alternative_titles_empty(self):
        """Test handling of empty alternative_titles dict."""
        response = {
            "title": "Some Anime",
            "alternative_titles": {},
        }
        self.assertEqual(get_english_title(response), "")


class BacklogActionRegistryTests(TestCase):
    """Ensure every backlog action endpoint has HX-Refresh policy tests."""

    def test_all_backlog_actions_covered(self):  # noqa: D102
        action_names = {
            p.name
            for p in urlpatterns
            if hasattr(p, "name")
            and p.name
            and (p.name.startswith("quick_") or p.name.startswith("backlog_"))
        }

        untested = action_names - TESTED_BACKLOG_ACTIONS
        self.assertEqual(
            untested,
            set(),
            f"Action(s) {untested} need HX-Refresh policy tests. "
            "Add coverage, then add the name to TESTED_BACKLOG_ACTIONS.",
        )
