from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.utils import timezone

from app import _media_sorting
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
from app.services import backlog
from app.tests.models.conftest import MediaManagerTestBase
from events.models import Event
from users.models import MediaStatusChoices


class MediaManagerSortTests(MediaManagerTestBase):
    """Test MediaManager sorting and ordering methods."""

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

    @classmethod
    def _create_extra_seasons(cls):
        season2_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Friends Season 2",
            image="http://example.com/image.jpg",
            season_number=2,
        )
        season2 = Season.objects.create(
            item=season2_item,
            related_tv=cls.tv,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
            score=7,
        )

        for i in range(1, 3):
            episode_item = Item.objects.create(
                media_id="1668",
                source=Sources.TMDB.value,
                media_type=MediaTypes.EPISODE.value,
                title=f"Friends S2E{i}",
                image="http://example.com/image.jpg",
                season_number=2,
                episode_number=i,
            )
            Episode.objects.create(
                item=episode_item,
                related_season=season2,
                end_date=datetime(2023, 7, i, 0, 0, tzinfo=UTC),
            )

        season3_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Friends Season 3",
            image="http://example.com/image.jpg",
            season_number=3,
        )
        Season.objects.create(
            item=season3_item,
            related_tv=cls.tv,
            user=cls.user,
            status=Status.PLANNING.value,
            score=0,
        )

    def _sorted_seasons(self, sort_field):
        queryset = Season.objects.filter(user=self.user).select_related("item")
        queryset = self.manager._apply_prefetch_related(
            queryset, MediaTypes.SEASON.value
        )
        return list(
            _media_sorting.sort_media_list(
                queryset, sort_field, MediaTypes.SEASON.value
            )
        )

    def _sorted_tv(self, sort_field):
        queryset = TV.objects.filter(user=self.user).select_related("item")
        queryset = self.manager._apply_prefetch_related(queryset, MediaTypes.TV.value)
        return list(
            _media_sorting.sort_media_list(queryset, sort_field, MediaTypes.TV.value)
        )

    @patch.object(Season, "_forward_fill_planning_seasons")
    @patch.object(Season, "_backfill_prior_seasons")
    def test_sort_seasons_by_start_date(self, *_):
        self._create_extra_seasons()
        seasons = self._sorted_seasons("start_date")

        self.assertEqual(seasons[0].item.title, "Friends")
        self.assertEqual(seasons[1].item.title, "Friends Season 2")
        self.assertEqual(seasons[2].item.title, "Friends Season 3")

    @patch.object(Season, "_forward_fill_planning_seasons")
    @patch.object(Season, "_backfill_prior_seasons")
    def test_sort_seasons_by_end_date(self, *_):
        self._create_extra_seasons()
        seasons = self._sorted_seasons("end_date")

        self.assertEqual(seasons[0].item.title, "Friends Season 2")
        self.assertEqual(seasons[1].item.title, "Friends")
        self.assertEqual(seasons[2].item.title, "Friends Season 3")

    @patch.object(Season, "_forward_fill_planning_seasons")
    @patch.object(Season, "_backfill_prior_seasons")
    def test_sort_seasons_by_score(self, *_):
        self._create_extra_seasons()
        seasons = self._sorted_seasons("score")

        self.assertEqual(seasons[0].score, 8)
        self.assertEqual(seasons[1].score, 7)
        self.assertEqual(seasons[2].score, 0)

    @patch.object(Season, "_forward_fill_planning_seasons")
    @patch.object(Season, "_backfill_prior_seasons")
    def test_sort_tv_by_progress(self, *_):
        self._create_extra_seasons()
        tv_shows = self._sorted_tv("progress")
        self.assertEqual(tv_shows[0].item.title, "Friends")

    @patch.object(Season, "_forward_fill_planning_seasons")
    @patch.object(Season, "_backfill_prior_seasons")
    def test_sort_tv_by_start_date(self, *_):
        self._create_extra_seasons()
        tv_shows = self._sorted_tv("start_date")
        self.assertEqual(tv_shows[0].item.title, "Friends")

    @patch.object(Season, "_forward_fill_planning_seasons")
    @patch.object(Season, "_backfill_prior_seasons")
    def test_sort_movies_by_title(self, *_):
        queryset = Movie.objects.filter(user=self.user).select_related("item")
        sorted_movies = _media_sorting.sort_media_list(
            queryset, "title", MediaTypes.MOVIE.value
        )
        self.assertEqual(next(iter(sorted_movies)).item.title, "Fight Club")

    def test_get_media_list_sort_by_item_field(self):
        media_list = self._get_media_list(
            MediaTypes.MOVIE.value, MediaStatusChoices.ALL, "title"
        )
        self.assertEqual(media_list[0], self.movie)

    def test_get_media_list_sort_by_regular_field(self):
        anime_item2 = Item.objects.create(
            media_id="5",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Naruto",
            image="http://example.com/naruto.jpg",
        )
        anime2 = Anime.objects.create(
            item=anime_item2,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            score=6,
        )

        media_list = self._get_media_list(
            MediaTypes.ANIME.value, MediaStatusChoices.ALL, "score"
        )
        self.assertEqual(media_list.first(), self.anime)
        self.assertEqual(media_list.last(), anime2)

    def test_sort_generic_anime_by_start_date_asc(self):
        anime_item2 = Item.objects.create(
            media_id="9001",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Other Anime",
            image="http://example.com/o.jpg",
        )
        Anime.objects.create(
            item=anime_item2,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            score=5,
            start_date=timezone.make_aware(datetime(2010, 1, 1)),
        )
        queryset = Anime.objects.filter(user=self.user).select_related("item")
        result = list(
            _media_sorting.sort_media_list(
                queryset, "start_date", MediaTypes.ANIME.value, "asc"
            )
        )
        self.assertGreater(len(result), 0)

    def test_sort_generic_anime_by_end_date_desc(self):
        queryset = Anime.objects.filter(user=self.user).select_related("item")
        result = list(
            _media_sorting.sort_media_list(
                queryset, "end_date", MediaTypes.ANIME.value, "desc"
            )
        )
        self.assertGreaterEqual(len(result), 0)

    def test_sort_in_progress_media(self):
        anime_list = self._build_in_progress_anime_list()

        sorted_list = backlog._sort_in_progress_media(anime_list, "upcoming")
        self.assertEqual(sorted_list, [anime_list[0], anime_list[2], anime_list[1]])

        sorted_list = backlog._sort_in_progress_media(anime_list, "title")
        self.assertEqual(
            sorted_list,
            sorted(anime_list, key=lambda x: x.item.title.lower()),
        )

        sorted_list = backlog._sort_in_progress_media(anime_list, "completion")
        self.assertEqual(sorted_list, [anime_list[0], anime_list[2], anime_list[1]])

        sorted_list = backlog._sort_in_progress_media(anime_list, "episodes_left")
        self.assertEqual(sorted_list, [anime_list[0], anime_list[2], anime_list[1]])

        sorted_list = backlog._sort_in_progress_media(anime_list, sort_by="recent")
        self.assertEqual(sorted_list, [anime_list[2], anime_list[1], anime_list[0]])

    def _build_in_progress_anime_list(self):
        anime1 = self.anime
        anime1.max_progress = 20
        anime1.progress = 13
        anime1.next_event = Event.objects.filter(item=self.anime_item).first()

        anime_item2 = Item.objects.create(
            media_id="5",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Naruto",
            image="http://example.com/naruto.jpg",
        )
        anime2 = Anime.objects.create(
            item=anime_item2,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            score=6,
            progress=5,
        )
        anime2.max_progress = 100
        anime2.next_event = None

        anime_item3 = Item.objects.create(
            media_id="6",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Attack on Titan",
            image="http://example.com/aot.jpg",
        )
        anime3 = Anime.objects.create(
            item=anime_item3,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            score=9,
            progress=30,
        )
        anime3.max_progress = 50
        anime3.next_event = Event.objects.create(
            item=anime_item3,
            content_number=31,
            datetime=timezone.now() + timedelta(days=10),
            notification_sent=False,
        )

        return [anime1, anime2, anime3]
