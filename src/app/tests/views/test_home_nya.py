from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from app.models import Anime, Item, MediaTypes, Movie, Sources, Status
from app.tests.views._home_helpers import backlog_save_data, create_item
from app.tests.views.test_home import _flatten_group_titles
from app.tests.views.test_home_rewatch import _collect_type_and_special_titles
from events.models import Event


class NotYetAiringTests(TestCase):
    """Test the 'Not Yet Airing' backlog section."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def _create_anime_with_future_events(self, media_id, title, days_ahead=30):
        item = create_item(media_id, Sources.MAL.value, MediaTypes.ANIME.value, title)
        Event.objects.create(
            item=item,
            content_number=1,
            datetime=timezone.now() + timedelta(days=days_ahead),
        )
        return item

    def test_not_yet_airing_in_dedicated_section_all_mode(self):
        """Not-yet-airing anime appears in a dedicated group, not in type groups."""
        item = self._create_anime_with_future_events("6000", "Future Anime")
        Anime.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        type_titles, nya_titles = _collect_type_and_special_titles(
            groups, "not_yet_airing"
        )

        self.assertIn("Future Anime", nya_titles)
        self.assertNotIn("Future Anime", type_titles)

    def test_not_yet_airing_separated_in_type_filter(self):
        """Not-yet-airing items get their own group even when filtering by type."""
        item = self._create_anime_with_future_events("6001", "Filtered Future Anime")
        Anime.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        response = self.client.get(reverse("home") + "?type=anime")
        groups = response.context["groups"]

        media_types = {g["media_type"] for g in groups}
        self.assertIn("not_yet_airing", media_types)

    def test_not_yet_airing_only_tv_anime(self):
        """Movies with future events are NOT extracted to Not Yet Airing."""
        item = create_item("6002", Sources.TMDB.value, MediaTypes.MOVIE.value, "Future Movie")
        Event.objects.create(
            item=item,
            content_number=None,
            datetime=timezone.now() + timedelta(days=30),
        )
        Movie.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        media_types = {g["media_type"] for g in groups}
        self.assertNotIn("not_yet_airing", media_types)

        titles = _flatten_group_titles(groups)
        self.assertIn("Future Movie", titles)

    def test_not_yet_airing_mixed_events_stays_in_group(self):
        """Anime with past AND future events stays in regular group."""
        item = create_item("6003", Sources.MAL.value, MediaTypes.ANIME.value, "Airing Anime")
        Event.objects.create(
            item=item,
            content_number=1,
            datetime=timezone.now() - timedelta(days=7),
        )
        Event.objects.create(
            item=item,
            content_number=2,
            datetime=timezone.now() + timedelta(days=7),
        )
        Anime.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        media_types = {g["media_type"] for g in groups}
        self.assertNotIn("not_yet_airing", media_types)

        titles = _flatten_group_titles(groups)
        self.assertIn("Airing Anime", titles)

    def test_not_yet_airing_sorted_by_release_date(self):
        """Items in Not Yet Airing are sorted by earliest release date."""
        item_far = self._create_anime_with_future_events(
            "6004", "Far Future Anime", days_ahead=90
        )
        Anime.objects.create(
            item=item_far, user=self.user, status=Status.PLANNING.value
        )

        item_near = self._create_anime_with_future_events(
            "6005", "Near Future Anime", days_ahead=10
        )
        Anime.objects.create(
            item=item_near, user=self.user, status=Status.PLANNING.value
        )

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        nya_group = [g for g in groups if g["media_type"] == "not_yet_airing"]
        self.assertEqual(len(nya_group), 1)

        titles = []
        for sg in nya_group[0]["status_groups"]:
            titles.extend(m.item.title for m in sg["items"])

        self.assertEqual(titles, ["Near Future Anime", "Far Future Anime"])

    def test_no_not_yet_airing_section_when_empty(self):
        """No Not Yet Airing group when no items meet criteria."""
        item = create_item("6006", Sources.MAL.value, MediaTypes.ANIME.value, "Normal Anime")
        Anime.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]
        media_types = {g["media_type"] for g in groups}
        self.assertNotIn("not_yet_airing", media_types)
        self.assertNotContains(response, "Not Yet Airing")

    def test_min_datetime_planning_is_not_yet_airing(self):
        """Anime with only datetime.min events in Planning is not-yet-airing."""
        item = create_item("6007", Sources.MAL.value, MediaTypes.ANIME.value, "Upcoming Unknown Anime")
        Event.objects.create(
            item=item,
            content_number=None,
            datetime=datetime.min.replace(tzinfo=UTC),
        )
        Anime.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value, progress=0
        )

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        type_titles, nya_titles = _collect_type_and_special_titles(
            groups, "not_yet_airing"
        )

        self.assertIn("Upcoming Unknown Anime", nya_titles)
        self.assertNotIn("Upcoming Unknown Anime", type_titles)

    def test_min_datetime_in_progress_stays_in_regular_group(self):
        """Anime with only datetime.min events in In Progress stays in regular group."""
        item = create_item("6008", Sources.MAL.value, MediaTypes.ANIME.value, "Airing Long Runner")
        Event.objects.create(
            item=item,
            content_number=None,
            datetime=datetime.min.replace(tzinfo=UTC),
        )
        Anime.objects.create(
            item=item, user=self.user, status=Status.IN_PROGRESS.value, progress=0
        )

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        media_types = {g["media_type"] for g in groups}
        self.assertNotIn("not_yet_airing", media_types)

        titles = _flatten_group_titles(groups)
        self.assertIn("Airing Long Runner", titles)

    def test_not_yet_airing_future_plus_min_datetime(self):
        """Anime with future real dates + datetime.min events is not-yet-airing."""
        item = create_item("6009", Sources.MAL.value, MediaTypes.ANIME.value, "Partial Schedule Anime")
        Event.objects.create(
            item=item,
            content_number=1,
            datetime=timezone.now() + timedelta(days=30),
        )
        Event.objects.create(
            item=item,
            content_number=12,
            datetime=datetime.min.replace(tzinfo=UTC),
        )
        Anime.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value, progress=0
        )

        response = self.client.get(reverse("home"))
        groups = response.context["groups"]

        type_titles, nya_titles = _collect_type_and_special_titles(
            groups, "not_yet_airing"
        )

        self.assertIn("Partial Schedule Anime", nya_titles)
        self.assertNotIn("Partial Schedule Anime", type_titles)


class NotYetAiringActionGatingTests(TestCase):
    """Test that actions are disabled for not-yet-airing media."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client.login(**self.credentials)

    def _create_not_yet_airing_anime(self, media_id="7000"):
        item = create_item(media_id, Sources.MAL.value, MediaTypes.ANIME.value, "Future Anime")
        Event.objects.create(
            item=item,
            content_number=1,
            datetime=timezone.now() + timedelta(days=30),
        )
        return Anime.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )

    def _create_airing_anime(self, media_id="7100"):
        item = create_item(media_id, Sources.MAL.value, MediaTypes.ANIME.value, "Airing Anime")
        Event.objects.create(
            item=item,
            content_number=1,
            datetime=timezone.now() - timedelta(days=7),
        )
        Event.objects.create(
            item=item,
            content_number=2,
            datetime=timezone.now() + timedelta(days=7),
        )
        anime = Anime.objects.create(
            item=item, user=self.user, status=Status.PLANNING.value
        )
        Anime.objects.filter(id=anime.id).update(
            status=Status.IN_PROGRESS.value, progress=1
        )
        anime.refresh_from_db()
        return anime

    def test_backlog_hides_score_for_not_yet_airing(self):
        self._create_not_yet_airing_anime()
        response = self.client.get(reverse("home"))
        content = response.content.decode()
        self.assertNotIn('name="score" min="0" max="10"', content)

    def test_backlog_hides_progress_for_not_yet_airing(self):
        self._create_not_yet_airing_anime()
        response = self.client.get(reverse("home"))
        content = response.content.decode()
        self.assertNotIn('name="progress" min="0"', content)
        self.assertIn('type="hidden" name="progress"', content)

    def test_backlog_hides_caught_up_checkbox_for_not_yet_airing(self):
        self._create_not_yet_airing_anime()
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, 'name="caught_up"')

    def test_backlog_hides_rewatch_checkbox_for_not_yet_airing(self):
        self._create_not_yet_airing_anime()
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, 'name="is_rewatch"')

    def test_backlog_shows_fields_for_airing_media(self):
        self._create_airing_anime()
        response = self.client.get(reverse("home"))
        content = response.content.decode()
        self.assertIn('name="score"', content)
        self.assertIn('name="progress"', content)
        self.assertIn('name="is_rewatch"', content)

    def test_backlog_save_preserves_values_for_not_yet_airing(self):
        anime = self._create_not_yet_airing_anime()
        response = self.client.post(
            reverse("backlog_save"),
            {
                "media_id": anime.item.media_id,
                "source": anime.item.source,
                "media_type": anime.item.media_type,
                "instance_id": anime.id,
                "score": "",
                "progress": "0",
                "status": Status.PLANNING.value,
            },
        )
        self.assertEqual(response.status_code, 200)
        anime.refresh_from_db()
        self.assertIsNone(anime.score)
        self.assertEqual(anime.progress, 0)

    def test_backlog_card_status_dropdown_restricted_for_not_yet_airing(self):
        self._create_not_yet_airing_anime()
        response = self.client.get(reverse("home"))
        content = response.content.decode()
        self.assertIn('value="Planning"', content)
        self.assertIn('value="Dropped"', content)
        self.assertNotIn('value="In progress"', content)
        self.assertNotIn('value="Completed"', content)
        self.assertNotIn('value="Paused"', content)

    def test_backlog_card_hides_start_button_for_not_yet_airing(self):
        self._create_not_yet_airing_anime()
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, "quick_status_transition")

    def test_backlog_card_shows_start_button_for_airing_planning(self):
        item = create_item("7200", Sources.MAL.value, MediaTypes.ANIME.value, "Airing Planning Anime")
        Event.objects.create(
            item=item,
            content_number=1,
            datetime=timezone.now() - timedelta(days=7),
        )
        Event.objects.create(
            item=item,
            content_number=2,
            datetime=timezone.now() + timedelta(days=7),
        )
        Anime.objects.create(item=item, user=self.user, status=Status.PLANNING.value)

        response = self.client.get(reverse("home"))
        self.assertContains(response, "quick_status_transition")


