from datetime import UTC, datetime, timedelta

from django.test import TestCase

from app.providers.tmdb import process_season

AIRED_CUTOFF = 7
NO_AIR_DATE_CUTOFF = 5


class ProcessSeasonMaxProgressTests(TestCase):
    """Test process_season filters unaired episodes from max_progress."""

    def _make_response(self, episodes):
        return {
            "name": "Season 1",
            "poster_path": "/test.jpg",
            "season_number": 1,
            "overview": "Test season",
            "air_date": "2024-01-01",
            "vote_average": 8.0,
            "episodes": episodes,
        }

    def test_all_aired_episodes(self):
        """All episodes have past air dates — max_progress = last episode number."""
        yesterday = (datetime.now(tz=UTC).date() - timedelta(days=1)).isoformat()
        episodes = [
            {
                "episode_number": i,
                "air_date": yesterday,
                "runtime": 45,
                "vote_count": 10,
                "still_path": None,
                "name": f"Ep {i}",
                "overview": "",
            }
            for i in range(1, 11)
        ]
        result = process_season(self._make_response(episodes))
        self.assertEqual(result["max_progress"], 10)

    def test_some_unaired_episodes(self):
        """7 aired, 3 unaired — max_progress should be 7."""
        yesterday = (datetime.now(tz=UTC).date() - timedelta(days=1)).isoformat()
        tomorrow = (datetime.now(tz=UTC).date() + timedelta(days=1)).isoformat()
        episodes = [
            {
                "episode_number": i,
                "air_date": yesterday if i <= AIRED_CUTOFF else tomorrow,
                "runtime": 45,
                "vote_count": 10,
                "still_path": None,
                "name": f"Ep {i}",
                "overview": "",
            }
            for i in range(1, 11)
        ]
        result = process_season(self._make_response(episodes))
        self.assertEqual(result["max_progress"], AIRED_CUTOFF)

    def test_episodes_with_no_air_date(self):
        """Episodes without air_date should not count toward max_progress."""
        yesterday = (datetime.now(tz=UTC).date() - timedelta(days=1)).isoformat()
        episodes = [
            {
                "episode_number": i,
                "air_date": yesterday if i <= NO_AIR_DATE_CUTOFF else None,
                "runtime": 45,
                "vote_count": 10,
                "still_path": None,
                "name": f"Ep {i}",
                "overview": "",
            }
            for i in range(1, 11)
        ]
        result = process_season(self._make_response(episodes))
        self.assertEqual(result["max_progress"], NO_AIR_DATE_CUTOFF)

    def test_no_aired_episodes(self):
        """All episodes unaired — max_progress should be 0."""
        tomorrow = (datetime.now(tz=UTC).date() + timedelta(days=1)).isoformat()
        episodes = [
            {
                "episode_number": i,
                "air_date": tomorrow,
                "runtime": 45,
                "vote_count": 10,
                "still_path": None,
                "name": f"Ep {i}",
                "overview": "",
            }
            for i in range(1, 4)
        ]
        result = process_season(self._make_response(episodes))
        self.assertEqual(result["max_progress"], 0)

    def test_full_episodes_list_preserved(self):
        """The full episodes list should be preserved regardless of air date."""
        yesterday = (datetime.now(tz=UTC).date() - timedelta(days=1)).isoformat()
        tomorrow = (datetime.now(tz=UTC).date() + timedelta(days=1)).isoformat()
        episodes = [
            {
                "episode_number": i,
                "air_date": yesterday if i <= NO_AIR_DATE_CUTOFF else tomorrow,
                "runtime": 45,
                "vote_count": 10,
                "still_path": None,
                "name": f"Ep {i}",
                "overview": "",
            }
            for i in range(1, 11)
        ]
        result = process_season(self._make_response(episodes))
        self.assertEqual(len(result["episodes"]), 10)
        self.assertEqual(result["max_progress"], NO_AIR_DATE_CUTOFF)
