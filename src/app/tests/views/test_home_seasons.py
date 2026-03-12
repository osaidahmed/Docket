import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import Anime, Item, Manga, MediaTypes, Season, Sources, Status

_DEFAULT_IMAGE = "http://example.com/image.jpg"


class PinnedPlanningTests(TestCase):
    """Tests for pinning Planning items and drag-and-drop reorder."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.anime_item = Item.objects.create(
            media_id="pin-1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Anime A",
            image=_DEFAULT_IMAGE,
        )
        cls.manga_item = Item.objects.create(
            media_id="pin-2",
            source=Sources.MAL.value,
            media_type=MediaTypes.MANGA.value,
            title="Manga B",
            image=_DEFAULT_IMAGE,
        )
        cls.movie_item = Item.objects.create(
            media_id="pin-3",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Movie C",
            image=_DEFAULT_IMAGE,
        )

    def setUp(self):
        self.client.login(**self.credentials)
        patcher = patch(
            "app.providers.services.get_media_metadata",
            return_value={"max_progress": None},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

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

    def test_toggle_pin_unpinned_item(self):
        """toggle_pin on unpinned Planning item sets pin_order."""
        anime = Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.PLANNING.value,
        )
        response = self.client.post(
            reverse("toggle_pin"),
            {"media_type": "anime", "instance_id": anime.id},
        )
        self.assertEqual(response["HX-Refresh"], "true")
        anime.refresh_from_db()
        self.assertIsNotNone(anime.pin_order)

    def test_toggle_pin_pinned_item(self):
        """toggle_pin on pinned item clears pin_order."""
        anime = Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=0,
        )
        response = self.client.post(
            reverse("toggle_pin"),
            {"media_type": "anime", "instance_id": anime.id},
        )
        self.assertEqual(response["HX-Refresh"], "true")
        anime.refresh_from_db()
        self.assertIsNone(anime.pin_order)

    def test_pinned_items_in_pinned_section(self):
        """Pinned items appear in sg.pinned_items on the backlog."""
        Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=0,
        )
        Manga.objects.create(
            item=self.manga_item,
            user=self.user,
            status=Status.PLANNING.value,
        )
        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        pinned_titles = []
        rest_titles = []
        for group in groups:
            for sg in group["status_groups"]:
                rest_titles.extend(m.item.title for m in sg["items"])
                if "pinned_items" in sg:
                    pinned_titles.extend(m.item.title for m in sg["pinned_items"])

        self.assertIn("Anime A", pinned_titles)
        self.assertIn("Manga B", rest_titles)
        self.assertNotIn("Anime A", rest_titles)

    def test_no_pinned_section_when_empty(self):
        """No pinned_items key when nothing is pinned."""
        Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.PLANNING.value,
        )
        response = self.client.get(reverse("home"))
        groups = response.context["groups"]
        for group in groups:
            for sg in group["status_groups"]:
                self.assertNotIn("pinned_items", sg)

    def test_pin_order_preserved_across_status_change(self):
        """pin_order survives Planning -> In Progress -> Planning."""
        anime = Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=5,
        )
        anime.status = Status.IN_PROGRESS.value
        anime.save()
        anime.status = Status.PLANNING.value
        anime.save()
        anime.refresh_from_db()
        self.assertEqual(anime.pin_order, 5)

    def test_save_pin_order(self):
        """POST ordered IDs updates pin_order values."""
        anime = Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=0,
        )
        manga = Manga.objects.create(
            item=self.manga_item,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=1,
        )
        response = self.client.post(
            reverse("save_pin_order"),
            json.dumps(
                [
                    {"media_type": "manga", "id": manga.id},
                    {"media_type": "anime", "id": anime.id},
                ]
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 204)
        manga.refresh_from_db()
        anime.refresh_from_db()
        self.assertEqual(manga.pin_order, 0)
        self.assertEqual(anime.pin_order, 1)

    def test_save_pin_order_rejects_other_user(self):
        """Cannot reorder another user's items."""
        other_user = get_user_model().objects.create_user(
            username="other", password="12345"
        )
        anime = Anime.objects.create(
            item=self.anime_item,
            user=other_user,
            status=Status.PLANNING.value,
            pin_order=0,
        )
        self.client.post(
            reverse("save_pin_order"),
            json.dumps([{"media_type": "anime", "id": anime.id}]),
            content_type="application/json",
        )
        anime.refresh_from_db()
        self.assertEqual(anime.pin_order, 0)

    def test_backlog_save_pin_toggle(self):
        """is_pinned checkbox in inline edit toggles pin_order."""
        anime = Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.PLANNING.value,
        )
        data = self._backlog_save_data(anime)
        data["is_pinned"] = "on"
        self.client.post(reverse("backlog_save"), data)
        anime.refresh_from_db()
        self.assertIsNotNone(anime.pin_order)

        data = self._backlog_save_data(anime)
        # is_pinned not in POST = unpin
        self.client.post(reverse("backlog_save"), data)
        anime.refresh_from_db()
        self.assertIsNone(anime.pin_order)

    def test_backlog_save_pin_change_triggers_refresh(self):
        """Pin change via backlog_save triggers HX-Refresh."""
        anime = Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.PLANNING.value,
        )
        data = self._backlog_save_data(anime)
        data["is_pinned"] = "on"
        response = self.client.post(reverse("backlog_save"), data)
        self.assertEqual(response["HX-Refresh"], "true")

    def test_pin_icon_visible_for_planning(self):
        """Pin toggle button appears on Planning cards."""
        Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.PLANNING.value,
        )
        response = self.client.get(reverse("home"))
        self.assertContains(response, "toggle_pin")

    def test_pin_icon_hidden_for_in_progress(self):
        """Pin toggle button does not appear on In Progress cards."""
        Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "toggle_pin")

    def test_pinned_order_across_media_types(self):
        """Pin order is globally unique per user across media types."""
        anime = Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.PLANNING.value,
        )
        self.client.post(
            reverse("toggle_pin"),
            {"media_type": "anime", "instance_id": anime.id},
        )
        anime.refresh_from_db()
        first_order = anime.pin_order

        manga = Manga.objects.create(
            item=self.manga_item,
            user=self.user,
            status=Status.PLANNING.value,
        )
        self.client.post(
            reverse("toggle_pin"),
            {"media_type": "manga", "instance_id": manga.id},
        )
        manga.refresh_from_db()
        self.assertGreater(manga.pin_order, first_order)