class CaughtUpToggleTests(TestCase):
    """Tests for manual caught_up toggle on backlog cards."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.anime_item = create_item(
            "3000", Sources.MAL.value, MediaTypes.ANIME.value, "Ongoing Anime"
        )

    def setUp(self):
        self.client.login(**self.credentials)

    def test_manual_caught_up_overrides_auto_detection(self):
        """Manual caught_up=True shows 'Caught Up' even when progress is behind."""
        anime = Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=3,
            caught_up=True,
        )
        Event.objects.create(
            item=self.anime_item,
            content_number=10,
            datetime=timezone.now() + timedelta(days=2),
        )

        response = self.client.get(reverse("home"))
        content = response.content.decode()

        card_id = f"backlog-card-anime-{anime.id}"
        card_start = content.find(card_id)
        self.assertNotEqual(card_start, -1)
        card_section = content[card_start : card_start + 8000]

        self.assertIn("Caught Up", card_section)
        self.assertNotIn("Caught Up?", card_section)

    def test_manual_caught_up_false_uses_auto_detection(self):
        """With caught_up=False and progress behind, shows 'Caught Up?'."""
        Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=3,
            caught_up=False,
        )
        Event.objects.create(
            item=self.anime_item,
            content_number=10,
            datetime=timezone.now() + timedelta(days=2),
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, "Caught Up?")

    def test_auto_caught_up_works_without_manual_flag(self):
        """Progress matching next event shows 'Caught Up' even without flag."""
        Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=9,
            caught_up=False,
        )
        Event.objects.create(
            item=self.anime_item,
            content_number=10,
            datetime=timezone.now() + timedelta(days=2),
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "Caught Up?")

    def test_caught_up_toggle_persists_via_backlog_save(self):
        """Setting caught_up via edit form persists on reload."""
        anime = Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=3,
        )
        Event.objects.create(
            item=self.anime_item,
            content_number=10,
            datetime=timezone.now() + timedelta(days=2),
        )

        data = backlog_save_data(anime)
        data["caught_up"] = "on"
        self.client.post(reverse("backlog_save"), data)

        anime.refresh_from_db()
        self.assertTrue(anime.caught_up)

    def test_caught_up_uncheck_persists_via_backlog_save(self):
        """Unchecking caught_up via edit form persists on reload."""
        anime = Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=3,
            caught_up=True,
        )
        Event.objects.create(
            item=self.anime_item,
            content_number=10,
            datetime=timezone.now() + timedelta(days=2),
        )

        data = backlog_save_data(anime)
        self.client.post(reverse("backlog_save"), data)

        anime.refresh_from_db()
        self.assertFalse(anime.caught_up)

    def test_edit_form_has_caught_up_checkbox(self):
        """The backlog card edit form contains a caught_up checkbox."""
        Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=3,
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, 'name="caught_up"')

    @patch("app.providers.services.get_media_metadata")
    def test_caught_up_no_effect_without_next_event(self, mock_metadata):
        """caught_up=True on finished content still shows 'Done' button."""
        mock_metadata.return_value = {"max_progress": None}
        item = create_item(
            "3001", Sources.TMDB.value, MediaTypes.MOVIE.value, "Finished Movie"
        )
        Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            caught_up=True,
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, "Done")

    def test_caught_up_response_matches_reload(self):
        """HTMX response after toggling caught_up matches page reload."""
        anime = Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=3,
        )
        Event.objects.create(
            item=self.anime_item,
            content_number=10,
            datetime=timezone.now() + timedelta(days=2),
        )

        data = backlog_save_data(anime)
        data["caught_up"] = "on"
        response = self.client.post(reverse("backlog_save"), data)
        self.assertContains(response, "Caught Up")
        self.assertNotContains(response, "Caught Up?")

        page = self.client.get(reverse("home"))
        content = page.content.decode()
        card_id = f"backlog-card-anime-{anime.id}"
        card_start = content.find(card_id)
        card_section = content[card_start : card_start + 8000]
        self.assertIn("Caught Up", card_section)
        self.assertNotIn("Caught Up?", card_section)

    def test_caught_up_checkbox_checked_when_true(self):
        """The caught_up checkbox is checked when the field is True."""
        Anime.objects.create(
            item=self.anime_item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=3,
            caught_up=True,
        )

        response = self.client.get(reverse("home"))
        self.assertContains(response, 'name="caught_up"')
        content = response.content.decode()
        caught_up_pos = content.find('name="caught_up"')
        checkbox_context = content[caught_up_pos : caught_up_pos + 200]
        self.assertIn("checked", checkbox_context)
