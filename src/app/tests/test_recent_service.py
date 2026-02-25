from django.test import TestCase, override_settings

from app.services import recent


@override_settings(REDIS_PREFIX=None)
class TrackViewTests(TestCase):
    """Test the recently viewed tracking service."""

    def setUp(self):
        recent.redis_client.flushdb()

    def _make_entry(self, media_type="movie", media_id="1", source="tmdb", **kwargs):
        return {
            "media_type": media_type,
            "media_id": media_id,
            "source": source,
            "title": kwargs.get("title", f"Test {media_type}"),
            "english_title": kwargs.get("english_title", ""),
            "image": kwargs.get("image", "http://example.com/img.jpg"),
        }

    def test_track_view_stores_entry(self):
        entry = self._make_entry()
        recent.track_view(1, entry)

        results = recent.get_recent(1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["media_id"], "1")
        self.assertEqual(results[0]["title"], "Test movie")

    def test_track_view_deduplicates(self):
        entry = self._make_entry()
        recent.track_view(1, entry)
        recent.track_view(1, entry)

        results = recent.get_recent(1)
        self.assertEqual(len(results), 1)

    def test_track_view_preserves_order(self):
        entry_a = self._make_entry(media_id="1", title="First")
        entry_b = self._make_entry(media_id="2", title="Second")
        recent.track_view(1, entry_a)
        recent.track_view(1, entry_b)

        results = recent.get_recent(1)
        self.assertEqual(results[0]["title"], "Second")
        self.assertEqual(results[1]["title"], "First")

    def test_track_view_caps_at_max(self):
        for i in range(25):
            recent.track_view(1, self._make_entry(media_id=str(i)))

        key = recent._key(1)
        length = recent.redis_client.llen(key)
        self.assertEqual(length, recent.MAX_ENTRIES)

    def test_track_view_updates_metadata(self):
        entry = self._make_entry(title="Old Title")
        recent.track_view(1, entry)

        updated = self._make_entry(title="New Title")
        recent.track_view(1, updated)

        results = recent.get_recent(1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "New Title")

    def test_dedup_bumps_to_front(self):
        entry_a = self._make_entry(media_id="1", title="First")
        entry_b = self._make_entry(media_id="2", title="Second")
        recent.track_view(1, entry_a)
        recent.track_view(1, entry_b)

        recent.track_view(1, entry_a)

        results = recent.get_recent(1)
        self.assertEqual(results[0]["title"], "First")
        self.assertEqual(results[1]["title"], "Second")

    def test_separate_users_isolated(self):
        recent.track_view(1, self._make_entry(title="User 1 Movie"))
        recent.track_view(2, self._make_entry(media_id="99", title="User 2 Movie"))

        results_1 = recent.get_recent(1)
        results_2 = recent.get_recent(2)

        self.assertEqual(len(results_1), 1)
        self.assertEqual(results_1[0]["title"], "User 1 Movie")
        self.assertEqual(len(results_2), 1)
        self.assertEqual(results_2[0]["title"], "User 2 Movie")


@override_settings(REDIS_PREFIX=None)
class GetRecentTests(TestCase):
    """Test the recently viewed retrieval service."""

    def setUp(self):
        recent.redis_client.flushdb()

    def _make_entry(self, media_type="movie", media_id="1", source="tmdb", **kwargs):
        return {
            "media_type": media_type,
            "media_id": media_id,
            "source": source,
            "title": kwargs.get("title", f"Test {media_type}"),
            "english_title": kwargs.get("english_title", ""),
            "image": kwargs.get("image", "http://example.com/img.jpg"),
        }

    def test_get_recent_empty(self):
        results = recent.get_recent(1)
        self.assertEqual(results, [])

    def test_get_recent_respects_limit(self):
        for i in range(10):
            recent.track_view(1, self._make_entry(media_id=str(i)))

        results = recent.get_recent(1, limit=5)
        self.assertEqual(len(results), 5)

    def test_get_recent_filters_by_media_type(self):
        recent.track_view(1, self._make_entry(media_type="movie", media_id="1"))
        recent.track_view(1, self._make_entry(media_type="anime", media_id="2"))

        results = recent.get_recent(1, media_type_filter="anime")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["media_type"], "anime")

    def test_get_recent_filter_all_returns_everything(self):
        recent.track_view(1, self._make_entry(media_type="movie", media_id="1"))
        recent.track_view(1, self._make_entry(media_type="anime", media_id="2"))

        results = recent.get_recent(1, media_type_filter=None)
        self.assertEqual(len(results), 2)

    def test_get_recent_filter_with_insufficient_matches(self):
        for i in range(8):
            recent.track_view(1, self._make_entry(media_type="movie", media_id=str(i)))
        recent.track_view(1, self._make_entry(media_type="anime", media_id="a1"))
        recent.track_view(1, self._make_entry(media_type="anime", media_id="a2"))

        results = recent.get_recent(1, media_type_filter="anime", limit=5)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["media_type"] == "anime" for r in results))

    def test_get_recent_default_limit_is_five(self):
        for i in range(10):
            recent.track_view(1, self._make_entry(media_id=str(i)))

        results = recent.get_recent(1)
        self.assertEqual(len(results), 5)
