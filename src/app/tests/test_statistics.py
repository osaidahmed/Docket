import datetime
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from app import statistics
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

User = get_user_model()


def _create_item(media_id, media_type, title, **kwargs):
    kwargs.setdefault("source", Sources.TMDB.value)
    return Item.objects.create(
        media_id=media_id,
        media_type=media_type,
        title=title,
        **kwargs,
    )


def _dt(year, month, day):
    return datetime.datetime(year, month, day, 0, 0, tzinfo=datetime.UTC)


class StatisticsTests(TestCase):
    """Test the statistics module functions."""

    def setUp(self):
        self.credentials = {"username": "testuser", "password": "testpassword"}
        self.user = User.objects.create_user(**self.credentials)
        self._create_tv_fixtures()
        self._create_standalone_media()

    def _create_tv_fixtures(self):
        season_item = _create_item(
            "1668",
            MediaTypes.SEASON.value,
            "Test TV Show",
            season_number=1,
        )
        ep1_item = _create_item(
            "1668",
            MediaTypes.EPISODE.value,
            "Test TV Show",
            season_number=1,
            episode_number=1,
        )
        ep2_item = _create_item(
            "1668",
            MediaTypes.EPISODE.value,
            "Test TV Show",
            season_number=1,
            episode_number=2,
        )

        self.season = Season.objects.create(
            user=self.user,
            item=season_item,
            status=Status.IN_PROGRESS.value,
            score=8.0,
        )
        Episode.objects.create(
            item=ep1_item,
            related_season=self.season,
            end_date=_dt(2025, 1, 1),
        )
        Episode.objects.create(
            item=ep2_item,
            related_season=self.season,
            end_date=_dt(2025, 1, 15),
        )

    def _create_standalone_media(self):
        movie_item = _create_item("238", MediaTypes.MOVIE.value, "Test Movie")
        anime_item = _create_item(
            "437",
            MediaTypes.ANIME.value,
            "Test Anime",
            source=Sources.MAL.value,
        )

        self.movie = Movie.objects.create(
            user=self.user,
            item=movie_item,
            status=Status.PLANNING.value,
            score=7.5,
            start_date=_dt(2025, 2, 1),
            end_date=_dt(2025, 2, 1),
        )
        self.anime = Anime.objects.create(
            user=self.user,
            item=anime_item,
            status=Status.COMPLETED.value,
            score=None,
            start_date=_dt(2025, 3, 1),
            end_date=_dt(2025, 3, 31),
        )

    def test_get_media_type_distribution(self):
        """Test the get_media_type_distribution function."""
        media_count = {
            "total": 3,
            MediaTypes.TV: 1,
            MediaTypes.MOVIE: 1,
            MediaTypes.ANIME: 1,
            MediaTypes.BOOK: 0,
        }

        chart_data = statistics.get_media_type_distribution(media_count)

        self.assertIn("labels", chart_data)
        self.assertIn("datasets", chart_data)
        self.assertEqual(len(chart_data["datasets"]), 1)
        self.assertIn("data", chart_data["datasets"][0])
        self.assertIn("backgroundColor", chart_data["datasets"][0])

        self.assertEqual(len(chart_data["labels"]), 3)
        self.assertEqual(len(chart_data["datasets"][0]["data"]), 3)
        self.assertEqual(len(chart_data["datasets"][0]["backgroundColor"]), 3)
        self.assertNotIn("Book", chart_data["labels"])

    def test_get_status_distribution(self):
        """Test the get_status_distribution function."""
        user_media = {
            MediaTypes.TV.value: TV.objects.filter(user=self.user),
            MediaTypes.MOVIE.value: Movie.objects.filter(user=self.user),
            MediaTypes.ANIME.value: Anime.objects.filter(user=self.user),
        }

        status_distribution = statistics.get_status_distribution(user_media)

        self.assertIn("labels", status_distribution)
        self.assertIn("datasets", status_distribution)
        self.assertIn("total_completed", status_distribution)

        self.assertEqual(len(status_distribution["labels"]), 3)
        self.assertEqual(
            len(status_distribution["datasets"]),
            len(Status.values),
        )
        self.assertEqual(status_distribution["total_completed"], 1)

        completed_dataset = next(
            d
            for d in status_distribution["datasets"]
            if d["label"] == Status.COMPLETED.value
        )
        in_progress_dataset = next(
            d
            for d in status_distribution["datasets"]
            if d["label"] == Status.IN_PROGRESS.value
        )
        planning_dataset = next(
            d
            for d in status_distribution["datasets"]
            if d["label"] == Status.PLANNING.value
        )

        self.assertEqual(completed_dataset["total"], 1)
        self.assertEqual(in_progress_dataset["total"], 1)
        self.assertEqual(planning_dataset["total"], 1)

    def test_get_status_pie_chart_data(self):
        """Test the get_status_pie_chart_data function."""
        status_distribution = {
            "labels": ["TV", "Movie", "Anime"],
            "datasets": [
                {
                    "label": Status.COMPLETED.value,
                    "data": [1, 0, 0],
                    "background_color": "#10b981",
                    "total": 1,
                },
                {
                    "label": Status.IN_PROGRESS.value,
                    "data": [0, 1, 0],
                    "background_color": "#6366f1",
                    "total": 1,
                },
                {
                    "label": Status.PLANNING.value,
                    "data": [0, 0, 1],
                    "background_color": "#3b82f6",
                    "total": 1,
                },
                {
                    "label": Status.PAUSED.value,
                    "data": [0, 0, 0],
                    "background_color": "#f97316",
                    "total": 0,
                },
            ],
            "total_completed": 1,
        }

        chart_data = statistics.get_status_pie_chart_data(status_distribution)

        self.assertIn("labels", chart_data)
        self.assertIn("datasets", chart_data)
        self.assertEqual(len(chart_data["datasets"]), 1)
        self.assertIn("data", chart_data["datasets"][0])
        self.assertIn("backgroundColor", chart_data["datasets"][0])

        self.assertEqual(len(chart_data["labels"]), 3)
        self.assertEqual(len(chart_data["datasets"][0]["data"]), 3)
        self.assertEqual(len(chart_data["datasets"][0]["backgroundColor"]), 3)
        self.assertNotIn(Status.PAUSED.value, chart_data["labels"])

    def test_get_score_distribution(self):
        """Test the get_score_distribution function."""
        TV.objects.filter(user=self.user).update(score=8.5)

        user_media = {
            MediaTypes.TV.value: TV.objects.filter(user=self.user),
            MediaTypes.MOVIE.value: Movie.objects.filter(user=self.user),
            MediaTypes.ANIME.value: Anime.objects.filter(user=self.user),
        }

        score_distribution, top_rated = statistics.get_score_distribution(user_media)

        self.assertIn("labels", score_distribution)
        self.assertIn("datasets", score_distribution)
        self.assertIn("average_score", score_distribution)
        self.assertIn("total_scored", score_distribution)

        self.assertEqual(len(score_distribution["labels"]), 11)
        self.assertEqual(len(score_distribution["datasets"]), 3)
        self.assertEqual(score_distribution["total_scored"], 2)
        self.assertEqual(score_distribution["average_score"], 8.0)

        self.assertEqual(len(top_rated), 2)
        self.assertEqual(top_rated[0].score, 8.5)
        self.assertEqual(top_rated[1].score, 7.5)

    def test_get_status_color(self):
        """Test the get_status_color function."""
        for status in Status.values:
            color = statistics.get_status_color(status)
            self.assertIsNotNone(color)
            self.assertTrue(color.startswith("#"))

    def test_get_timeline(self):
        """Test the get_timeline function."""
        user_media = {
            MediaTypes.TV.value: TV.objects.filter(user=self.user),
            MediaTypes.SEASON.value: Season.objects.filter(user=self.user),
            MediaTypes.MOVIE.value: Movie.objects.filter(user=self.user),
            MediaTypes.ANIME.value: Anime.objects.filter(user=self.user),
        }
        timeline = statistics.get_timeline(user_media)

        self.assertIsInstance(timeline, dict)
        self.assertIn("January 2025", timeline)
        self.assertIn("February 2025", timeline)
        self.assertIn("March 2025", timeline)

        self.assertEqual(len(timeline["January 2025"]), 1)
        self.assertEqual(len(timeline["February 2025"]), 1)
        self.assertEqual(len(timeline["March 2025"]), 1)

        months = list(timeline.keys())
        self.assertEqual(months[0], "March 2025")
        self.assertEqual(months[1], "February 2025")
        self.assertEqual(months[2], "January 2025")

    def test_get_level(self):
        """Test the get_level function."""
        self.assertEqual(statistics.get_level(0), 0)
        self.assertEqual(statistics.get_level(1), 1)
        self.assertEqual(statistics.get_level(3), 1)
        self.assertEqual(statistics.get_level(4), 2)
        self.assertEqual(statistics.get_level(6), 2)
        self.assertEqual(statistics.get_level(7), 3)
        self.assertEqual(statistics.get_level(9), 3)
        self.assertEqual(statistics.get_level(10), 4)
        self.assertEqual(statistics.get_level(20), 4)

    @patch("app.statistics.get_filtered_historical_data")
    def test_get_activity_data(self, mock_get_filtered_data):
        """Test the get_activity_data function."""
        start_date = _dt(2025, 1, 1)
        end_date = _dt(2025, 3, 31)

        mock_get_filtered_data.return_value = [
            {"date": datetime.date(2025, 1, 1), "count": 2},
            {"date": datetime.date(2025, 1, 2), "count": 1},
            {"date": datetime.date(2025, 1, 3), "count": 3},
            {"date": datetime.date(2025, 1, 4), "count": 0},
            {"date": datetime.date(2025, 1, 5), "count": 5},
            {"date": datetime.date(2025, 1, 6), "count": 2},
            {"date": datetime.date(2025, 1, 7), "count": 1},
            {"date": datetime.date(2025, 1, 8), "count": 4},
            {"date": datetime.date(2025, 1, 9), "count": 0},
            {"date": datetime.date(2025, 1, 10), "count": 0},
            {"date": datetime.date(2025, 3, 31), "count": 3},
        ]

        result = statistics.get_activity_data(self.user, start_date, end_date)

        self.assertIn("calendar_weeks", result)
        self.assertIn("months", result)
        self.assertIn("stats", result)

        stats = result["stats"]
        self.assertIn("most_active_day", stats)
        self.assertIn("most_active_day_percentage", stats)
        self.assertIn("current_streak", stats)
        self.assertIn("longest_streak", stats)

        calendar_weeks = result["calendar_weeks"]
        self.assertIsInstance(calendar_weeks, list)

        first_week = calendar_weeks[0]
        self.assertEqual(len(first_week), 7)

        months = result["months"]
        self.assertIsInstance(months, list)

    @patch("app.statistics.BasicMedia.objects.get_historical_models")
    @patch("app.statistics.apps.get_model")
    def test_get_filtered_historical_data(self, mock_get_model, mock_get_hist_models):
        """Test the get_filtered_historical_data function."""
        start = _dt(2025, 1, 1)
        end = _dt(2025, 3, 31)

        mock_get_hist_models.return_value = ["historicalmodel1", "historicalmodel2"]

        def build_fake_model(timestamps):
            qs = MagicMock()
            qs.filter.return_value = qs
            qs.values_list.return_value.iterator.return_value = timestamps
            model = MagicMock()
            model.objects = qs
            return model

        model1_ts = [
            datetime.datetime(2025, 1, 5, 12, tzinfo=datetime.UTC),
            datetime.datetime(2025, 1, 5, 18, tzinfo=datetime.UTC),
            datetime.datetime(2025, 1, 10, 9, tzinfo=datetime.UTC),
            datetime.datetime(2025, 1, 10, 10, tzinfo=datetime.UTC),
            datetime.datetime(2025, 1, 10, 11, tzinfo=datetime.UTC),
        ]
        model2_ts = [
            datetime.datetime(2025, 2, 15, 8, tzinfo=datetime.UTC),
            datetime.datetime(2025, 3, 20, 17, tzinfo=datetime.UTC),
            datetime.datetime(2025, 3, 20, 18, tzinfo=datetime.UTC),
            datetime.datetime(2025, 3, 20, 19, tzinfo=datetime.UTC),
            datetime.datetime(2025, 3, 20, 20, tzinfo=datetime.UTC),
        ]

        fake_model1 = build_fake_model(model1_ts)
        fake_model2 = build_fake_model(model2_ts)
        mock_get_model.side_effect = lambda _, name: (
            fake_model1 if name == "historicalmodel1" else fake_model2
        )

        result = statistics.get_filtered_historical_data(start, end, self.user)

        expected = [
            {"date": datetime.date(2025, 1, 5), "count": 2},
            {"date": datetime.date(2025, 1, 10), "count": 3},
            {"date": datetime.date(2025, 2, 15), "count": 1},
            {"date": datetime.date(2025, 3, 20), "count": 4},
        ]
        self.assertCountEqual(result, expected)

    def test_calculate_day_of_week_stats(self):
        """Test the calculate_day_of_week_stats function."""
        date_counts = {
            datetime.date(2025, 1, 1): 2,
            datetime.date(2025, 1, 2): 1,
            datetime.date(2025, 1, 3): 3,
            datetime.date(2025, 1, 4): 0,
            datetime.date(2025, 1, 5): 5,
            datetime.date(2025, 1, 6): 2,
            datetime.date(2025, 1, 7): 1,
            datetime.date(2025, 1, 8): 4,
            datetime.date(2025, 1, 9): 0,
            datetime.date(2025, 1, 10): 0,
            datetime.date(2025, 1, 12): 5,
            datetime.date(2025, 1, 19): 3,
        }

        start_date = datetime.date(2025, 1, 1)

        most_active_day, percentage = statistics.calculate_day_of_week_stats(
            date_counts,
            start_date,
        )

        self.assertEqual(most_active_day, "Sunday")
        self.assertEqual(percentage, 33)

        most_active_day, percentage = statistics.calculate_day_of_week_stats(
            {},
            start_date,
        )
        self.assertIsNone(most_active_day)
        self.assertEqual(percentage, 0)

    def test_calculate_streaks(self):
        """Test the calculate_streaks function."""
        today = datetime.date(2025, 3, 31)
        yesterday = today - datetime.timedelta(days=1)
        two_days_ago = today - datetime.timedelta(days=2)

        date_counts = {
            today: 1,
            yesterday: 2,
            two_days_ago: 3,
            datetime.date(2025, 3, 27): 0,
            datetime.date(2025, 3, 26): 1,
            datetime.date(2025, 3, 25): 1,
            datetime.date(2025, 3, 24): 1,
            datetime.date(2025, 3, 23): 1,
            datetime.date(2025, 3, 22): 0,
            datetime.date(2025, 3, 21): 1,
        }

        current_streak, longest_streak = statistics.calculate_streaks(
            date_counts,
            today,
        )
        self.assertEqual(current_streak, 3)
        self.assertEqual(longest_streak, 4)

        date_counts = {
            yesterday: 2,
            two_days_ago: 3,
            datetime.date(2025, 3, 27): 0,
            datetime.date(2025, 3, 26): 1,
        }

        current_streak, longest_streak = statistics.calculate_streaks(
            date_counts,
            today,
        )
        self.assertEqual(current_streak, 0)
        self.assertEqual(longest_streak, 2)

        current_streak, longest_streak = statistics.calculate_streaks({}, today)
        self.assertEqual(current_streak, 0)
        self.assertEqual(longest_streak, 0)
