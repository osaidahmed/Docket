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
