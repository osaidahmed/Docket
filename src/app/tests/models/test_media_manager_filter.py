from app.models import (
    Anime,
    Item,
    MediaTypes,
    Movie,
    Sources,
    Status,
)
from app.services import backlog
from app.tests.models.conftest import MediaManagerTestBase
from users.models import MediaStatusChoices


class MediaManagerFilterTests(MediaManagerTestBase):
    """Test MediaManager filtering, searching, and lookup methods."""

    def test_get_media_list_with_status_filter(self):
        media_list = self._get_media_list(
            MediaTypes.ANIME.value, Status.IN_PROGRESS.value, "score"
        )
        self.assertEqual(len(media_list), 1)
        self.assertEqual(media_list[0], self.anime)

    def test_get_media_list_with_all_status(self):
        media_list = self._get_media_list(
            MediaTypes.ANIME.value, MediaStatusChoices.ALL, "score"
        )
        self.assertEqual(len(media_list), 1)

    def test_get_media_list_with_list_status_filter(self):
        planning_item = Item.objects.create(
            media_id="999",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Planning Anime",
            image="http://example.com/planning.jpg",
        )
        Anime.objects.create(
            item=planning_item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        media_list = self._get_media_list(
            MediaTypes.ANIME.value,
            [Status.IN_PROGRESS.value, Status.COMPLETED.value],
            None,
        )

        statuses = {m.status for m in media_list}
        self.assertIn(Status.IN_PROGRESS.value, statuses)
        self.assertNotIn(Status.PLANNING.value, statuses)

    def test_get_media_list_search_matching(self):
        media_list = self._get_media_list(
            MediaTypes.ANIME.value, MediaStatusChoices.ALL, "score", search="Cowboy"
        )
        self.assertEqual(len(media_list), 1)

    def test_get_media_list_search_no_match(self):
        media_list = self._get_media_list(
            MediaTypes.ANIME.value, MediaStatusChoices.ALL, "score", search="Naruto"
        )
        self.assertEqual(len(media_list), 0)

    def test_get_media_types_to_process_specific(self):
        media_types = backlog._get_media_types_to_process(
            self.user, [MediaTypes.ANIME.value]
        )
        self.assertEqual(media_types, [MediaTypes.ANIME.value])

    def test_get_media_types_to_process_tv_includes_season(self):
        media_types = backlog._get_media_types_to_process(
            self.user, [MediaTypes.TV.value]
        )
        self.assertEqual(media_types, [MediaTypes.TV.value, MediaTypes.SEASON.value])

    def test_get_media_types_to_process_all(self):
        media_types = backlog._get_media_types_to_process(self.user, None)

        for expected in (
            MediaTypes.TV,
            MediaTypes.ANIME,
            MediaTypes.MOVIE,
            MediaTypes.GAME,
            MediaTypes.BOOK,
            MediaTypes.MANGA,
        ):
            self.assertIn(expected.value, media_types)

    def test_get_media_types_to_process_disabled(self):
        for mt in ["anime", "manga"]:
            pref = self.user.get_or_create_media_pref(mt)
            pref.enabled = False
            pref.save(update_fields=["enabled"])
        if hasattr(self.user, "_pref_cache"):
            del self.user._pref_cache

        media_types = backlog._get_media_types_to_process(self.user, None)
        self.assertNotIn(MediaTypes.ANIME.value, media_types)
        self.assertNotIn(MediaTypes.MANGA.value, media_types)
        self.assertIn(MediaTypes.MOVIE.value, media_types)

    def test_get_media(self):
        tv = self.manager.get_media(
            user=self.user,
            media_type=MediaTypes.TV.value,
            instance_id=self.tv.id,
        )
        self.assertEqual(tv, self.tv)

        season = self.manager.get_media(
            user=self.user,
            media_type=MediaTypes.SEASON.value,
            instance_id=self.season1.id,
        )
        self.assertEqual(season, self.season1)

        episode = self.manager.get_media(
            user=self.user,
            media_type=MediaTypes.EPISODE.value,
            instance_id=self.season1.episodes.first().id,
        )
        self.assertIsNotNone(episode)
        self.assertEqual(episode.item.episode_number, 1)

        with self.assertRaises(Movie.DoesNotExist):
            self.manager.get_media(
                user=self.user,
                media_type=MediaTypes.MOVIE.value,
                instance_id=9999,
            )

    def test_filter_media(self):
        tv = self.manager.filter_media(
            user=self.user,
            media_id="1668",
            media_type=MediaTypes.TV.value,
            source=Sources.TMDB.value,
        ).first()
        self.assertEqual(tv, self.tv)

        season = self.manager.filter_media(
            user=self.user,
            media_id="1668",
            media_type=MediaTypes.SEASON.value,
            source=Sources.TMDB.value,
            season_number=1,
        ).first()
        self.assertEqual(season, self.season1)

        episode = self.manager.filter_media(
            user=self.user,
            media_id="1668",
            media_type=MediaTypes.EPISODE.value,
            source=Sources.TMDB.value,
            season_number=1,
            episode_number=1,
        ).first()
        self.assertIsNotNone(episode)
        self.assertEqual(episode.item.episode_number, 1)

        non_existent = self.manager.filter_media(
            user=self.user,
            media_id="9999",
            media_type=MediaTypes.MOVIE.value,
            source=Sources.TMDB.value,
        ).first()
        self.assertIsNone(non_existent)
