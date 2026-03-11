from datetime import UTC, datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import (
    Episode,
    Item,
    MediaTypes,
    Season,
    Sources,
    Status,
)
from users.models import QuickWatchDateChoices


class SeasonGetRemainingEpsQuickWatchDateTests(TestCase):
    """Tests for Season.get_remaining_eps with different quick_watch_date settings."""

    @classmethod
    def setUpTestData(cls):
        with (
            patch.object(Item, "fetch_releases"),
            patch(
                "app.models.providers.services.get_media_metadata",
                return_value={
                    "title": "Friends",
                    "image": "http://example.com/tv.jpg",
                    "details": {"seasons": 1},
                    "related": {"seasons": []},
                },
            ),
        ):
            cls._create_test_data()

    @classmethod
    def _create_test_data(cls):
        cls.QuickWatchDateChoices = QuickWatchDateChoices
        cls.credentials = {"username": "test_quick", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        item_season = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Friends",
            image="http://example.com/image.jpg",
            season_number=1,
        )

        cls.season = Season.objects.create(
            item=item_season,
            user=cls.user,
            status=Status.PLANNING.value,
        )

        cls.mock_metadata = {
            "episodes": [
                {
                    "episode_number": 1,
                    "image": "img1.jpg",
                    "air_date": datetime(1994, 9, 22, tzinfo=UTC),
                },
                {
                    "episode_number": 2,
                    "image": "img2.jpg",
                    "air_date": datetime(1994, 9, 29, tzinfo=UTC),
                },
                {
                    "episode_number": 3,
                    "image": "img3.jpg",
                    "air_date": None,
                },
            ],
            "image": "season_img.jpg",
        }

    @patch("app.models.Season.get_episode_item")
    def test_get_remaining_eps_current_date(self, mock_get_episode_item):
        self.user.quick_watch_date = self.QuickWatchDateChoices.CURRENT_DATE
        self.user.save()

        for i in range(1, 4):
            mock_get_episode_item.return_value = Item.objects.create(
                media_id="1668",
                source=Sources.TMDB.value,
                media_type=MediaTypes.EPISODE.value,
                title=f"Episode {i}",
                image=f"img{i}.jpg",
                season_number=1,
                episode_number=i,
            )

        episodes = self.season.get_remaining_eps(self.mock_metadata)

        for ep in episodes:
            self.assertIsNotNone(ep.end_date)

    @patch("app.models.Season.get_episode_item")
    def test_get_remaining_eps_no_date(self, mock_get_episode_item):
        self.user.quick_watch_date = self.QuickWatchDateChoices.NO_DATE
        self.user.save()

        for i in range(1, 4):
            mock_get_episode_item.return_value = Item.objects.create(
                media_id="1668",
                source=Sources.TMDB.value,
                media_type=MediaTypes.EPISODE.value,
                title=f"Episode {i}",
                image=f"img{i}.jpg",
                season_number=1,
                episode_number=i,
            )

        episodes = self.season.get_remaining_eps(self.mock_metadata)

        for ep in episodes:
            self.assertIsNone(ep.end_date)

    @patch("app.models.Season.get_episode_item")
    def test_get_remaining_eps_release_date(self, mock_get_episode_item):
        self.user.quick_watch_date = self.QuickWatchDateChoices.RELEASE_DATE
        self.user.save()

        episode_items = []
        for i in range(1, 4):
            item = Item.objects.create(
                media_id="1668",
                source=Sources.TMDB.value,
                media_type=MediaTypes.EPISODE.value,
                title=f"Episode {i}",
                image=f"img{i}.jpg",
                season_number=1,
                episode_number=i,
            )
            episode_items.append(item)

        mock_get_episode_item.side_effect = episode_items

        episodes = self.season.get_remaining_eps(self.mock_metadata)

        self.assertIsNone(episodes[0].end_date)
        self.assertEqual(episodes[1].end_date, datetime(1994, 9, 29, tzinfo=UTC))
        self.assertEqual(episodes[2].end_date, datetime(1994, 9, 22, tzinfo=UTC))

    @patch("app.models.providers.services.get_media_metadata")
    def test_season_completion_with_no_date(self, mock_get_metadata):
        self.user.quick_watch_date = self.QuickWatchDateChoices.NO_DATE
        self.user.save()

        mock_get_metadata.return_value = {
            "episodes": [
                {"episode_number": 1, "image": "img1.jpg", "air_date": None},
                {"episode_number": 2, "image": "img2.jpg", "air_date": None},
            ],
            "image": "season_img.jpg",
            "related": {
                "seasons": [{"season_number": 1, "image": "img1.jpg"}],
            },
        }

        self.season.status = Status.COMPLETED.value
        self.season.save()

        episodes = Episode.objects.filter(related_season=self.season)
        self.assertEqual(episodes.count(), 2)
        for ep in episodes:
            self.assertIsNone(ep.end_date)

    @patch("app.models.providers.services.get_media_metadata")
    def test_season_completion_auto_advances_next_season(self, mock_get_metadata):
        mock_get_metadata.return_value = {
            "episodes": [
                {"episode_number": 1, "image": "img1.jpg", "air_date": None},
            ],
            "image": "season_img.jpg",
            "related": {
                "seasons": [
                    {"season_number": 1, "image": "img1.jpg"},
                    {"season_number": 2, "image": "img2.jpg"},
                ],
            },
        }

        tv = self.season.related_tv
        tv.status = Status.IN_PROGRESS.value
        tv.save()

        season2_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Friends",
            image="http://example.com/image.jpg",
            season_number=2,
        )
        season2 = Season.objects.create(
            item=season2_item,
            user=self.user,
            related_tv=tv,
            status=Status.PLANNING.value,
        )

        self.season.status = Status.COMPLETED.value
        self.season.save()

        season2.refresh_from_db()
        self.assertEqual(season2.status, Status.IN_PROGRESS.value)

    @patch("app.models.providers.services.get_media_metadata")
    def test_season_completion_no_advance_if_tv_dropped(self, mock_get_metadata):
        mock_get_metadata.return_value = {
            "episodes": [
                {"episode_number": 1, "image": "img1.jpg", "air_date": None},
            ],
            "image": "season_img.jpg",
            "related": {
                "seasons": [{"season_number": 1, "image": "img1.jpg"}],
            },
        }

        tv = self.season.related_tv
        tv.status = Status.DROPPED.value
        tv.save()

        season2_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Friends",
            image="http://example.com/image.jpg",
            season_number=2,
        )
        season2 = Season.objects.create(
            item=season2_item,
            user=self.user,
            related_tv=tv,
            status=Status.PLANNING.value,
        )

        self.season.status = Status.COMPLETED.value
        self.season.save()

        season2.refresh_from_db()
        self.assertEqual(season2.status, Status.PLANNING.value)

    @patch("app.models.providers.services.get_media_metadata")
    def test_season_completion_no_phantom_season(self, mock_get_metadata):
        mock_get_metadata.return_value = {
            "episodes": [
                {"episode_number": 1, "image": "img1.jpg", "air_date": None},
            ],
            "image": "season_img.jpg",
            "related": {
                "seasons": [
                    {"season_number": 1, "image": "img1.jpg"},
                ],
            },
        }

        tv = self.season.related_tv
        tv.status = Status.IN_PROGRESS.value
        tv.save()

        self.season.status = Status.COMPLETED.value
        self.season.save()

        self.assertEqual(tv.seasons.count(), 1)

    @patch("app.models.providers.services.get_media_metadata")
    def test_season_completion_with_release_date(self, mock_get_metadata):
        self.user.quick_watch_date = self.QuickWatchDateChoices.RELEASE_DATE
        self.user.save()

        mock_get_metadata.return_value = {
            "episodes": [
                {
                    "episode_number": 1,
                    "image": "img1.jpg",
                    "air_date": datetime(1994, 9, 22, tzinfo=UTC),
                },
                {
                    "episode_number": 2,
                    "image": "img2.jpg",
                    "air_date": datetime(1994, 9, 29, tzinfo=UTC),
                },
            ],
            "image": "season_img.jpg",
            "related": {
                "seasons": [{"season_number": 1, "image": "img1.jpg"}],
            },
        }

        self.season.status = Status.COMPLETED.value
        self.season.save()

        episodes = Episode.objects.filter(related_season=self.season).order_by(
            "item__episode_number",
        )
        self.assertEqual(episodes.count(), 2)
        self.assertEqual(episodes[0].end_date, datetime(1994, 9, 22, tzinfo=UTC))
        self.assertEqual(episodes[1].end_date, datetime(1994, 9, 29, tzinfo=UTC))
