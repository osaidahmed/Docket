import json
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse


class ImportMALViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "testuser", "password": "testpassword"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    @patch("integrations.views.tasks.import_mal.delay")
    def test_import_mal_once(self, mock_delay):
        response = self.client.post(
            reverse("import_mal"),
            {"user": "mal_user", "mode": "full", "frequency": "once"},
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_delay.assert_called_once_with(
            username="mal_user", user_id=self.user.id, mode="full"
        )
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("MyAnimeList" in str(m) for m in messages))

    @patch("integrations.views.helpers.create_import_schedule")
    def test_import_mal_scheduled(self, mock_schedule):
        response = self.client.post(
            reverse("import_mal"),
            {
                "user": "mal_user",
                "mode": "full",
                "frequency": "daily",
                "time": "08:00",
            },
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_schedule.assert_called_once()

    def test_import_mal_missing_username(self):
        response = self.client.post(
            reverse("import_mal"),
            {"user": "", "mode": "full", "frequency": "once"},
        )
        self.assertRedirects(response, reverse("import_data"))
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("required" in str(m) for m in messages))

    def test_import_mal_get_not_allowed(self):
        response = self.client.get(reverse("import_mal"))
        self.assertEqual(response.status_code, 405)


class ImportKitsuViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "testuser", "password": "testpassword"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    @patch("integrations.views.tasks.import_kitsu.delay")
    def test_import_kitsu_once(self, mock_delay):
        response = self.client.post(
            reverse("import_kitsu"),
            {"user": "12345", "mode": "full", "frequency": "once"},
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_delay.assert_called_once_with(
            username="12345", user_id=self.user.id, mode="full"
        )

    @patch("integrations.views.helpers.create_import_schedule")
    def test_import_kitsu_scheduled(self, mock_schedule):
        response = self.client.post(
            reverse("import_kitsu"),
            {
                "user": "12345",
                "mode": "full",
                "frequency": "daily",
                "time": "09:00",
            },
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_schedule.assert_called_once()

    def test_import_kitsu_missing_id(self):
        response = self.client.post(
            reverse("import_kitsu"),
            {"user": "", "mode": "full", "frequency": "once"},
        )
        self.assertRedirects(response, reverse("import_data"))
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("required" in str(m) for m in messages))


class ImportSteamViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "testuser", "password": "testpassword"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    @patch("integrations.views.tasks.import_steam.delay")
    def test_import_steam_once(self, mock_delay):
        response = self.client.post(
            reverse("import_steam"),
            {"user": "steam_user", "mode": "full", "frequency": "once"},
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_delay.assert_called_once_with(
            username="steam_user", user_id=self.user.id, mode="full"
        )

    @patch("integrations.views.helpers.create_import_schedule")
    def test_import_steam_scheduled(self, mock_schedule):
        response = self.client.post(
            reverse("import_steam"),
            {
                "user": "steam_user",
                "mode": "full",
                "frequency": "daily",
                "time": "10:00",
            },
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_schedule.assert_called_once()

    def test_import_steam_missing_id(self):
        response = self.client.post(
            reverse("import_steam"),
            {"user": "", "mode": "full", "frequency": "once"},
        )
        self.assertRedirects(response, reverse("import_data"))
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("required" in str(m) for m in messages))


class ImportTraktPublicViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "testuser", "password": "testpassword"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    @patch("integrations.views.tasks.import_trakt.delay")
    def test_import_trakt_public_once(self, mock_delay):
        response = self.client.post(
            reverse("import_trakt_public"),
            {
                "user": "trakt_user",
                "mode": "full",
                "frequency": "once",
                "time": "08:00",
            },
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_delay.assert_called_once_with(
            user_id=self.user.id, mode="full", username="trakt_user"
        )

    @patch("integrations.views.helpers.create_import_schedule")
    def test_import_trakt_public_scheduled(self, mock_schedule):
        response = self.client.post(
            reverse("import_trakt_public"),
            {
                "user": "trakt_user",
                "mode": "full",
                "frequency": "daily",
                "time": "08:00",
            },
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_schedule.assert_called_once()

    def test_import_trakt_public_missing_username(self):
        response = self.client.post(
            reverse("import_trakt_public"),
            {"user": "", "mode": "full", "frequency": "once", "time": "08:00"},
        )
        self.assertRedirects(response, reverse("import_data"))
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("required" in str(m) for m in messages))


class ImportAnilistPublicViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "testuser", "password": "testpassword"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    @patch("integrations.views.tasks.import_anilist.delay")
    def test_import_anilist_public_once(self, mock_delay):
        response = self.client.post(
            reverse("import_anilist_public"),
            {
                "user": "anilist_user",
                "mode": "full",
                "frequency": "once",
                "time": "08:00",
            },
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_delay.assert_called_once_with(
            user_id=self.user.id, mode="full", username="anilist_user"
        )

    @patch("integrations.views.helpers.create_import_schedule")
    def test_import_anilist_public_scheduled(self, mock_schedule):
        response = self.client.post(
            reverse("import_anilist_public"),
            {
                "user": "anilist_user",
                "mode": "full",
                "frequency": "daily",
                "time": "08:00",
            },
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_schedule.assert_called_once()

    def test_import_anilist_public_missing_username(self):
        response = self.client.post(
            reverse("import_anilist_public"),
            {"user": "", "mode": "full", "frequency": "once", "time": "08:00"},
        )
        self.assertRedirects(response, reverse("import_data"))
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("required" in str(m) for m in messages))


class ImportFileViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "testuser", "password": "testpassword"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    @patch("integrations.views.tasks.import_yamtrack.delay")
    def test_import_yamtrack_with_file(self, mock_delay):
        csv_file = SimpleUploadedFile("test.csv", b"col1,col2\nval1,val2")
        response = self.client.post(
            reverse("import_yamtrack"),
            {"yamtrack_csv": csv_file, "mode": "full"},
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_delay.assert_called_once()
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("Yamtrack" in str(m) for m in messages))

    def test_import_yamtrack_missing_file(self):
        response = self.client.post(
            reverse("import_yamtrack"),
            {"mode": "full"},
        )
        self.assertRedirects(response, reverse("import_data"))
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("required" in str(m) for m in messages))

    @patch("integrations.views.tasks.import_hltb.delay")
    def test_import_hltb_with_file(self, mock_delay):
        csv_file = SimpleUploadedFile("test.csv", b"col1,col2\nval1,val2")
        response = self.client.post(
            reverse("import_hltb"),
            {"hltb_csv": csv_file, "mode": "full"},
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_delay.assert_called_once()

    def test_import_hltb_missing_file(self):
        response = self.client.post(
            reverse("import_hltb"),
            {"mode": "full"},
        )
        self.assertRedirects(response, reverse("import_data"))
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("required" in str(m) for m in messages))

    @patch("integrations.views.tasks.import_imdb.delay")
    def test_import_imdb_with_file(self, mock_delay):
        csv_file = SimpleUploadedFile("test.csv", b"col1,col2\nval1,val2")
        response = self.client.post(
            reverse("import_imdb"),
            {"imdb_csv": csv_file, "mode": "full"},
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_delay.assert_called_once()

    def test_import_imdb_missing_file(self):
        response = self.client.post(
            reverse("import_imdb"),
            {"mode": "full"},
        )
        self.assertRedirects(response, reverse("import_data"))
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("required" in str(m) for m in messages))

    @patch("integrations.views.tasks.import_goodreads.delay")
    def test_import_goodreads_with_file(self, mock_delay):
        csv_file = SimpleUploadedFile("test.csv", b"col1,col2\nval1,val2")
        response = self.client.post(
            reverse("import_goodreads"),
            {"goodreads_csv": csv_file, "mode": "full"},
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_delay.assert_called_once()

    def test_import_goodreads_missing_file(self):
        response = self.client.post(
            reverse("import_goodreads"),
            {"mode": "full"},
        )
        self.assertRedirects(response, reverse("import_data"))
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("required" in str(m) for m in messages))


class TraktOAuthViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "testuser", "password": "testpassword"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def test_trakt_oauth_redirects(self):
        response = self.client.post(
            reverse("trakt_oauth"),
            {"mode": "full", "frequency": "once", "time": "08:00"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("trakt.tv/oauth/authorize", response.url)

    @patch("integrations.views.trakt.handle_oauth_callback")
    @patch("integrations.views.tasks.import_trakt.delay")
    def test_import_trakt_private_once(self, mock_delay, mock_oauth):
        mock_oauth.return_value = {
            "refresh_token": "test_refresh_token",
            "username": "trakt_user",
        }
        session = self.client.session
        state_token = "test_state"
        session[state_token] = {
            "mode": "full",
            "frequency": "once",
            "time": "08:00",
        }
        session.save()

        response = self.client.get(
            reverse("import_trakt_private"),
            {"code": "test_code", "state": state_token},
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_delay.assert_called_once()

    @patch("integrations.views.trakt.handle_oauth_callback")
    @patch("integrations.views.helpers.create_import_schedule")
    def test_import_trakt_private_scheduled(self, mock_schedule, mock_oauth):
        mock_oauth.return_value = {
            "refresh_token": "test_refresh_token",
            "username": "trakt_user",
        }
        session = self.client.session
        state_token = "test_state"
        session[state_token] = {
            "mode": "full",
            "frequency": "daily",
            "time": "08:00",
        }
        session.save()

        response = self.client.get(
            reverse("import_trakt_private"),
            {"code": "test_code", "state": state_token},
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_schedule.assert_called_once()


class SimklOAuthViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "testuser", "password": "testpassword"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def test_simkl_oauth_redirects(self):
        response = self.client.post(
            reverse("simkl_oauth"),
            {"mode": "full", "frequency": "once", "time": "08:00"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("simkl.com/oauth/authorize", response.url)

    @patch("integrations.views.simkl.get_token")
    @patch("integrations.views.tasks.import_simkl.delay")
    def test_import_simkl_private_once(self, mock_delay, mock_get_token):
        mock_get_token.return_value = {
            "access_token": "test_access_token",
            "username": "simkl_user",
        }
        session = self.client.session
        state_token = "test_state"
        session[state_token] = {
            "mode": "full",
            "frequency": "once",
            "time": "08:00",
        }
        session.save()

        response = self.client.get(
            reverse("import_simkl_private"),
            {"code": "test_code", "state": state_token},
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_delay.assert_called_once()

    @patch("integrations.views.simkl.get_token")
    @patch("integrations.views.helpers.create_import_schedule")
    def test_import_simkl_private_scheduled(self, mock_schedule, mock_get_token):
        mock_get_token.return_value = {
            "access_token": "test_access_token",
            "username": "simkl_user",
        }
        session = self.client.session
        state_token = "test_state"
        session[state_token] = {
            "mode": "full",
            "frequency": "daily",
            "time": "08:00",
        }
        session.save()

        response = self.client.get(
            reverse("import_simkl_private"),
            {"code": "test_code", "state": state_token},
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_schedule.assert_called_once()


class AnilistOAuthViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "testuser", "password": "testpassword"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def test_anilist_oauth_redirects(self):
        response = self.client.post(
            reverse("import_anilist_oauth"),
            {"mode": "full", "frequency": "once", "time": "08:00"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("anilist.co/api/v2/oauth/authorize", response.url)

    @patch("integrations.views.anilist.get_token")
    @patch("integrations.views.tasks.import_anilist.delay")
    def test_import_anilist_private_once(self, mock_delay, mock_get_token):
        mock_get_token.return_value = {
            "access_token": "test_access_token",
            "username": "anilist_user",
        }
        session = self.client.session
        state_token = "test_state"
        session[state_token] = {
            "mode": "full",
            "frequency": "once",
            "time": "08:00",
        }
        session.save()

        response = self.client.get(
            reverse("import_anilist_private"),
            {"code": "test_code", "state": state_token},
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_delay.assert_called_once()

    @patch("integrations.views.anilist.get_token")
    @patch("integrations.views.helpers.create_import_schedule")
    def test_import_anilist_private_scheduled(self, mock_schedule, mock_get_token):
        mock_get_token.return_value = {
            "access_token": "test_access_token",
            "username": "anilist_user",
        }
        session = self.client.session
        state_token = "test_state"
        session[state_token] = {
            "mode": "full",
            "frequency": "daily",
            "time": "08:00",
        }
        session.save()

        response = self.client.get(
            reverse("import_anilist_private"),
            {"code": "test_code", "state": state_token},
        )
        self.assertRedirects(response, reverse("import_data"))
        mock_schedule.assert_called_once()

    @patch("integrations.views.anilist.get_token")
    def test_import_anilist_private_missing_username(self, mock_get_token):
        mock_get_token.return_value = {
            "access_token": "test_access_token",
            "username": None,
        }
        session = self.client.session
        state_token = "test_state"
        session[state_token] = {
            "mode": "full",
            "frequency": "once",
            "time": "08:00",
        }
        session.save()

        response = self.client.get(
            reverse("import_anilist_private"),
            {"code": "test_code", "state": state_token},
        )
        self.assertRedirects(response, reverse("import_data"))
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("required" in str(m) for m in messages))


class WebhookViewMissingPayloadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_superuser(
            username="webhookuser",
            token="webhook-token",
        )

    def setUp(self):
        self.client = Client()

    def test_jellyfin_webhook_missing_payload(self):
        url = reverse("jellyfin_webhook", kwargs={"token": "webhook-token"})
        response = self.client.post(url, data=b"", content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_plex_webhook_missing_payload(self):
        url = reverse("plex_webhook", kwargs={"token": "webhook-token"})
        response = self.client.post(url, data={}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_emby_webhook_missing_payload(self):
        url = reverse("emby_webhook", kwargs={"token": "webhook-token"})
        response = self.client.post(url, data={}, format="multipart")
        self.assertEqual(response.status_code, 400)

    def test_jellyfin_webhook_invalid_token(self):
        url = reverse("jellyfin_webhook", kwargs={"token": "bad-token"})
        response = self.client.post(
            url, data=b"test", content_type="application/json"
        )
        self.assertEqual(response.status_code, 401)

    def test_plex_webhook_invalid_token(self):
        url = reverse("plex_webhook", kwargs={"token": "bad-token"})
        response = self.client.post(url, data={}, format="multipart")
        self.assertEqual(response.status_code, 401)

    def test_emby_webhook_invalid_token(self):
        url = reverse("emby_webhook", kwargs={"token": "bad-token"})
        response = self.client.post(url, data={}, format="multipart")
        self.assertEqual(response.status_code, 401)
