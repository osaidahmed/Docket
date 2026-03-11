import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from app import statistics
from app.models import (
    Episode,
    Item,
    MediaTypes,
    Movie,
    Season,
    Sources,
    Status,
)

User = get_user_model()


def _create_item(media_id, media_type, title, **kwargs):
    return Item.objects.create(
        media_id=media_id,
        source=Sources.TMDB.value,
        media_type=media_type,
        title=title,
        **kwargs,
    )


def _create_movie(user, item, status, **kwargs):
    return Movie.objects.create(user=user, item=item, status=status, **kwargs)


def _dt(year, month, day):
    return datetime.datetime(year, month, day, 0, 0, tzinfo=datetime.UTC)


class StatisticsDateFilteringTests(TestCase):
    """Test the date filtering functionality in the statistics module."""

    def setUp(self):
        self.credentials = {"username": "testuser", "password": "testpassword"}
        self.user = User.objects.create_user(**self.credentials)
        self._create_tv_fixtures()
        self._create_movie_fixtures()

    def _create_tv_fixtures(self):
        season_item = _create_item(
            "1668", MediaTypes.SEASON.value, "Test TV Show", season_number=1,
        )
        ep1_item = _create_item(
            "1668", MediaTypes.EPISODE.value, "Test TV Show",
            season_number=1, episode_number=1,
        )
        ep2_item = _create_item(
            "1668", MediaTypes.EPISODE.value, "Test TV Show",
            season_number=1, episode_number=2,
        )

        self.season = Season.objects.create(
            user=self.user, item=season_item,
            status=Status.IN_PROGRESS.value, score=8.0,
        )
        Episode.objects.create(
            item=ep1_item, related_season=self.season,
            end_date=_dt(2025, 1, 1),
        )
        Episode.objects.create(
            item=ep2_item, related_season=self.season,
            end_date=_dt(2025, 1, 15),
        )

    def _create_movie_fixtures(self):
        specs = [
            ("238", "Movie with start and end dates", Status.COMPLETED.value,
             {"score": 7.5, "start_date": _dt(2025, 2, 10), "end_date": _dt(2025, 2, 10)}),
            ("239", "Movie with only start date", Status.IN_PROGRESS.value,
             {"score": 8.0, "start_date": _dt(2025, 2, 15)}),
            ("240", "Movie with only end date", Status.COMPLETED.value,
             {"score": 6.5, "end_date": _dt(2025, 2, 20)}),
            ("241", "Movie with no dates", Status.PLANNING.value, {}),
            ("242", "Movie outside date range (before)", Status.COMPLETED.value,
             {"score": 9.0, "start_date": _dt(2025, 1, 10), "end_date": _dt(2025, 1, 15)}),
            ("243", "Movie outside date range (after)", Status.PLANNING.value,
             {"start_date": _dt(2025, 3, 10), "end_date": _dt(2025, 3, 15)}),
            ("244", "Movie partially in range (starts before, ends in range)",
             Status.COMPLETED.value,
             {"score": 7.0, "start_date": _dt(2025, 1, 25), "end_date": _dt(2025, 2, 5)}),
            ("245", "Movie partially in range (starts in range, ends after)",
             Status.COMPLETED.value,
             {"score": 8.5, "start_date": _dt(2025, 2, 25), "end_date": _dt(2025, 3, 5)}),
        ]

        self.movie_items = {}
        for media_id, title, status, kwargs in specs:
            item = _create_item(media_id, MediaTypes.MOVIE.value, title)
            _create_movie(self.user, item, status, **kwargs)
            self.movie_items[media_id] = item

    def _get_movie_ids(self, user_media):
        return [m.item.id for m in user_media[MediaTypes.MOVIE.value]]

    def _assert_outside_movie_excluded(self, media_id, status, **movie_kwargs):
        outside_item = _create_item(media_id, MediaTypes.MOVIE.value, "Outside range")
        _create_movie(self.user, outside_item, status, **movie_kwargs)

        user_media, _ = statistics.get_user_media(
            self.user, _dt(2025, 2, 10), _dt(2025, 2, 20),
        )
        movie_ids = self._get_movie_ids(user_media)
        self.assertNotIn(outside_item.id, movie_ids)

    def test_all_time_filtering(self):
        """Test when no date filtering is applied (All Time)."""
        _, media_count = statistics.get_user_media(self.user, None, None)

        self.assertEqual(media_count["total"], 10)
        self.assertEqual(media_count[MediaTypes.TV.value], 1)
        self.assertEqual(media_count[MediaTypes.SEASON.value], 1)
        self.assertEqual(media_count[MediaTypes.MOVIE.value], 8)

    def test_date_range_filtering(self):
        """Test filtering with a specific date range."""
        user_media, media_count = statistics.get_user_media(
            self.user, _dt(2025, 2, 1), _dt(2025, 2, 28),
        )

        self.assertEqual(media_count[MediaTypes.TV.value], 0)
        self.assertEqual(media_count[MediaTypes.SEASON.value], 0)
        self.assertEqual(media_count[MediaTypes.MOVIE.value], 5)
        self.assertEqual(media_count["total"], 5)

        movie_ids = self._get_movie_ids(user_media)
        for mid in ("238", "239", "240", "244", "245"):
            self.assertIn(self.movie_items[mid].id, movie_ids)
        for mid in ("241", "242", "243"):
            self.assertNotIn(self.movie_items[mid].id, movie_ids)

    def test_both_dates_filtering(self):
        """Test filtering for media with both start and end dates."""
        user_media, _ = statistics.get_user_media(
            self.user, _dt(2025, 2, 5), _dt(2025, 2, 15),
        )

        movie_ids = self._get_movie_ids(user_media)
        self.assertIn(self.movie_items["238"].id, movie_ids)
        self.assertIn(self.movie_items["244"].id, movie_ids)
        self.assertNotIn(self.movie_items["242"].id, movie_ids)
        self.assertNotIn(self.movie_items["243"].id, movie_ids)

    def test_start_date_only_filtering(self):
        """Test filtering for media with only start date."""
        user_media, _ = statistics.get_user_media(
            self.user, _dt(2025, 2, 10), _dt(2025, 2, 20),
        )
        movie_ids = self._get_movie_ids(user_media)
        self.assertIn(self.movie_items["239"].id, movie_ids)

        self._assert_outside_movie_excluded(
            "246", Status.IN_PROGRESS.value, start_date=_dt(2025, 3, 1),
        )

    def test_end_date_only_filtering(self):
        """Test filtering for media with only end date."""
        user_media, _ = statistics.get_user_media(
            self.user, _dt(2025, 2, 10), _dt(2025, 2, 20),
        )
        movie_ids = self._get_movie_ids(user_media)
        self.assertIn(self.movie_items["240"].id, movie_ids)

        self._assert_outside_movie_excluded(
            "247", Status.COMPLETED.value, end_date=_dt(2025, 3, 1),
        )

    def test_no_dates_filtering(self):
        """Test that media with no dates is excluded from date-filtered results."""
        user_media, _ = statistics.get_user_media(
            self.user, _dt(2025, 2, 1), _dt(2025, 2, 28),
        )
        movie_ids = self._get_movie_ids(user_media)
        self.assertNotIn(self.movie_items["241"].id, movie_ids)

        user_media, _ = statistics.get_user_media(self.user, None, None)
        movie_ids = self._get_movie_ids(user_media)
        self.assertIn(self.movie_items["241"].id, movie_ids)

    def test_overlapping_ranges(self):
        """Test media with date ranges that overlap with the filter range."""
        start_date = _dt(2025, 2, 1)
        end_date = _dt(2025, 2, 28)

        user_media, _ = statistics.get_user_media(self.user, start_date, end_date)
        movie_ids = self._get_movie_ids(user_media)

        self.assertIn(self.movie_items["244"].id, movie_ids)
        self.assertIn(self.movie_items["245"].id, movie_ids)

        spanning_item = _create_item(
            "248", MediaTypes.MOVIE.value, "Movie that spans the entire range",
        )
        _create_movie(
            self.user, spanning_item, Status.COMPLETED.value,
            start_date=_dt(2025, 1, 15), end_date=_dt(2025, 3, 15),
        )

        user_media, _ = statistics.get_user_media(self.user, start_date, end_date)
        movie_ids = self._get_movie_ids(user_media)
        self.assertIn(spanning_item.id, movie_ids)
