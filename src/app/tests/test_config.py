from django.test import SimpleTestCase

from app.config import (
    get_explore_filters,
    get_property,
    get_sample_search_url,
    get_status_property,
    get_unit,
    has_explore_filters,
    is_announced_media,
)
from app.models import MediaTypes, Status


class IsAnnouncedMediaTests(SimpleTestCase):
    """Test is_announced_media() against various provider statuses."""

    def test_upcoming_is_announced(self):
        self.assertTrue(is_announced_media({"details": {"status": "Upcoming"}}))

    def test_announced_is_announced(self):
        self.assertTrue(is_announced_media({"details": {"status": "Announced"}}))

    def test_in_production_is_announced(self):
        self.assertTrue(is_announced_media({"details": {"status": "In Production"}}))

    def test_post_production_is_announced(self):
        self.assertTrue(is_announced_media({"details": {"status": "Post Production"}}))

    def test_planned_is_announced(self):
        self.assertTrue(is_announced_media({"details": {"status": "Planned"}}))

    def test_rumored_is_announced(self):
        self.assertTrue(is_announced_media({"details": {"status": "Rumored"}}))

    def test_released_is_not_announced(self):
        self.assertFalse(is_announced_media({"details": {"status": "Released"}}))

    def test_airing_is_not_announced(self):
        self.assertFalse(is_announced_media({"details": {"status": "Airing"}}))

    def test_finished_is_not_announced(self):
        self.assertFalse(is_announced_media({"details": {"status": "Finished"}}))

    def test_empty_status_is_not_announced(self):
        self.assertFalse(is_announced_media({"details": {"status": ""}}))

    def test_missing_details_is_not_announced(self):
        self.assertFalse(is_announced_media({}))

    def test_missing_status_is_not_announced(self):
        self.assertFalse(is_announced_media({"details": {}}))


class ConfigHelperTests(SimpleTestCase):
    """Test config helper functions for coverage gaps."""

    def test_has_explore_filters_episode_type(self):
        self.assertFalse(has_explore_filters(MediaTypes.EPISODE.value))

    def test_has_explore_filters_movie_type(self):
        self.assertTrue(has_explore_filters(MediaTypes.MOVIE.value))

    def test_get_property_missing_raises(self):
        with self.assertRaises(KeyError):
            get_property(MediaTypes.MOVIE.value, "nonexistent_property")

    def test_get_sample_search_url_season(self):
        url = get_sample_search_url(MediaTypes.SEASON.value)
        self.assertIn("media_type=tv", url)
        self.assertIn("Breaking+Bad", url)

    def test_get_unit_no_unit_type(self):
        self.assertEqual(get_unit(MediaTypes.MOVIE.value, short=True), "")
        self.assertEqual(get_unit(MediaTypes.MOVIE.value, short=False), "")

    def test_get_unit_with_unit_type(self):
        self.assertEqual(get_unit(MediaTypes.ANIME.value, short=True), "E")
        self.assertEqual(get_unit(MediaTypes.ANIME.value, short=False), "Episode")

    def test_get_status_property_invalid_status(self):
        with self.assertRaises(KeyError):
            get_status_property("nonexistent_status", "text_color")

    def test_get_status_property_invalid_property(self):
        with self.assertRaises(KeyError):
            get_status_property(Status.COMPLETED.value, "nonexistent_property")


class MinScorePresetButtonsTests(SimpleTestCase):
    """Test that min_score filter uses preset_buttons type."""

    def _get_min_score_filter(self, media_type):
        filters = get_explore_filters(media_type)
        return next(f for f in filters if f["key"] == "min_score")

    def test_movie_min_score_is_preset_buttons(self):
        f = self._get_min_score_filter(MediaTypes.MOVIE.value)
        self.assertEqual(f["type"], "preset_buttons")

    def test_min_score_has_presets_list(self):
        f = self._get_min_score_filter(MediaTypes.MOVIE.value)
        self.assertIn("presets", f)
        self.assertGreater(len(f["presets"]), 0)

    def test_min_score_presets_include_any(self):
        f = self._get_min_score_filter(MediaTypes.MOVIE.value)
        values = [p["value"] for p in f["presets"]]
        self.assertIn("", values)
