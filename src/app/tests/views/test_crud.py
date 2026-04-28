import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

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


class CreateMedia(TestCase):
    """Test the creation of media objects through views."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    @override_settings(MEDIA_ROOT=("create_media"))
    def test_create_anime(self):
        """Test the creation of a TV object."""
        Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Test Anime",
            image="http://example.com/image.jpg",
        )
        self.client.post(
            reverse("media_save"),
            {
                "media_id": "1",
                "source": Sources.MAL.value,
                "media_type": MediaTypes.ANIME.value,
                "status": Status.PLANNING.value,
                "progress": 0,
                "repeats": 0,
            },
        )
        self.assertEqual(
            Anime.objects.filter(item__media_id="1", user=self.user).exists(),
            True,
        )

    @override_settings(MEDIA_ROOT=("create_media"))
    def test_create_tv(self):
        """Test the creation of a TV object through views."""
        Item.objects.create(
            media_id="5895",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Friends",
            image="http://example.com/image.jpg",
        )
        self.client.post(
            reverse("media_save"),
            {
                "media_id": "5895",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.TV.value,
                "status": Status.PLANNING.value,
            },
        )
        self.assertEqual(
            TV.objects.filter(item__media_id="5895", user=self.user).exists(),
            True,
        )

    def test_create_season(self):
        """Test the creation of a Season through views."""
        Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Friends",
            image="http://example.com/image.jpg",
            season_number=1,
        )
        self.client.post(
            reverse("media_save"),
            {
                "media_id": "1668",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.SEASON.value,
                "season_number": 1,
                "status": Status.PLANNING.value,
            },
        )
        self.assertEqual(
            Season.objects.filter(item__media_id="1668", user=self.user).exists(),
            True,
        )

    def test_create_episodes(self):
        """Test the creation of Episode through views."""
        self.client.post(
            reverse("episode_save"),
            {
                "media_id": "1668",
                "season_number": 1,
                "episode_number": 1,
                "source": Sources.TMDB.value,
                "date": "2023-06-01T00:00",
            },
        )
        self.assertEqual(
            Episode.objects.filter(
                item__media_id="1668",
                related_season__user=self.user,
                item__episode_number=1,
            ).exists(),
            True,
        )


class EditMedia(TestCase):
    """Test the editing of media objects through views."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    def test_edit_movie_score(self):
        """Test the editing of a movie score."""
        item = Item.objects.create(
            media_id="10494",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Perfect Blue",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=item,
            user=self.user,
            score=9,
            progress=1,
            status=Status.COMPLETED.value,
            notes="Nice",
            start_date=datetime.datetime(2023, 6, 1, 0, 0, tzinfo=datetime.UTC),
            end_date=datetime.datetime(2023, 6, 1, 0, 0, tzinfo=datetime.UTC),
        )

        self.client.post(
            reverse("media_save"),
            {
                "instance_id": movie.id,
                "media_id": "10494",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
                "score": 10,
                "progress": 1,
                "status": Status.COMPLETED.value,
                "notes": "Nice",
            },
        )
        self.assertEqual(Movie.objects.get(item__media_id="10494").score, 10)


