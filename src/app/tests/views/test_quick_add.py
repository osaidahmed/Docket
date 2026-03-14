from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import Anime, Item, MediaTypes, Sources, Status

_IMG = "http://example.com/image.jpg"


def _assert_stub_title_updated(test_case, media_id, initial_title, expected_title):
    Item.objects.create(
        media_id=media_id,
        source=Sources.MAL.value,
        media_type=MediaTypes.ANIME.value,
        title=initial_title,
        image=_IMG,
    )
    with patch(
        "app.providers.services.get_media_metadata",
        return_value={
            "title": expected_title,
            "english_title": "",
            "image": _IMG,
            "synopsis": "",
        },
    ):
        test_case.client.post(
            reverse("quick_add"),
            {
                "media_id": media_id,
                "source": Sources.MAL.value,
                "media_type": MediaTypes.ANIME.value,
            },
        )
    item = Item.objects.get(media_id=media_id)
    test_case.assertEqual(item.title, expected_title)


class QuickAddWithStubItemTests(TestCase):
    """Test that quick_add handles pre-existing stub Items correctly."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "addtest", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def test_quick_add_with_no_existing_item(self):
        """Adding anime when no Item exists creates Item with correct title."""
        with patch(
            "app.providers.services.get_media_metadata",
            return_value={
                "title": "Fresh Anime",
                "english_title": "",
                "image": _IMG,
                "synopsis": "",
            },
        ):
            self.client.post(
                reverse("quick_add"),
                {
                    "media_id": "50001",
                    "source": Sources.MAL.value,
                    "media_type": MediaTypes.ANIME.value,
                },
            )
        item = Item.objects.get(media_id="50001")
        self.assertEqual(item.title, "Fresh Anime")
        anime = Anime.objects.get(item=item, user=self.user)
        self.assertEqual(anime.status, Status.PLANNING.value)

    def test_quick_add_with_existing_stub_updates_title(self):
        """Adding anime when a stub Item exists should use correct title."""
        _assert_stub_title_updated(self, "50002", "-", "Real Anime Title")

    def test_quick_add_with_existing_stub_empty_title_updates(self):
        """Adding anime when a stub with empty title exists should fix it."""
        _assert_stub_title_updated(self, "50003", "", "Corrected Title")

    def test_quick_add_with_properly_titled_item_keeps_title(self):
        """Adding anime when Item exists with proper title preserves it."""
        Item.objects.create(
            media_id="50004",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Proper Title",
            image=_IMG,
        )
        self.client.post(
            reverse("quick_add"),
            {
                "media_id": "50004",
                "source": Sources.MAL.value,
                "media_type": MediaTypes.ANIME.value,
            },
        )
        item = Item.objects.get(media_id="50004")
        self.assertEqual(item.title, "Proper Title")
