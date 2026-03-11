from datetime import timedelta

from django.db.models import Prefetch
from django.utils import timezone

from app.models import (
    TV,
    Anime,
    Item,
    MediaTypes,
    Movie,
    Season,
    Sources,
    Status,
)
from app.services import backlog
from app.tests.models.conftest import MediaManagerTestBase
from events.models import Event
from users.models import MediaStatusChoices


class MediaManagerPrefetchTests(MediaManagerTestBase):
    """Test MediaManager prefetch, annotation, and query optimization methods."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for i in range(4, 7):
            Event.objects.create(
                item=cls.anime_item,
                content_number=i + 13,
                datetime=timezone.now() + timedelta(days=i),
                notification_sent=False,
            )

    def test_get_historical_models(self):
        historical_models = self.manager.get_historical_models()
        expected = [
            f"historical{media_type}" for media_type in MediaTypes.values
        ]
        self.assertEqual(historical_models, expected)

    def _prefetch_for(self, model_cls, media_type):
        queryset = model_cls.objects.filter(user=self.user.id)
        return self.manager._apply_prefetch_related(queryset, media_type)

    def test_apply_prefetch_related_tv(self):
        prefetched = self._prefetch_for(TV, MediaTypes.TV.value)
        self.assertEqual(len(prefetched._prefetch_related_lookups), 2)

    def test_apply_prefetch_related_season(self):
        prefetched = self._prefetch_for(Season, MediaTypes.SEASON.value)
        self.assertEqual(len(prefetched._prefetch_related_lookups), 2)

    def test_apply_prefetch_related_movie(self):
        prefetched = self._prefetch_for(Movie, MediaTypes.MOVIE.value)
        self.assertEqual(len(prefetched._prefetch_related_lookups), 1)

    def _force_evaluate_tv_prefetch(self, tv_list):
        for tv in tv_list:
            for season in tv.seasons.all():
                list(season.episodes.all())

    def test_tv_prefetch_avoids_extra_queries(self):
        tv_list = list(self._get_media_list(
            MediaTypes.TV.value, MediaStatusChoices.ALL, "score"
        ))

        self._force_evaluate_tv_prefetch(tv_list)

        with self.assertNumQueries(0):
            self._force_evaluate_tv_prefetch(tv_list)

    def test_season_prefetch_avoids_extra_queries(self):
        season_list = list(self._get_media_list(
            MediaTypes.SEASON.value, MediaStatusChoices.ALL, "score"
        ))

        for season in season_list:
            list(season.episodes.all())

        with self.assertNumQueries(0):
            for season in season_list:
                list(season.episodes.all())

    def _prefetch_events_for(self, anime_list):
        for anime in anime_list:
            anime.item.prefetched_events = list(
                Event.objects.filter(item=anime.item)
            )

    def test_annotate_next_event_with_future_event(self):
        queryset = Anime.objects.filter(user=self.user.id).select_related("item")
        anime_list = list(queryset)
        self._prefetch_events_for(anime_list)

        backlog.annotate_next_event(anime_list)

        self.assertIsNotNone(anime_list[0].next_event)
        self.assertEqual(anime_list[0].next_event.item, self.anime_item)

    def test_annotate_next_event_with_past_event(self):
        anime_item2 = Item.objects.create(
            media_id="5",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Naruto",
            image="http://example.com/naruto.jpg",
        )
        Anime.objects.create(
            item=anime_item2,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            score=6,
        )
        Event.objects.create(
            item=anime_item2,
            content_number=1,
            datetime=timezone.now() - timedelta(days=1),
            notification_sent=True,
        )

        queryset = Anime.objects.filter(
            user=self.user.id, item=anime_item2
        ).select_related("item")
        anime_list = list(queryset)
        self._prefetch_events_for(anime_list)

        backlog.annotate_next_event(anime_list)

        self.assertIsNone(anime_list[0].next_event)

    def test_annotate_max_progress_movie(self):
        movie_list = list(Movie.objects.filter(user=self.user.id))
        self.manager.annotate_max_progress(movie_list, MediaTypes.MOVIE.value)
        self.assertEqual(movie_list[0].max_progress, 1)

    def test_annotate_max_progress_anime(self):
        anime_list = list(
            Anime.objects.filter(user=self.user.id).select_related("item"),
        )

        Event.objects.create(
            item=self.anime_item,
            content_number=20,
            datetime=timezone.now() - timedelta(days=20),
            notification_sent=True,
        )

        self._prefetch_events_for(anime_list)
        self.manager.annotate_max_progress(anime_list, MediaTypes.ANIME.value)
        self.assertEqual(anime_list[0].max_progress, 20)

    def test_annotate_max_progress_tv(self):
        tv_list = TV.objects.filter(user=self.user.id)

        Event.objects.create(
            item=self.season1_item,
            content_number=10,
            datetime=timezone.now() - timedelta(days=10),
        )

        tv_list = tv_list.prefetch_related(
            Prefetch(
                "seasons__item__event_set",
                queryset=Event.objects.all(),
                to_attr="prefetched_events",
            ),
        )

        self.manager._annotate_tv_released_episodes(tv_list, timezone.now())
        self.assertEqual(tv_list[0].max_progress, 10)
