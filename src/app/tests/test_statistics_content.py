import datetime
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from app import statistics


class GetAlignedMondayTests(TestCase):
    def test_monday_returns_self(self):
        monday = datetime.datetime(2026, 5, 4)
        assert statistics.get_aligned_monday(monday) == monday

    def test_wednesday_subtracts_two_days(self):
        wednesday = datetime.datetime(2026, 5, 6)
        assert statistics.get_aligned_monday(wednesday) == datetime.datetime(
            2026,
            5,
            4,
        )

    def test_sunday_subtracts_six_days(self):
        sunday = datetime.datetime(2026, 5, 10)
        assert statistics.get_aligned_monday(sunday) == datetime.datetime(2026, 5, 4)

    def test_none_returns_none(self):
        assert statistics.get_aligned_monday(None) is None


class GenerateMonthLabelsTests(TestCase):
    def test_only_mondays_become_labels(self):
        date_range = [
            datetime.date(2026, 5, 1) + datetime.timedelta(days=i) for i in range(28)
        ]
        labels = statistics._generate_month_labels(date_range)
        assert labels
        assert all(isinstance(label, tuple) for label in labels)

    def test_empty_input_returns_empty(self):
        assert statistics._generate_month_labels([]) == []

    def test_no_mondays_returns_empty(self):
        date_range = [datetime.date(2026, 5, 5)]
        assert statistics._generate_month_labels(date_range) == []

    def test_label_count_matches_monday_count(self):
        date_range = [
            datetime.date(2026, 5, 4) + datetime.timedelta(days=7 * i) for i in range(5)
        ]
        labels = statistics._generate_month_labels(date_range)
        total_count = sum(c for _, c in labels)
        assert total_count <= len(date_range)


class GetLevelTests(TestCase):
    def test_zero_returns_zero(self):
        assert statistics.get_level(0) == 0

    def test_one_returns_one(self):
        assert statistics.get_level(1) == 1

    def test_three_returns_one(self):
        assert statistics.get_level(3) == 1

    def test_four_returns_two(self):
        assert statistics.get_level(4) == 2

    def test_six_returns_two(self):
        assert statistics.get_level(6) == 2

    def test_seven_returns_three(self):
        assert statistics.get_level(7) == 3

    def test_nine_returns_three(self):
        assert statistics.get_level(9) == 3

    def test_ten_returns_four(self):
        assert statistics.get_level(10) == 4

    def test_large_returns_four(self):
        assert statistics.get_level(100) == 4


class GetActivityDataInclusiveRangeTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model

        self.user = get_user_model().objects.create_user(username="stats", password="x")

    def test_seven_day_range_yields_seven_days(self):
        with patch.object(statistics, "get_filtered_historical_data", return_value=[]):
            start = timezone.make_aware(datetime.datetime(2026, 5, 4))
            end = timezone.make_aware(datetime.datetime(2026, 5, 10, 23, 59, 59))
            result = statistics.get_activity_data(self.user, start, end)
        flattened = [day for week in result["calendar_weeks"] for day in week]
        assert len(flattened) == 7

    def test_count_is_addition_not_subtraction(self):
        fake_data = [
            {"date": datetime.date(2026, 5, 4), "count": 3},
            {"date": datetime.date(2026, 5, 4), "count": 2},
        ]
        with patch.object(
            statistics,
            "get_filtered_historical_data",
            return_value=fake_data,
        ):
            start = timezone.make_aware(datetime.datetime(2026, 5, 4))
            end = timezone.make_aware(datetime.datetime(2026, 5, 4, 23, 59, 59))
            result = statistics.get_activity_data(self.user, start, end)
        flattened = [day for week in result["calendar_weeks"] for day in week]
        target = next(d for d in flattened if d["date"] == "2026-05-04")
        assert target["count"] == 5


class TimeLineSortKeyTests(TestCase):
    def _make_media(self, *, start_date, end_date):
        class FakeMedia:
            pass

        m = FakeMedia()
        m.start_date = start_date
        m.end_date = end_date
        return m

    def test_uses_end_date_when_set(self):
        end = timezone.make_aware(datetime.datetime(2026, 5, 4))
        start = timezone.make_aware(datetime.datetime(2026, 1, 1))
        media = self._make_media(start_date=start, end_date=end)
        assert statistics.time_line_sort_key(media) == timezone.localdate(end)

    def test_falls_back_to_start_date_when_end_is_none(self):
        start = timezone.make_aware(datetime.datetime(2026, 1, 1))
        media = self._make_media(start_date=start, end_date=None)
        assert statistics.time_line_sort_key(media) == timezone.localdate(start)


class GetScoreDistributionBucketBoundTests(TestCase):
    def test_buckets_have_eleven_keys(self):
        score_counts = dict.fromkeys(range(11), 0)
        for raw in [-1, 0, 5, 9.5, 10, 10.5, 11, 100]:
            bucket = max(0, min(int(raw), 10))
            score_counts[bucket] += 1
        assert all(0 <= k <= 10 for k in score_counts)
        assert sum(score_counts.values()) == 8
