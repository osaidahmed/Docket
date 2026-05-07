from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import Anime, Item, MediaTypes, Sources, Status


class MediaListPinnedTests(TestCase):
    """Tests for pinned items on the media list page."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.anime_item_a = Item.objects.create(
            media_id="ml-pin-1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Alpha Anime",
            image="http://example.com/a.jpg",
        )
        cls.anime_item_b = Item.objects.create(
            media_id="ml-pin-2",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Beta Anime",
            image="http://example.com/b.jpg",
        )
        cls.anime_item_c = Item.objects.create(
            media_id="ml-pin-3",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Charlie Anime",
            image="http://example.com/c.jpg",
        )

    def setUp(self):
        self.client.login(**self.credentials)
        patcher = patch(
            "app.providers.services.get_media_metadata",
            return_value={"max_progress": None},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_pinned_items_separate_from_paginated(self):
        """Pinned items appear in pinned_list, not in paginated media_list."""
        Anime.objects.create(
            item=self.anime_item_a,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=0,
        )
        Anime.objects.create(
            item=self.anime_item_b,
            user=self.user,
            status=Status.PLANNING.value,
        )
        response = self.client.get(
            reverse("medialist", args=["anime"]) + "?status=Planning"
        )
        pinned = response.context["pinned_list"]
        media_list = response.context["media_list"]
        self.assertEqual(len(pinned), 1)
        self.assertEqual(pinned[0].item.title, "Alpha Anime")
        paginated_titles = [m.item.title for m in media_list]
        self.assertNotIn("Alpha Anime", paginated_titles)
        self.assertIn("Beta Anime", paginated_titles)

    def test_pinned_list_filters_to_in_progress(self):
        """pinned_list contains only In Progress pinned items when filter is In Progress."""
        Anime.objects.create(
            item=self.anime_item_a,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            pin_order=0,
        )
        Anime.objects.create(
            item=self.anime_item_b,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=1,
        )
        response = self.client.get(
            reverse("medialist", args=["anime"]) + "?status=In+progress"
        )
        pinned = response.context["pinned_list"]
        self.assertEqual(len(pinned), 1)
        self.assertEqual(pinned[0].item.title, "Alpha Anime")

    def test_pinned_list_filters_to_completed(self):
        """pinned_list contains only Completed pinned items when filter is Completed."""
        Anime.objects.create(
            item=self.anime_item_a,
            user=self.user,
            status=Status.COMPLETED.value,
            pin_order=0,
        )
        Anime.objects.create(
            item=self.anime_item_b,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=1,
        )
        response = self.client.get(
            reverse("medialist", args=["anime"]) + "?status=Completed"
        )
        pinned = response.context["pinned_list"]
        self.assertEqual(len(pinned), 1)
        self.assertEqual(pinned[0].item.title, "Alpha Anime")

    def test_pinned_list_under_all_filter_shows_all_pinned(self):
        """With status=All, pinned_list contains pinned items from any status."""
        Anime.objects.create(
            item=self.anime_item_a,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=0,
        )
        Anime.objects.create(
            item=self.anime_item_b,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            pin_order=1,
        )
        response = self.client.get(reverse("medialist", args=["anime"]) + "?status=All")
        pinned = response.context["pinned_list"]
        titles = {p.item.title for p in pinned}
        self.assertEqual(titles, {"Alpha Anime", "Beta Anime"})

    def test_pinned_section_renders_in_template(self):
        """Pinned section header appears in rendered HTML."""
        Anime.objects.create(
            item=self.anime_item_a,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=0,
        )
        response = self.client.get(
            reverse("medialist", args=["anime"]) + "?status=Planning"
        )
        self.assertContains(response, "Pinned")
        self.assertContains(response, "save_pin_order")

    def test_pinned_order_respected(self):
        """Pinned items appear in pin_order."""
        Anime.objects.create(
            item=self.anime_item_a,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=1,
        )
        Anime.objects.create(
            item=self.anime_item_b,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=0,
        )
        response = self.client.get(
            reverse("medialist", args=["anime"]) + "?status=Planning"
        )
        pinned = response.context["pinned_list"]
        self.assertEqual(len(pinned), 2)
        self.assertEqual(pinned[0].item.title, "Beta Anime")
        self.assertEqual(pinned[1].item.title, "Alpha Anime")

    def test_pin_toggle_on_media_list_card(self):
        """Pin toggle button appears on Planning cards in media list."""
        Anime.objects.create(
            item=self.anime_item_a,
            user=self.user,
            status=Status.PLANNING.value,
        )
        response = self.client.get(
            reverse("medialist", args=["anime"]) + "?status=Planning"
        )
        self.assertContains(response, "toggle_pin")

    def test_pin_toggle_visible_for_non_planning(self):
        """Pin toggle button appears on non-Planning cards too."""
        Anime.objects.create(
            item=self.anime_item_a,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        response = self.client.get(
            reverse("medialist", args=["anime"]) + "?status=In+progress"
        )
        self.assertContains(response, "toggle_pin")

    def test_rest_count_header(self):
        """Shows 'N more planning items' when pinned items exist."""
        Anime.objects.create(
            item=self.anime_item_a,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=0,
        )
        Anime.objects.create(
            item=self.anime_item_b,
            user=self.user,
            status=Status.PLANNING.value,
        )
        Anime.objects.create(
            item=self.anime_item_c,
            user=self.user,
            status=Status.PLANNING.value,
        )
        response = self.client.get(
            reverse("medialist", args=["anime"]) + "?status=Planning"
        )
        self.assertContains(response, "2 more planning items")

    def test_only_pinned_no_empty_state(self):
        """When all items are pinned, empty state does not show."""
        Anime.objects.create(
            item=self.anime_item_a,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=0,
        )
        response = self.client.get(
            reverse("medialist", args=["anime"]) + "?status=Planning"
        )
        self.assertNotContains(response, "No Anime Tracked Yet")
        self.assertContains(response, "Alpha Anime")


class MediaListRestCountHeaderTests(TestCase):
    """The 'N more <status> items' header must reflect the active filter."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.item_a = Item.objects.create(
            media_id="hdr-1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="A1",
            image="http://example.com/a.jpg",
        )
        cls.item_b = Item.objects.create(
            media_id="hdr-2",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="A2",
            image="http://example.com/b.jpg",
        )
        cls.item_c = Item.objects.create(
            media_id="hdr-3",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="A3",
            image="http://example.com/c.jpg",
        )

    def setUp(self):
        self.client.login(**self.credentials)
        patcher = patch(
            "app.providers.services.get_media_metadata",
            return_value={"max_progress": None},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_header_reflects_completed_filter(self):
        """Header reads 'N more completed items' when status=Completed."""
        Anime.objects.create(
            item=self.item_a,
            user=self.user,
            status=Status.COMPLETED.value,
            pin_order=0,
        )
        Anime.objects.create(
            item=self.item_b,
            user=self.user,
            status=Status.COMPLETED.value,
        )
        response = self.client.get(
            reverse("medialist", args=["anime"]) + "?status=Completed"
        )
        self.assertContains(response, "more completed item")
        self.assertNotContains(response, "more planning item")

    def test_header_reflects_in_progress_filter(self):
        """Header reads 'N more in progress items' when status=In progress."""
        Anime.objects.create(
            item=self.item_a,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            pin_order=0,
        )
        Anime.objects.create(
            item=self.item_b,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        response = self.client.get(
            reverse("medialist", args=["anime"]) + "?status=In+progress"
        )
        self.assertContains(response, "more in progress item")
        self.assertNotContains(response, "more planning item")

    def test_header_reflects_planning_filter(self):
        """Header reads 'N more planning items' when status=Planning."""
        Anime.objects.create(
            item=self.item_a,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=0,
        )
        Anime.objects.create(
            item=self.item_b,
            user=self.user,
            status=Status.PLANNING.value,
        )
        response = self.client.get(
            reverse("medialist", args=["anime"]) + "?status=Planning"
        )
        self.assertContains(response, "more planning item")

    def test_header_omits_status_for_all_filter(self):
        """Header reads 'N more items' when status=All (no status word)."""
        Anime.objects.create(
            item=self.item_a,
            user=self.user,
            status=Status.PLANNING.value,
            pin_order=0,
        )
        Anime.objects.create(
            item=self.item_b,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        response = self.client.get(reverse("medialist", args=["anime"]) + "?status=All")
        self.assertContains(response, "more item")
        self.assertNotContains(response, "more planning item")
        self.assertNotContains(response, "more in progress item")
        self.assertNotContains(response, "more all item")


class MediaListStatusFilterRedirectTests(TestCase):
    """HTMX status-filter switches must trigger a full reload to refresh page chrome."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)
        cls.item_in_progress = Item.objects.create(
            media_id="rdr-1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="InProgress",
            image="http://example.com/a.jpg",
        )
        cls.item_planning = Item.objects.create(
            media_id="rdr-2",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Planning",
            image="http://example.com/b.jpg",
        )

    def setUp(self):
        self.client.login(**self.credentials)
        patcher = patch(
            "app.providers.services.get_media_metadata",
            return_value={"max_progress": None},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_changing_status_triggers_full_reload(self):
        """Switching status filter via HTMX returns HX-Redirect for full reload."""
        Anime.objects.create(
            item=self.item_planning,
            user=self.user,
            status=Status.PLANNING.value,
        )
        response = self.client.get(
            reverse("medialist", args=["anime"]) + "?status=In+progress",
            HTTP_HX_REQUEST="true",
            HTTP_HX_CURRENT_URL="http://testserver/medialist/anime?status=Planning",
        )
        self.assertIn("HX-Redirect", response.headers)

    def test_no_redirect_when_status_unchanged(self):
        """Sort changes within same status do not trigger full reload."""
        Anime.objects.create(
            item=self.item_in_progress,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        response = self.client.get(
            reverse("medialist", args=["anime"]) + "?status=In+progress&sort=title",
            HTTP_HX_REQUEST="true",
            HTTP_HX_CURRENT_URL="http://testserver/medialist/anime?status=In+progress",
        )
        self.assertNotIn("HX-Redirect", response.headers)

    def test_redirect_when_pinned_present_in_destination(self):
        """If destination filter has pinned items, full reload to render chrome."""
        Anime.objects.create(
            item=self.item_in_progress,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            pin_order=0,
        )
        response = self.client.get(
            reverse("medialist", args=["anime"]) + "?status=In+progress",
            HTTP_HX_REQUEST="true",
            HTTP_HX_CURRENT_URL="http://testserver/medialist/anime?status=In+progress",
        )
        self.assertIn("HX-Redirect", response.headers)
