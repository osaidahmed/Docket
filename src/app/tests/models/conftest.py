from datetime import UTC, datetime

from django.contrib.auth import get_user_model
from django.test import TestCase

from app.models import (
    TV,
    Anime,
    Book,
    Episode,
    Game,
    Item,
    Manga,
    MediaManager,
    MediaTypes,
    Movie,
    Season,
    Sources,
    Status,
)


class MediaManagerTestBase(TestCase):
    """Shared test fixtures for MediaManager test classes."""

    @classmethod
    def setUpTestData(cls):
        cls.user = cls._create_user()
        cls._create_items()
        cls._create_media_entries()
        cls._create_tv_hierarchy()

    def setUp(self):
        self.manager = MediaManager()

    @classmethod
    def _create_user(cls):
        user = get_user_model().objects.create_user(
            username="test", password="12345"
        )
        for media_type in MediaTypes.values:
            setattr(user, f"{media_type.lower()}_enabled", True)
        user.save()
        return user

    @classmethod
    def _create_items(cls):
        cls.movie_item = Item.objects.create(
            media_id="550",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Fight Club",
            image="http://example.com/fightclub.jpg",
        )
        cls.anime_item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Cowboy Bebop",
            image="http://example.com/bebop.jpg",
        )
        cls.game_item = Item.objects.create(
            media_id="1234",
            source=Sources.IGDB.value,
            media_type=MediaTypes.GAME.value,
            title="The Last of Us",
            image="http://example.com/tlou.jpg",
        )
        cls.book_item = Item.objects.create(
            media_id="OL21733390M",
            source=Sources.OPENLIBRARY.value,
            media_type=MediaTypes.BOOK.value,
            title="1984",
            image="http://example.com/1984.jpg",
        )
        cls.manga_item = Item.objects.create(
            media_id="2",
            source=Sources.MAL.value,
            media_type=MediaTypes.MANGA.value,
            title="Berserk",
            image="http://example.com/berserk.jpg",
        )

    @classmethod
    def _create_media_entries(cls):
        cls.movie = Movie.objects.create(
            item=cls.movie_item,
            user=cls.user,
            status=Status.COMPLETED.value,
            score=9,
        )
        cls.anime = Anime.objects.create(
            item=cls.anime_item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
            score=10,
            progress=13,
        )
        cls.game = Game.objects.create(
            item=cls.game_item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
            score=7,
            progress=120,
        )
        cls.book = Book.objects.create(
            item=cls.book_item,
            user=cls.user,
            status=Status.PLANNING.value,
            score=0,
        )
        cls.manga = Manga.objects.create(
            item=cls.manga_item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
            score=10,
            progress=100,
        )

    @classmethod
    def _create_tv_hierarchy(cls):
        cls.season1_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Friends",
            image="http://example.com/image.jpg",
            season_number=1,
        )
        cls.season1 = Season.objects.create(
            item=cls.season1_item,
            user=cls.user,
            status=Status.IN_PROGRESS.value,
            score=8,
        )
        cls.tv = TV.objects.get(user=cls.user)

        for i in range(1, 5):
            episode_item = Item.objects.create(
                media_id="1668",
                source=Sources.TMDB.value,
                media_type=MediaTypes.EPISODE.value,
                title=f"Friends S1E{i}",
                image="http://example.com/image.jpg",
                season_number=1,
                episode_number=i,
            )
            watched_episodes = 3
            if i <= watched_episodes:
                Episode.objects.create(
                    item=episode_item,
                    related_season=cls.season1,
                    end_date=datetime(2023, 6, i, 0, 0, tzinfo=UTC),
                )

    def _get_media_list(self, media_type, status_filter, sort_filter, **kwargs):
        return self.manager.get_media_list(
            user=self.user,
            media_type=media_type,
            status_filter=status_filter,
            sort_filter=sort_filter,
            **kwargs,
        )