class DeleteMedia(TestCase):
    """Test the deletion of media objects through views."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

        self.item_season = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Friends",
            image="http://example.com/image.jpg",
            season_number=1,
        )
        self.season = Season.objects.create(
            item=self.item_season,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        self.item_ep = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            title="Friends",
            image="http://example.com/image.jpg",
            season_number=1,
            episode_number=1,
        )
        self.episode = Episode.objects.create(
            item=self.item_ep,
            related_season=self.season,
            end_date=datetime.datetime(2023, 6, 1, 0, 0, tzinfo=datetime.UTC),
        )

    def test_delete_tv(self):
        """Test the deletion of a tv through views."""
        self.assertEqual(TV.objects.filter(user=self.user).count(), 1)
        tv_obj = TV.objects.get(user=self.user)

        self.client.post(
            reverse("media_delete"),
            data={
                "instance_id": tv_obj.id,
                "media_type": MediaTypes.TV.value,
            },
        )

        self.assertEqual(Movie.objects.filter(user=self.user).count(), 0)

    def test_delete_season(self):
        """Test the deletion of a season through views."""
        self.client.post(
            reverse(
                "media_delete",
            ),
            data={"instance_id": self.season.id, "media_type": MediaTypes.SEASON.value},
        )

        self.assertEqual(Season.objects.filter(user=self.user).count(), 0)
        self.assertEqual(
            Episode.objects.filter(related_season__user=self.user).count(),
            0,
        )

    def test_unwatch_episode(self):
        """Test unwatching of an episode through views."""
        self.client.post(
            reverse("media_delete"),
            data={
                "instance_id": self.episode.id,
                "media_type": MediaTypes.EPISODE.value,
            },
        )

        self.assertEqual(
            Episode.objects.filter(related_season__user=self.user).count(),
            0,
        )

    def test_delete_already_deleted(self):
        instance_id = self.season.id
        self.season.delete()

        response = self.client.post(
            reverse("media_delete"),
            data={
                "instance_id": instance_id,
                "media_type": MediaTypes.SEASON.value,
            },
        )
        self.assertEqual(response.status_code, 302)


class UpdateMediaScore(TestCase):
    def setUp(self):
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

        item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )
        self.movie = Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.COMPLETED.value,
            progress=1,
            score=7,
        )

    def test_update_score(self):
        response = self.client.post(
            reverse(
                "update_media_score",
                kwargs={
                    "media_type": MediaTypes.MOVIE.value,
                    "instance_id": self.movie.id,
                },
            ),
            {"score": "9.5"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["success"], True)
        self.assertEqual(response.json()["score"], 9.5)
        self.movie.refresh_from_db()
        self.assertEqual(self.movie.score, 9.5)


class MediaSaveFormErrors(TestCase):
    def setUp(self):
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    def test_save_with_invalid_form(self):
        Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Test Anime",
            image="http://example.com/image.jpg",
        )
        response = self.client.post(
            reverse("media_save"),
            {
                "media_id": "1",
                "source": Sources.MAL.value,
                "media_type": MediaTypes.ANIME.value,
                "status": "invalid_status",
                "progress": "not_a_number",
                "repeats": 0,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Anime.objects.filter(item__media_id="1", user=self.user).exists(),
        )


class EpisodeSaveInvalidForm(TestCase):
    def setUp(self):
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    def test_episode_save_invalid_form(self):
        response = self.client.post(
            reverse("episode_save"),
            {
                "media_id": "1668",
                "season_number": 1,
                "episode_number": 1,
                "source": Sources.TMDB.value,
                "end_date": "invalid-date",
            },
        )
        self.assertEqual(response.status_code, 400)


class SyncMetadata(TestCase):
    def setUp(self):
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    def test_sync_manual_item(self):
        response = self.client.post(
            reverse(
                "sync_metadata",
                kwargs={
                    "source": Sources.MANUAL.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "media_id": "1",
                },
            ),
            {"next": "/"},
        )
        self.assertEqual(response.status_code, 400)

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_sync_movie(self, mock_fetch, mock_metadata):
        mock_metadata.return_value = {
            "title": "Test Movie",
            "image": "http://example.com/image.jpg",
        }
        mock_fetch.return_value = None

        Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Old Title",
            image="http://example.com/old.jpg",
        )

        response = self.client.post(
            reverse(
                "sync_metadata",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "media_id": "238",
                },
            ),
            {"next": "/"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], "/")

        item = Item.objects.get(media_id="238")
        self.assertEqual(item.title, "Test Movie")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_sync_recently_synced(self, mock_fetch, mock_metadata):
        mock_metadata.return_value = {
            "title": "Test Movie",
            "image": "http://example.com/image.jpg",
        }
        mock_fetch.return_value = None

        from django.core.cache import cache

        cache.set("tmdb_movie_238", "cached_data", 86400)

        response = self.client.post(
            reverse(
                "sync_metadata",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "media_id": "238",
                },
            ),
            {"next": "/"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)
        mock_metadata.assert_not_called()
        cache.delete("tmdb_movie_238")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.providers.tmdb.process_episodes")
    @patch("app.models.Item.fetch_releases")
    def test_sync_season(self, mock_fetch, mock_process, mock_metadata):
        mock_metadata.return_value = {
            "title": "Test TV",
            "image": "http://example.com/image.jpg",
            "episodes": [],
        }
        mock_process.return_value = [
            {
                "episode_number": 1,
                "image": "http://example.com/ep1.jpg",
            },
        ]
        mock_fetch.return_value = None

        Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.SEASON.value,
            title="Old Season",
            image="http://example.com/old.jpg",
            season_number=1,
        )
        Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.EPISODE.value,
            title="Old Title",
            image="http://example.com/old_ep.jpg",
            season_number=1,
            episode_number=1,
        )

        response = self.client.post(
            reverse(
                "sync_metadata",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.SEASON.value,
                    "media_id": "1668",
                    "season_number": 1,
                },
            ),
            {"next": "/"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)

        ep_item = Item.objects.get(
            media_id="1668",
            media_type=MediaTypes.EPISODE.value,
            episode_number=1,
        )
        self.assertEqual(ep_item.image, "http://example.com/ep1.jpg")

    @patch("app.providers.services.get_media_metadata")
    @patch("app.models.Item.fetch_releases")
    def test_sync_no_htmx(self, mock_fetch, mock_metadata):
        mock_metadata.return_value = {
            "title": "Test Movie",
            "image": "http://example.com/image.jpg",
        }
        mock_fetch.return_value = None

        response = self.client.post(
            reverse(
                "sync_metadata",
                kwargs={
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                    "media_id": "238",
                },
            )
            + "?next=/",
        )
        self.assertEqual(response.status_code, 302)


class CrudHelperBranchTests(TestCase):
    def test_restrict_ongoing_status_choices_with_none_metadata(self):
        from app.forms import AnimeForm
        from app.views.crud import _restrict_ongoing_status_choices

        form = AnimeForm()
        before = list(form.fields["status"].choices)
        _restrict_ongoing_status_choices(form, MediaTypes.ANIME.value, None)
        self.assertEqual(list(form.fields["status"].choices), before)

    def test_restrict_ongoing_status_choices_skips_other_types(self):
        from app.forms import MovieForm
        from app.views.crud import _restrict_ongoing_status_choices

        form = MovieForm()
        before = list(form.fields["status"].choices)
        _restrict_ongoing_status_choices(
            form, MediaTypes.MOVIE.value, {"is_ongoing": True}
        )
        self.assertEqual(list(form.fields["status"].choices), before)

    def test_apply_form_restrictions_announced_drops_fields(self):
        from app.forms import MovieForm
        from app.views.crud import _apply_form_restrictions

        form = MovieForm()
        metadata = {"details": {"status": "Announced"}}
        _apply_form_restrictions(form, media=None, metadata=metadata)
        for field_name in ("score", "progress", "caught_up", "is_rewatch"):
            self.assertNotIn(field_name, form.fields)
        statuses = {c[0] for c in form.fields["status"].choices}
        self.assertEqual(statuses, {Status.PLANNING.value})

    def test_apply_form_restrictions_no_op_for_normal_state(self):
        from app.forms import MovieForm
        from app.views.crud import _apply_form_restrictions

        form = MovieForm()
        before = list(form.fields["status"].choices)
        _apply_form_restrictions(
            form, media=None, metadata={"details": {"status": "Released"}}
        )
        self.assertEqual(list(form.fields["status"].choices), before)
