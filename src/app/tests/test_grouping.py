from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import (
    Anime,
    Item,
    ItemRelationship,
    MediaTypes,
    RelationType,
    Season,
    Sources,
    Status,
)
from app.services.grouping import group_media_list

_IMG = "http://example.com/image.jpg"


def _make_item(media_id, source, media_type, **kwargs):
    kwargs.setdefault("title", "Test")
    kwargs.setdefault("image", _IMG)
    return Item.objects.create(
        media_id=media_id,
        source=source,
        media_type=media_type,
        **kwargs,
    )


def _assert_stub_title_updated(test_case, media_id, initial_title, expected_title):
    _make_item(media_id, Sources.MAL.value, MediaTypes.ANIME.value, title=initial_title)
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


class TVSeasonGroupingTests(TestCase):
    """Test TV season grouping logic in the grouping service."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="grouptest", password="12345", group_related_media=True
        )

    def setUp(self):
        patcher = patch(
            "app.providers.services.get_media_metadata",
            return_value={
                "max_progress": None,
                "title": "Mock Show",
                "image": _IMG,
                "details": {"seasons": 1, "episodes": 10},
                "related": {"seasons": []},
                "episodes": [],
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _make_season(self, media_id, season_num, status=Status.PLANNING.value):
        item = _make_item(
            media_id,
            Sources.TMDB.value,
            MediaTypes.SEASON.value,
            title=f"Show {media_id}",
            season_number=season_num,
        )
        return Season.objects.create(item=item, user=self.user, status=status)

    def test_single_season_not_grouped(self):
        s1 = self._make_season("show-a", 1)
        result = group_media_list([s1], MediaTypes.SEASON.value)
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0].is_group)

    def test_two_seasons_same_show_grouped(self):
        s1 = self._make_season("show-b", 1)
        s2 = self._make_season("show-b", 2)
        result = group_media_list([s1, s2], MediaTypes.SEASON.value)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].is_group)
        self.assertEqual(result[0].group_count, 2)

    def test_three_seasons_grouped_sorted_by_season_number(self):
        s3 = self._make_season("show-c", 3)
        s1 = self._make_season("show-c", 1)
        s2 = self._make_season("show-c", 2)
        result = group_media_list([s3, s1, s2], MediaTypes.SEASON.value)
        self.assertEqual(len(result), 1)
        group = result[0]
        self.assertEqual(group.item.season_number, 1)
        self.assertEqual([g.item.season_number for g in group.group_items], [2, 3])

    def test_different_shows_not_grouped_together(self):
        s1 = self._make_season("show-d", 1)
        s2 = self._make_season("show-e", 1)
        result = group_media_list([s1, s2], MediaTypes.SEASON.value)
        self.assertEqual(len(result), 2)
        self.assertFalse(result[0].is_group)
        self.assertFalse(result[1].is_group)

    def test_mixed_shows_grouped_separately(self):
        s1a = self._make_season("show-f", 1)
        s1b = self._make_season("show-f", 2)
        s2a = self._make_season("show-g", 1)
        result = group_media_list([s1a, s1b, s2a], MediaTypes.SEASON.value)
        groups = [r for r in result if r.is_group]
        singles = [r for r in result if not r.is_group]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0].group_count, 2)
        self.assertEqual(len(singles), 1)

    def test_representative_is_most_active_status(self):
        s1 = self._make_season("show-h", 1, Status.COMPLETED.value)
        s2 = self._make_season("show-h", 2, Status.IN_PROGRESS.value)
        s3 = self._make_season("show-h", 3, Status.PLANNING.value)
        result = group_media_list([s1, s2, s3], MediaTypes.SEASON.value)
        rep = result[0]
        self.assertTrue(rep.is_group)
        self.assertEqual(rep.status, Status.IN_PROGRESS.value)

    def test_representative_tiebreak_by_season_number(self):
        s2 = self._make_season("show-i", 2, Status.PLANNING.value)
        s1 = self._make_season("show-i", 1, Status.PLANNING.value)
        result = group_media_list([s2, s1], MediaTypes.SEASON.value)
        rep = result[0]
        self.assertEqual(rep.item.season_number, 1)

    def test_empty_list(self):
        result = group_media_list([], MediaTypes.SEASON.value)
        self.assertEqual(result, [])

    def test_non_groupable_media_type_passes_through(self):
        item = Item.objects.create(
            media_id="movie-1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="A Movie",
            image=_IMG,
        )
        from app.models import Movie

        movie = Movie.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )
        result = group_media_list([movie], MediaTypes.MOVIE.value)
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0].is_group)


class AnimeGroupingTests(TestCase):
    """Test anime grouping via ItemRelationship connected components."""

    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="animegroup", password="12345", group_related_media=True
        )

    def setUp(self):
        patcher = patch(
            "app.providers.services.get_media_metadata",
            return_value={"max_progress": None},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _make_anime(self, media_id, title="Anime", status=Status.PLANNING.value):
        item = _make_item(
            media_id, Sources.MAL.value, MediaTypes.ANIME.value, title=title
        )
        return Anime.objects.create(item=item, user=self.user, status=status)

    def _make_item_only(self, media_id, title="Stub"):
        """Create an Item without a Media entry (untracked stub)."""
        return _make_item(
            media_id, Sources.MAL.value, MediaTypes.ANIME.value, title=title
        )

    def _relate(self, from_item, to_item, rel_type=RelationType.SEQUEL):
        ItemRelationship.objects.create(
            from_item=from_item, to_item=to_item, relation_type=rel_type
        )

    def test_no_relationships_no_grouping(self):
        a1 = self._make_anime("a1", "Anime 1")
        a2 = self._make_anime("a2", "Anime 2")
        result = group_media_list([a1, a2], MediaTypes.ANIME.value)
        self.assertEqual(len(result), 2)
        self.assertFalse(result[0].is_group)
        self.assertFalse(result[1].is_group)

    def test_direct_sequel_grouped(self):
        a1 = self._make_anime("b1", "Anime B1")
        a2 = self._make_anime("b2", "Anime B2")
        self._relate(a1.item, a2.item, RelationType.SEQUEL)
        result = group_media_list([a1, a2], MediaTypes.ANIME.value)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].is_group)
        self.assertEqual(result[0].group_count, 2)

    def test_direct_prequel_grouped(self):
        a1 = self._make_anime("c1", "Anime C1")
        a2 = self._make_anime("c2", "Anime C2")
        self._relate(a1.item, a2.item, RelationType.PREQUEL)
        result = group_media_list([a1, a2], MediaTypes.ANIME.value)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].is_group)

    def test_chain_through_untracked_item(self):
        """A -> B (untracked) -> C: A and C should be grouped."""
        a1 = self._make_anime("d1", "Anime D1")
        stub = self._make_item_only("d2", "Untracked D2")
        a3 = self._make_anime("d3", "Anime D3")
        self._relate(a1.item, stub, RelationType.SEQUEL)
        self._relate(stub, a3.item, RelationType.SEQUEL)
        result = group_media_list([a1, a3], MediaTypes.ANIME.value)
        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].is_group)
        self.assertEqual(result[0].group_count, 2)

    def test_untracked_stub_not_in_group_items(self):
        """Untracked items should not appear in group_items."""
        a1 = self._make_anime("e1", "Anime E1")
        stub = self._make_item_only("e2", "Untracked E2")
        a3 = self._make_anime("e3", "Anime E3")
        self._relate(a1.item, stub, RelationType.SEQUEL)
        self._relate(stub, a3.item, RelationType.SEQUEL)
        result = group_media_list([a1, a3], MediaTypes.ANIME.value)
        group = result[0]
        media_ids = {m.item.media_id for m in group.group_items}
        self.assertNotIn("e2", media_ids)
        # Representative (e1) is excluded from group_items
        self.assertEqual(group.item.media_id, "e1")
        self.assertIn("e3", media_ids)

    def test_single_tracked_in_chain_not_grouped(self):
        """If only one tracked item exists in a chain, no group is formed."""
        a1 = self._make_anime("f1", "Anime F1")
        stub = self._make_item_only("f2", "Untracked F2")
        self._relate(a1.item, stub, RelationType.SEQUEL)
        result = group_media_list([a1], MediaTypes.ANIME.value)
        self.assertEqual(len(result), 1)
        self.assertFalse(result[0].is_group)

    def test_representative_picks_in_progress_over_planning(self):
        a1 = self._make_anime("g1", "Anime G1", Status.PLANNING.value)
        a2 = self._make_anime("g2", "Anime G2", Status.IN_PROGRESS.value)
        self._relate(a1.item, a2.item, RelationType.SEQUEL)
        result = group_media_list([a1, a2], MediaTypes.ANIME.value)
        rep = result[0]
        self.assertEqual(rep.status, Status.IN_PROGRESS.value)

    def test_empty_anime_list(self):
        result = group_media_list([], MediaTypes.ANIME.value)
        self.assertEqual(result, [])

    def test_two_separate_groups(self):
        a1 = self._make_anime("h1", "Group1 A")
        a2 = self._make_anime("h2", "Group1 B")
        a3 = self._make_anime("h3", "Group2 A")
        a4 = self._make_anime("h4", "Group2 B")
        self._relate(a1.item, a2.item, RelationType.SEQUEL)
        self._relate(a3.item, a4.item, RelationType.SEQUEL)
        result = group_media_list([a1, a2, a3, a4], MediaTypes.ANIME.value)
        groups = [r for r in result if r.is_group]
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0].group_count, 2)
        self.assertEqual(groups[1].group_count, 2)

    def test_mixed_grouped_and_ungrouped(self):
        a1 = self._make_anime("i1", "Grouped A")
        a2 = self._make_anime("i2", "Grouped B")
        a3 = self._make_anime("i3", "Standalone")
        self._relate(a1.item, a2.item, RelationType.SEQUEL)
        result = group_media_list([a1, a2, a3], MediaTypes.ANIME.value)
        groups = [r for r in result if r.is_group]
        singles = [r for r in result if not r.is_group]
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(singles), 1)
        self.assertEqual(singles[0].item.media_id, "i3")


class FullFlowRelationshipStubTests(TestCase):
    """Integration tests: relationship saving → adding → listing."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "flowtest", "password": "12345"}
        cls.user = get_user_model().objects.create_user(
            **cls.credentials, group_related_media=True
        )

    def setUp(self):
        self.client.login(**self.credentials)
        patcher = patch(
            "app.providers.services.get_media_metadata",
            return_value={"max_progress": None},
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_stub_with_valid_title_keeps_title_on_tracking(self):
        """Stub with a valid API title is kept when user tracks it."""
        from app.providers.mal import _save_anime_relationships

        main_item = Item.objects.create(
            media_id="9000",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Main Anime",
            image=_IMG,
        )
        Anime.objects.create(
            item=main_item, user=self.user, status=Status.IN_PROGRESS.value
        )

        _save_anime_relationships(
            9000,
            [
                {
                    "media_id": 9001,
                    "title": "Sequel Anime",
                    "image": _IMG,
                    "relation_type": "sequel",
                }
            ],
        )

        stub = Item.objects.get(media_id="9001")
        self.assertEqual(stub.title, "Sequel Anime")

        self.client.post(
            reverse("quick_add"),
            {
                "media_id": "9001",
                "source": Sources.MAL.value,
                "media_type": MediaTypes.ANIME.value,
            },
        )

        stub.refresh_from_db()
        self.assertEqual(
            stub.title,
            "Sequel Anime",
            "Valid stub title should be preserved on tracking",
        )

    def test_stub_with_placeholder_title_updated_on_tracking(self):
        """Stub with placeholder title gets updated from metadata on tracking."""
        _assert_stub_title_updated(self, "9002", "-", "Real Anime Title")

    def test_anime_list_page_does_not_crash_with_grouped_items(self):
        """Anime list page renders without error when grouping is enabled."""
        a1_item = Item.objects.create(
            media_id="8000",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Anime A",
            image=_IMG,
        )
        a2_item = Item.objects.create(
            media_id="8001",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Anime B",
            image=_IMG,
        )
        Anime.objects.create(item=a1_item, user=self.user, status=Status.PLANNING.value)
        Anime.objects.create(item=a2_item, user=self.user, status=Status.PLANNING.value)
        ItemRelationship.objects.create(
            from_item=a1_item,
            to_item=a2_item,
            relation_type=RelationType.SEQUEL,
        )

        response = self.client.get(reverse("medialist", args=["anime"]))
        self.assertEqual(response.status_code, 200)

    def test_anime_list_page_works_with_grouping_off(self):
        """Anime list page renders normally when grouping is off."""
        self.user.group_related_media = False
        self.user.save()

        item = Item.objects.create(
            media_id="8010",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Solo Anime",
            image=_IMG,
        )
        Anime.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        response = self.client.get(reverse("medialist", args=["anime"]))
        self.assertEqual(response.status_code, 200)

        self.user.group_related_media = True
        self.user.save()
