from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import (
    TV,
    Item,
    MediaTypes,
    Season,
    Sources,
    Status,
)


class SeasonAutoFillTests(TestCase):
    """Test auto-fill behavior for backfill and forward-fill of seasons."""

    @classmethod
    def setUpTestData(cls):
        with (
            patch.object(Item, "fetch_releases"),
            patch(
                "app.models.providers.services.get_media_metadata",
            ),
        ):
            cls.user = get_user_model().objects.create_user(
                username="autofill_test",
                password="12345",
            )
            cls.tv_item = Item.objects.create(
                media_id="456",
                source=Sources.TMDB.value,
                media_type=MediaTypes.TV.value,
                title="Test Show",
                image="http://example.com/tv.jpg",
            )
            cls.tv = TV.objects.create(
                item=cls.tv_item,
                user=cls.user,
                status=Status.IN_PROGRESS.value,
            )
            cls.season3_item = Item.objects.create(
                media_id="456",
                source=Sources.TMDB.value,
                media_type=MediaTypes.SEASON.value,
                title="Test Show",
                image="http://example.com/s3.jpg",
                season_number=3,
            )
            cls.season3 = Season.objects.create(
                item=cls.season3_item,
                user=cls.user,
                related_tv=cls.tv,
                status=Status.PLANNING.value,
            )

    def setUp(self):
        patcher = patch.object(Item, "fetch_releases")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _mock_metadata(self, media_type, _media_id, _source, *args):
        if media_type == MediaTypes.TV.value:
            return {
                "related": {
                    "seasons": [
                        {"season_number": i, "image": f"s{i}.jpg"} for i in range(1, 6)
                    ],
                },
            }
        if media_type == "tv_with_seasons":
            season_numbers = args[0]
            return {
                f"season/{sn}": {
                    "image": f"s{sn}.jpg",
                    "episodes": [
                        {"episode_number": j, "image": f"s{sn}e{j}.jpg"}
                        for j in range(1, 3)
                    ],
                }
                for sn in season_numbers
            }
        if media_type == MediaTypes.SEASON.value:
            sn = args[0][0]
            return {
                "image": f"s{sn}.jpg",
                "episodes": [
                    {"episode_number": j, "image": f"s{sn}e{j}.jpg"}
                    for j in range(1, 3)
                ],
            }
        return {}

    @patch("app.models.providers.services.get_media_metadata")
    def test_completing_season3_backfills_prior_seasons(self, mock_get_metadata):
        mock_get_metadata.side_effect = self._mock_metadata

        self.tv.status = Status.DROPPED.value
        self.tv.save()

        self.season3.status = Status.COMPLETED.value
        self.season3.save()

        for sn in [1, 2]:
            season = Season.objects.get(
                item__media_id="456",
                item__season_number=sn,
                user=self.user,
            )
            self.assertEqual(season.status, Status.COMPLETED.value)
            self.assertEqual(season.related_tv, self.tv)
            self.assertEqual(season.episodes.count(), 2)

    @patch("app.models.providers.services.get_media_metadata")
    def test_starting_season3_backfills_prior_seasons(self, mock_get_metadata):
        mock_get_metadata.side_effect = self._mock_metadata

        self.season3.status = Status.IN_PROGRESS.value
        self.season3.save()

        for sn in [1, 2]:
            season = Season.objects.get(
                item__media_id="456",
                item__season_number=sn,
                user=self.user,
            )
            self.assertEqual(season.status, Status.COMPLETED.value)
            self.assertEqual(season.episodes.count(), 2)

    @patch("app.models.providers.services.get_media_metadata")
    def test_completing_season1_does_not_backfill(self, mock_get_metadata):
        mock_get_metadata.side_effect = self._mock_metadata

        season1_item = Item.objects.create(
            media_id="456",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test Show",
            image="http://example.com/s1.jpg",
            season_number=1,
        )
        season1 = Season.objects.create(
            item=season1_item,
            user=self.user,
            related_tv=self.tv,
            status=Status.PAUSED.value,
        )

        self.tv.status = Status.DROPPED.value
        self.tv.save()

        seasons_before = Season.objects.filter(user=self.user).count()

        season1.status = Status.COMPLETED.value
        season1.save()

        self.assertEqual(
            Season.objects.filter(user=self.user).count(),
            seasons_before,
        )

    @patch("app.models.providers.services.get_media_metadata")
    def test_existing_completed_season_not_duplicated(self, mock_get_metadata):
        mock_get_metadata.side_effect = self._mock_metadata

        season1_item = Item.objects.create(
            media_id="456",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test Show",
            image="http://example.com/s1.jpg",
            season_number=1,
        )
        Season.objects.create(
            item=season1_item,
            user=self.user,
            related_tv=self.tv,
            status=Status.COMPLETED.value,
        )

        self.tv.status = Status.DROPPED.value
        self.tv.save()

        self.season3.status = Status.COMPLETED.value
        self.season3.save()

        self.assertEqual(
            Season.objects.filter(
                item__media_id="456",
                item__season_number=1,
                user=self.user,
            ).count(),
            1,
        )
        self.assertTrue(
            Season.objects.filter(
                item__media_id="456",
                item__season_number=2,
                user=self.user,
            ).exists(),
        )

    @patch("app.models.providers.services.get_media_metadata")
    def test_existing_non_completed_season_force_completed(self, mock_get_metadata):
        mock_get_metadata.side_effect = self._mock_metadata

        season2_item = Item.objects.create(
            media_id="456",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test Show",
            image="http://example.com/s2.jpg",
            season_number=2,
        )
        season2 = Season.objects.create(
            item=season2_item,
            user=self.user,
            related_tv=self.tv,
            status=Status.IN_PROGRESS.value,
        )

        self.tv.status = Status.DROPPED.value
        self.tv.save()

        self.season3.status = Status.COMPLETED.value
        self.season3.save()

        season2.refresh_from_db()
        self.assertEqual(season2.status, Status.COMPLETED.value)

    @patch("app.models.providers.services.get_media_metadata")
    def test_paused_does_not_trigger_autofill(self, mock_get_metadata):
        mock_get_metadata.side_effect = self._mock_metadata

        self.season3.status = Status.PAUSED.value
        self.season3.save()

        self.assertEqual(
            Season.objects.filter(user=self.user).count(),
            1,
        )

    @patch("app.models.providers.services.get_media_metadata")
    def test_dropped_does_not_trigger_backfill(self, mock_get_metadata):
        mock_get_metadata.side_effect = self._mock_metadata

        self.season3.status = Status.DROPPED.value
        self.season3.save()

        self.assertEqual(
            Season.objects.filter(user=self.user).count(),
            1,
        )

    @patch("app.models.providers.services.get_media_metadata")
    def test_planning_forward_fills_subsequent_seasons(self, mock_get_metadata):
        mock_get_metadata.side_effect = self._mock_metadata

        season1_item = Item.objects.create(
            media_id="456",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test Show",
            image="http://example.com/s1.jpg",
            season_number=1,
        )
        season1 = Season(
            item=season1_item,
            user=self.user,
            related_tv=self.tv,
        )
        season1.status = Status.PLANNING.value
        season1.save()

        for sn in [2, 4, 5]:
            season = Season.objects.get(
                item__media_id="456",
                item__season_number=sn,
                user=self.user,
            )
            self.assertEqual(season.status, Status.PLANNING.value)

        self.season3.refresh_from_db()
        self.assertEqual(self.season3.status, Status.PLANNING.value)

        for sn in [2, 4, 5]:
            season = Season.objects.get(
                item__media_id="456",
                item__season_number=sn,
                user=self.user,
            )
            self.assertEqual(season.episodes.count(), 0)

    @patch("app.models.providers.services.get_media_metadata")
    def test_forward_fill_does_not_duplicate_existing(self, mock_get_metadata):
        mock_get_metadata.side_effect = self._mock_metadata

        season1_item = Item.objects.create(
            media_id="456",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test Show",
            image="http://example.com/s1.jpg",
            season_number=1,
        )
        season1 = Season(
            item=season1_item,
            user=self.user,
            related_tv=self.tv,
        )
        season1.status = Status.PLANNING.value
        season1.save()

        self.assertEqual(
            Season.objects.filter(
                item__media_id="456",
                item__season_number=3,
                user=self.user,
            ).count(),
            1,
        )

    @patch("app.models.providers.services.get_media_metadata")
    def test_integration_backfill_and_auto_advance(self, mock_get_metadata):
        mock_get_metadata.side_effect = self._mock_metadata

        season4_item = Item.objects.create(
            media_id="456",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Test Show",
            image="http://example.com/s4.jpg",
            season_number=4,
        )
        season4 = Season.objects.create(
            item=season4_item,
            user=self.user,
            related_tv=self.tv,
            status=Status.PLANNING.value,
        )

        self.season3.status = Status.COMPLETED.value
        self.season3.save()

        for sn in [1, 2]:
            season = Season.objects.get(
                item__media_id="456",
                item__season_number=sn,
                user=self.user,
            )
            self.assertEqual(season.status, Status.COMPLETED.value)
            self.assertEqual(season.episodes.count(), 2)

        self.assertEqual(self.season3.episodes.count(), 2)

        season4.refresh_from_db()
        self.assertEqual(season4.status, Status.IN_PROGRESS.value)
