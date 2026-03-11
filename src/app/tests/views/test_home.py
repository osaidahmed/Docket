import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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
from app.urls import urlpatterns
from users.models import HomeSortChoices

TESTED_BACKLOG_ACTIONS = {
    "quick_add",
    "quick_archive",
    "quick_catch_up",
    "quick_catch_up_add",
    "quick_complete",
    "quick_drop",
    "quick_rewatch",
    "quick_status_transition",
    "quick_untrack",
    "backlog_save",
    "toggle_pin",
}


def _flatten_group_titles(groups):
    """Extract all item titles from grouped backlog structure."""
    titles = []
    for group in groups:
        for sg in group["status_groups"]:
            titles.extend(m.item.title for m in sg["items"])
    return titles


def _find_newline_in_js_string(expr):
    """Return an error message if *expr* contains a newline inside a JS string."""
    in_string = False
    quote_char = None
    for char in expr:
        if not in_string:
            if char in ("'", '"'):
                in_string = True
                quote_char = char
            continue
        if char == quote_char:
            in_string = False
        elif char == "\n":
            start = max(0, expr.index(quote_char) - 20)
            end = expr.index(quote_char) + 40
            return f"Newline inside JS string in x-data: ...{expr[start:end]}..."
    return None


class HomeViewTests(TestCase):
    """Test the home view core rendering and grouping."""

    @classmethod
    def setUpTestData(cls):
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
            error = _find_newline_in_js_string(match.group(1))
            if error:
                self.fail(error)

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
        self.assertEqual(response.context["selected_types"], {"anime"})

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
        self.assertEqual(page_final.context["archive_count"], count_before_save + 1)

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


class BacklogActionRegistryTests(TestCase):
    """Ensure every backlog action endpoint has HX-Refresh policy tests."""

    def test_all_backlog_actions_covered(self):
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
