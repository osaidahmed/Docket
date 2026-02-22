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
    MediaTypes,
    Movie,
    Season,
    Sources,
    Status,
)
from events.models import Event
from users.models import HomeSortChoices


def _flatten_group_titles(groups):
    """Extract all item titles from grouped backlog structure."""
    titles = []
    for group in groups:
        for sg in group["status_groups"]:
            titles.extend(m.item.title for m in sg["items"])
    return titles


class HomeViewTests(TestCase):
    """Test the home view."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

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
            user=self.user,
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
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=10,
        )

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

    def test_backlog_card_shows_synopsis(self):
        """Test that synopsis text appears in the backlog card HTML."""
        movie_item = Item.objects.create(
            media_id="600",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Movie With Synopsis",
            image="http://example.com/image.jpg",
            synopsis="A gripping tale of adventure and mystery.",
        )
        Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, "A gripping tale of adventure and mystery.")

    def test_archive_opens_with_view_param(self):
        """Test that ?view=archive sets archive_open in context."""
        response = self.client.get(reverse("home") + "?view=archive")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context.get("archive_open"))

    def test_sidebar_contains_archive_link(self):
        """Test that the sidebar includes an Archive navigation link."""
        response = self.client.get(reverse("home"))
        self.assertContains(response, "?view=archive")
        self.assertContains(response, ">Archive</span>")

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

    def test_tv_filter_chip_exists(self):
        """Test that TV Show appears as a filter chip option."""
        response = self.client.get(reverse("home"))
        filter_values = [c["value"] for c in response.context["type_filter_choices"]]
        self.assertIn(MediaTypes.TV.value, filter_values)
        self.assertNotIn(MediaTypes.SEASON.value, filter_values)
        self.assertNotIn(MediaTypes.EPISODE.value, filter_values)

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
    def test_archive_count_on_page_matches_list(self, mock_metadata):
        """Test that archive_count in context matches the archive list length."""
        mock_metadata.return_value = {"max_progress": None}
        for mid in ["810", "811", "812"]:
            item = Item.objects.create(
                media_id=mid,
                source=Sources.TMDB.value,
                media_type=MediaTypes.MOVIE.value,
                title=f"Movie {mid}",
                image="http://example.com/image.jpg",
            )
            Movie.objects.create(
                item=item, user=self.user, status=Status.COMPLETED.value
            )

        response = self.client.get(reverse("home"))
        self.assertEqual(
            response.context["archive_count"], len(response.context["archive"])
        )

    @patch("app.providers.services.get_media_metadata")
    def test_quick_complete_archive_count_matches_page(self, mock_metadata):
        """Test that archive_count from quick_complete matches a fresh page load."""
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

        page = self.client.get(reverse("home"))
        self.assertEqual(oob_count, page.context["archive_count"])

    @patch("app.providers.services.get_media_metadata")
    def test_archive_count_stable_with_rewatched_item(self, mock_metadata):
        """Test completing an item with prior rewatches increases count by 1."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="830",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Multi Rewatch Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)

        new_item = Item.objects.create(
            media_id="831",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Fresh Movie",
            image="http://example.com/image.jpg",
        )
        new_movie = Movie.objects.create(
            item=new_item, user=self.user, status=Status.IN_PROGRESS.value
        )

        page_before = self.client.get(reverse("home"))
        count_before = page_before.context["archive_count"]

        self.client.post(
            reverse("quick_complete"),
            {"media_type": "movie", "instance_id": new_movie.id},
        )

        page_after = self.client.get(reverse("home"))
        count_after = page_after.context["archive_count"]

        self.assertEqual(count_after, count_before + 1)

    @patch("app.providers.services.get_media_metadata")
    def test_archive_count_during_active_rewatch(self, mock_metadata):
        """Test that completing a rewatch increases archive count by exactly 1."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="840",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Rewatch In Progress",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)
        rewatch = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        page_before = self.client.get(reverse("home"))
        count_before = page_before.context["archive_count"]

        self.client.post(
            reverse("quick_complete"),
            {"media_type": "movie", "instance_id": rewatch.id},
        )

        page_after = self.client.get(reverse("home"))
        count_after = page_after.context["archive_count"]

        self.assertEqual(count_after, count_before + 1)

    @patch("app.providers.services.get_media_metadata")
    def test_archive_count_oob_matches_during_rewatch(self, mock_metadata):
        """Test OOB archive_count matches page after completing a rewatch."""
        mock_metadata.return_value = {"max_progress": None}
        item = Item.objects.create(
            media_id="850",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="OOB Rewatch Test",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(item=item, user=self.user, status=Status.COMPLETED.value)
        rewatch = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

        response = self.client.post(
            reverse("quick_complete"),
            {"media_type": "movie", "instance_id": rewatch.id},
        )
        oob_count = int(
            response.content.decode()
            .split('id="archive-count"')[1]
            .split("(")[1]
            .split(")")[0]
        )

        page = self.client.get(reverse("home"))
        self.assertEqual(oob_count, page.context["archive_count"])

    @patch("app.providers.services.get_media_metadata")
    def test_archive_count_oob_excludes_active_rewatch_items(self, mock_metadata):
        """Test OOB count excludes items whose newest instance is a rewatch."""
        mock_metadata.return_value = {"max_progress": None}
        item_a = Item.objects.create(
            media_id="860",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Active Rewatch Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(item=item_a, user=self.user, status=Status.COMPLETED.value)
        Movie.objects.create(item=item_a, user=self.user, status=Status.PLANNING.value)

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

    @patch("app.providers.services.get_media_metadata")
    def test_backlog_save_complete_archive_count_excludes_rewatches(
        self, mock_metadata
    ):
        """Test backlog_save archive_count excludes items with active rewatches."""
        mock_metadata.return_value = {"max_progress": None}
        item_a = Item.objects.create(
            media_id="870",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Rewatch In Progress A",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(item=item_a, user=self.user, status=Status.COMPLETED.value)
        Movie.objects.create(item=item_a, user=self.user, status=Status.PLANNING.value)

        item_b = Item.objects.create(
            media_id="871",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Complete Via Save",
            image="http://example.com/image.jpg",
        )
        movie_b = Movie.objects.create(
            item=item_b, user=self.user, status=Status.IN_PROGRESS.value
        )

        data = self._backlog_save_data(movie_b)
        data["status"] = Status.COMPLETED.value
        response = self.client.post(reverse("backlog_save"), data)

        oob_count = int(
            response.content.decode()
            .split('id="archive-count"')[1]
            .split("(")[1]
            .split(")")[0]
        )

        page = self.client.get(reverse("home"))
        self.assertEqual(oob_count, page.context["archive_count"])

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
        self.assertNotContains(response, "Caught Up")

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
        self.assertNotContains(response, "Caught Up")

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
        self.assertNotContains(response, "Caught Up")


class EnrichmentTests(TestCase):
    """Test the enrich_items_with_user_data helper."""

    def setUp(self):
        """Create a user and test data."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.factory = RequestFactory()

        self.item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )

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
    def test_enrichment_newest_instance_wins(self, mock_metadata):
        """Test that setdefault keeps newest instance (first in queryset)."""
        mock_metadata.return_value = {"max_progress": None}
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
        )
        planning = Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        results = enrich_items_with_user_data(
            self._make_request(), self._search_items(), "search"
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["media"].id, planning.id)
        self.assertEqual(results[0]["media"].status, Status.PLANNING.value)

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
