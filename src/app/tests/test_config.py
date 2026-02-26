from django.test import SimpleTestCase

from app.config import is_announced_media


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
