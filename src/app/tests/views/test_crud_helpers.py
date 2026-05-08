from unittest.mock import MagicMock

from django.test import TestCase

from app.models import MediaTypes, Status
from app.views.crud import _restrict_ongoing_status_choices


class RestrictOngoingStatusChoicesTests(TestCase):
    def _form_with_status_choices(self):
        form = MagicMock()
        form.fields = {
            "status": MagicMock(),
        }
        form.fields["status"].choices = list(Status.choices)
        return form

    def test_non_anime_non_tv_is_noop(self):
        form = self._form_with_status_choices()
        original = list(form.fields["status"].choices)
        _restrict_ongoing_status_choices(form, MediaTypes.MOVIE.value, {"details": {}})
        self.assertEqual(form.fields["status"].choices, original)

    def test_none_metadata_is_noop(self):
        form = self._form_with_status_choices()
        original = list(form.fields["status"].choices)
        _restrict_ongoing_status_choices(form, MediaTypes.TV.value, None)
        self.assertEqual(form.fields["status"].choices, original)

    def test_airing_tv_removes_completed(self):
        form = self._form_with_status_choices()
        _restrict_ongoing_status_choices(
            form,
            MediaTypes.TV.value,
            {"details": {"status": "Airing"}},
        )
        choices = [c[0] for c in form.fields["status"].choices]
        self.assertNotIn(Status.COMPLETED.value, choices)

    def test_upcoming_tv_removes_completed(self):
        form = self._form_with_status_choices()
        _restrict_ongoing_status_choices(
            form,
            MediaTypes.TV.value,
            {"details": {"status": "Upcoming"}},
        )
        choices = [c[0] for c in form.fields["status"].choices]
        self.assertNotIn(Status.COMPLETED.value, choices)

    def test_ended_tv_keeps_completed(self):
        form = self._form_with_status_choices()
        _restrict_ongoing_status_choices(
            form,
            MediaTypes.TV.value,
            {"details": {"status": "Ended"}},
        )
        choices = [c[0] for c in form.fields["status"].choices]
        self.assertIn(Status.COMPLETED.value, choices)

    def test_is_ongoing_metadata_flag_removes_completed(self):
        form = self._form_with_status_choices()
        _restrict_ongoing_status_choices(
            form,
            MediaTypes.ANIME.value,
            {"details": {}, "is_ongoing": True},
        )
        choices = [c[0] for c in form.fields["status"].choices]
        self.assertNotIn(Status.COMPLETED.value, choices)

    def test_next_episode_season_present_removes_completed(self):
        form = self._form_with_status_choices()
        _restrict_ongoing_status_choices(
            form,
            MediaTypes.ANIME.value,
            {"details": {}, "next_episode_season": 2},
        )
        choices = [c[0] for c in form.fields["status"].choices]
        self.assertNotIn(Status.COMPLETED.value, choices)

    def test_anime_airing_removes_completed(self):
        form = self._form_with_status_choices()
        _restrict_ongoing_status_choices(
            form,
            MediaTypes.ANIME.value,
            {"details": {"status": "Airing"}},
        )
        choices = [c[0] for c in form.fields["status"].choices]
        self.assertNotIn(Status.COMPLETED.value, choices)

    def test_no_ongoing_signal_keeps_completed(self):
        form = self._form_with_status_choices()
        _restrict_ongoing_status_choices(
            form,
            MediaTypes.ANIME.value,
            {"details": {"status": "Completed"}},
        )
        choices = [c[0] for c in form.fields["status"].choices]
        self.assertIn(Status.COMPLETED.value, choices)