class SeasonCollapsingTests(TestCase):
    """Tests for automatic collapsing of multiple seasons in Planning."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)
        patcher = patch(
            "app.providers.services.get_media_metadata",
            return_value={
                "max_progress": None,
                "title": "Mock Show",
                "image": "http://example.com/mock.jpg",
                "details": {"seasons": 1},
                "related": {"seasons": []},
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _create_season(self, media_id, season_number, title, **kwargs):
        item = Item.objects.create(
            media_id=media_id,
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title=title,
            image=_DEFAULT_IMAGE,
            season_number=season_number,
        )
        return Season.objects.create(
            item=item,
            user=self.user,
            status=Status.PLANNING.value,
            **kwargs,
        )

    def test_multiple_seasons_collapsed(self):
        """S1, S2, S3 in Planning collapse to S1 with collapsed_seasons."""
        self._create_season("show-1", 1, "Show X")
        self._create_season("show-1", 2, "Show X")
        self._create_season("show-1", 3, "Show X")

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        season_items = _collect_season_items(groups)

        show_items = [m for m in season_items if m.item.media_id == "show-1"]
        self.assertEqual(len(show_items), 1)
        representative = show_items[0]
        self.assertEqual(representative.item.season_number, 1)
        self.assertEqual(len(representative.collapsed_seasons), 2)

    def test_single_season_not_collapsed(self):
        """Single season renders normally without collapsed_seasons."""
        self._create_season("show-2", 1, "Show Y")

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        season_items = []
        for group in groups:
            for sg in group["status_groups"]:
                season_items.extend(
                    m
                    for m in sg["items"]
                    if m.item.media_type == MediaTypes.SEASON.value
                )

        show_items = [m for m in season_items if m.item.media_id == "show-2"]
        self.assertEqual(len(show_items), 1)
        self.assertEqual(show_items[0].collapsed_seasons, [])

    def test_pinned_season_not_collapsed(self):
        """Pinned season appears independently, rest are collapsed."""
        self._create_season("show-3", 1, "Show Z")
        self._create_season("show-3", 2, "Show Z")
        self._create_season("show-3", 3, "Show Z", pin_order=0)

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        pinned_seasons = []
        rest_seasons = []
        for group in groups:
            for sg in group["status_groups"]:
                rest_seasons.extend(
                    m
                    for m in sg["items"]
                    if m.item.media_type == MediaTypes.SEASON.value
                )
                if "pinned_items" in sg:
                    pinned_seasons.extend(
                        m
                        for m in sg["pinned_items"]
                        if m.item.media_type == MediaTypes.SEASON.value
                    )

        pinned_show = [m for m in pinned_seasons if m.item.media_id == "show-3"]
        rest_show = [m for m in rest_seasons if m.item.media_id == "show-3"]

        self.assertEqual(len(pinned_show), 1)
        self.assertEqual(pinned_show[0].item.season_number, 3)

        self.assertEqual(len(rest_show), 1)
        self.assertEqual(rest_show[0].item.season_number, 1)
        self.assertEqual(len(rest_show[0].collapsed_seasons), 1)

    def test_collapse_only_in_planning(self):
        """In Progress seasons are not collapsed."""
        s1 = self._create_season("show-4", 1, "Show W")
        s1.status = Status.IN_PROGRESS.value
        s1.save()
        s2 = self._create_season("show-4", 2, "Show W")
        s2.status = Status.IN_PROGRESS.value
        s2.save()

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        ip_seasons = []
        for group in groups:
            for sg in group["status_groups"]:
                if sg["status"] == Status.IN_PROGRESS.value:
                    ip_seasons.extend(
                        m
                        for m in sg["items"]
                        if m.item.media_type == MediaTypes.SEASON.value
                    )

        show_items = [m for m in ip_seasons if m.item.media_id == "show-4"]
        self.assertEqual(len(show_items), 2)

    def test_collapse_badge_in_template(self):
        """Collapsed seasons show '+N more seasons' badge in rendered HTML."""
        self._create_season("show-5", 1, "Show V")
        self._create_season("show-5", 2, "Show V")
        self._create_season("show-5", 3, "Show V")

        response = self.client.get(reverse("home"))
        self.assertContains(response, "+2 more seasons")


def _collect_season_items(groups):
    """Extract all Season-type media items from backlog groups."""
    season_items = []
    for group in groups:
        for sg in group["status_groups"]:
            season_items.extend(
                m for m in sg["items"] if m.item.media_type == MediaTypes.SEASON.value
            )
            if "pinned_items" in sg:
                season_items.extend(
                    m
                    for m in sg["pinned_items"]
                    if m.item.media_type == MediaTypes.SEASON.value
                )
    return season_items
