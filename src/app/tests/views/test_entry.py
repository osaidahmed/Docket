from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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


class CreateEntryViewTests(TestCase):
    """Test the create entry view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def test_create_entry_get(self):
        """Test the GET method of create_entry view."""
        response = self.client.get(reverse("create_entry"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/create_entry.html")
        self.assertIn("media_types", response.context)

        media_types = response.context["media_types"]
        for mt in self.user.get_enabled_media_types():
            self.assertIn(mt, media_types)

    def test_create_entry_get_includes_season_episode_when_tv_enabled(self):
        """Test that season and episode types are included when TV is enabled."""
        self.user.tv_enabled = True
        self.user.save()

        response = self.client.get(reverse("create_entry"))
        media_types = response.context["media_types"]

        self.assertIn(MediaTypes.TV.value, media_types)
        self.assertIn(MediaTypes.SEASON.value, media_types)
        self.assertIn(MediaTypes.EPISODE.value, media_types)

        tv_idx = media_types.index(MediaTypes.TV.value)
        season_idx = media_types.index(MediaTypes.SEASON.value)
        episode_idx = media_types.index(MediaTypes.EPISODE.value)
        self.assertEqual(season_idx, tv_idx + 1)
        self.assertEqual(episode_idx, tv_idx + 2)

    def test_create_entry_get_excludes_season_episode_when_tv_disabled(self):
        """Test that season and episode types are excluded when TV is disabled."""
        self.user.tv_enabled = False
        self.user.save()

        response = self.client.get(reverse("create_entry"))
        media_types = response.context["media_types"]

        self.assertNotIn(MediaTypes.TV.value, media_types)
        self.assertNotIn(MediaTypes.SEASON.value, media_types)
        self.assertNotIn(MediaTypes.EPISODE.value, media_types)

    def test_create_entry_get_respects_disabled_types(self):
        """Test that disabled media types are excluded."""
        self.user.anime_enabled = False
        self.user.save()

        response = self.client.get(reverse("create_entry"))
        media_types = response.context["media_types"]

        self.assertNotIn(MediaTypes.ANIME.value, media_types)
        self.assertIn(MediaTypes.MOVIE.value, media_types)

    def test_create_entry_post_movie(self):
        """Test creating a movie entry."""
        form_data = {
            "title": "Test Movie",
            "media_type": MediaTypes.MOVIE.value,
            "status": Status.COMPLETED.value,
            "score": 8,
            "progress": 1,
            "start_date": "2023-01-01T00:00",
            "end_date": "2023-01-02T00:00",
        }

        response = self.client.post(reverse("create_entry"), form_data, follow=True)

        self.assertRedirects(response, reverse("create_entry"))

        self.assertTrue(
            Item.objects.filter(
                title="Test Movie",
                media_type=MediaTypes.MOVIE.value,
            ).exists(),
        )

        movie = Movie.objects.get(item__title="Test Movie")
        self.assertEqual(movie.status, Status.COMPLETED.value)
        self.assertEqual(movie.score, 8)
        self.assertEqual(movie.progress, 1)
        self.assertEqual(movie.user, self.user)

    def test_create_entry_post_tv(self):
        """Test creating a TV show entry."""
        form_data = {
            "title": "Test TV Show",
            "media_type": MediaTypes.TV.value,
            "status": Status.IN_PROGRESS.value,
            "score": 7,
        }

        response = self.client.post(reverse("create_entry"), form_data, follow=True)

        self.assertRedirects(response, reverse("create_entry"))

        self.assertTrue(
            Item.objects.filter(
                title="Test TV Show",
                media_type=MediaTypes.TV.value,
            ).exists(),
        )

        tv = TV.objects.get(item__title="Test TV Show")
        self.assertEqual(tv.status, Status.IN_PROGRESS.value)
        self.assertEqual(tv.score, 7)
        self.assertEqual(tv.user, self.user)

    def test_create_entry_post_season(self):
        """Test creating a season entry with parent TV."""
        tv_item = Item.objects.create(
            media_id="1",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.TV.value,
            title="TV Show",
        )
        parent_tv = TV.objects.create(
            item=tv_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        form_data = {
            "title": "TV Show",
            "media_type": MediaTypes.SEASON.value,
            "season_number": 1,
            "parent_tv": parent_tv.id,
            "status": Status.IN_PROGRESS.value,
            "score": 7,
        }

        response = self.client.post(reverse("create_entry"), form_data, follow=True)

        self.assertRedirects(response, reverse("create_entry"))

        self.assertTrue(
            Item.objects.filter(
                title="TV Show",
                media_type=MediaTypes.SEASON.value,
                season_number=1,
            ).exists(),
        )

        season = Season.objects.get(item__title="TV Show")
        self.assertEqual(season.status, Status.IN_PROGRESS.value)
        self.assertEqual(season.score, 7)
        self.assertEqual(season.user, self.user)
        self.assertEqual(season.related_tv, parent_tv)

    def test_create_entry_post_episode(self):
        """Test creating an episode entry with parent season."""
        tv_item = Item.objects.create(
            media_id="1",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.TV.value,
            title="TV Show",
        )
        parent_tv = TV.objects.create(
            item=tv_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        season_item = Item.objects.create(
            media_id="1",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.SEASON.value,
            title="TV Show",
            season_number=1,
        )
        parent_season = Season.objects.create(
            item=season_item,
            user=self.user,
            related_tv=parent_tv,
            status=Status.IN_PROGRESS.value,
        )

        form_data = {
            "title": "TV Show",
            "media_type": MediaTypes.EPISODE.value,
            "season_number": 1,
            "episode_number": 1,
            "parent_season": parent_season.id,
            "end_date": "2023-01-02T00:00",
        }

        response = self.client.post(reverse("create_entry"), form_data, follow=True)

        self.assertRedirects(response, reverse("create_entry"))

        self.assertTrue(
            Item.objects.filter(
                title="TV Show",
                media_type=MediaTypes.EPISODE.value,
                season_number=1,
                episode_number=1,
            ).exists(),
        )

        episode = Episode.objects.get(item__title="TV Show")
        self.assertEqual(episode.related_season, parent_season)
        end_date_local = timezone.localtime(episode.end_date)
        self.assertEqual(end_date_local.strftime("%Y-%m-%d %H:%M"), "2023-01-02 00:00")

    def test_create_entry_post_duplicate_item(self):
        """Test creating a duplicate item."""
        tv_item = Item.objects.create(
            media_id="1",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.TV.value,
            title="TV Show",
        )
        parent_tv = TV.objects.create(
            item=tv_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        season_item = Item.objects.create(
            media_id="1",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.SEASON.value,
            title="TV Show",
            season_number=1,
        )
        Season.objects.create(
            item=season_item,
            user=self.user,
            related_tv=parent_tv,
            status=Status.IN_PROGRESS.value,
        )

        initial_count = Item.objects.count()

        form_data = {
            "title": "TV Show",
            "media_type": MediaTypes.SEASON.value,
            "season_number": 1,
            "parent_tv": parent_tv.id,
            "status": Status.IN_PROGRESS.value,
            "score": 7,
            "repeats": 0,
        }

        with transaction.atomic():
            self.client.post(reverse("create_entry"), form_data)

        self.assertEqual(Item.objects.count(), initial_count)

    def test_create_entry_post_anime_with_link(self):
        """Test creating an anime entry with link."""
        form_data = {
            "title": "Test Anime",
            "media_type": MediaTypes.ANIME.value,
            "status": Status.IN_PROGRESS.value,
            "score": 8,
            "progress": 5,
            "link": "https://example.com/watch",
        }
        response = self.client.post(reverse("create_entry"), form_data, follow=True)
        self.assertRedirects(response, reverse("create_entry"))
        anime = Anime.objects.get(item__title="Test Anime")
        self.assertEqual(anime.link, "https://example.com/watch")

    def test_create_entry_post_movie_with_is_rewatch(self):
        """Test creating a movie entry with is_rewatch."""
        form_data = {
            "title": "Rewatch Movie",
            "media_type": MediaTypes.MOVIE.value,
            "status": Status.COMPLETED.value,
            "is_rewatch": "on",
        }
        response = self.client.post(reverse("create_entry"), form_data, follow=True)
        self.assertRedirects(response, reverse("create_entry"))
        movie = Movie.objects.get(item__title="Rewatch Movie")
        self.assertTrue(movie.is_rewatch)

    def test_create_entry_post_anime_with_caught_up(self):
        """Test creating an anime entry with caught_up."""
        form_data = {
            "title": "Caught Up Anime",
            "media_type": MediaTypes.ANIME.value,
            "status": Status.IN_PROGRESS.value,
            "progress": 10,
            "caught_up": "on",
        }
        response = self.client.post(reverse("create_entry"), form_data, follow=True)
        self.assertRedirects(response, reverse("create_entry"))
        anime = Anime.objects.get(item__title="Caught Up Anime")
        self.assertTrue(anime.caught_up)

    def test_create_entry_post_with_english_title(self):
        """Test creating an anime entry with english_title."""
        form_data = {
            "title": "Shingeki no Kyojin",
            "english_title": "Attack on Titan",
            "media_type": MediaTypes.ANIME.value,
            "status": Status.IN_PROGRESS.value,
            "progress": 0,
        }
        response = self.client.post(reverse("create_entry"), form_data, follow=True)
        self.assertRedirects(response, reverse("create_entry"))
        item = Item.objects.get(title="Shingeki no Kyojin")
        self.assertEqual(item.english_title, "Attack on Titan")

    def test_create_entry_post_with_synopsis(self):
        """Test creating a movie entry with synopsis."""
        form_data = {
            "title": "Synopsis Movie",
            "synopsis": "A great film about testing.",
            "media_type": MediaTypes.MOVIE.value,
            "status": Status.COMPLETED.value,
        }
        response = self.client.post(reverse("create_entry"), form_data, follow=True)
        self.assertRedirects(response, reverse("create_entry"))
        item = Item.objects.get(title="Synopsis Movie")
        self.assertEqual(item.synopsis, "A great film about testing.")

    def test_create_entry_post_movie_without_progress(self):
        """Test that movie creation works without progress field."""
        form_data = {
            "title": "No Progress Movie",
            "media_type": MediaTypes.MOVIE.value,
            "status": Status.COMPLETED.value,
            "score": 9,
        }
        response = self.client.post(reverse("create_entry"), form_data, follow=True)
        self.assertRedirects(response, reverse("create_entry"))
        movie = Movie.objects.get(item__title="No Progress Movie")
        self.assertEqual(movie.score, 9)
