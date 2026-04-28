import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from app import config
from app.history_processor import (
    apply_date_status_integration,
    build_changes_list,
    collect_creation_changes,
    format_description,
    organize_changes,
    process_history_entries,
)
from app.models import (
    Item,
    MediaTypes,
    Movie,
    Sources,
    Status,
)


class HistoryProcessorTests(TestCase):
    def test_get_verb_covers_all_media_types(self):
        """Test that get_verb covers all media types defined in MediaTypes."""
        # Get all media types from the MediaTypes enum
        for media_type in MediaTypes:
            # Ensure both present and past tense verbs are defined
            try:
                config.get_verb(media_type.value, past_tense=False)
                config.get_verb(media_type.value, past_tense=True)
            except KeyError:
                self.fail(f"Media type {media_type.name} not defined in get_verb")

    def test_format_description_status_initial(self):
        """Test format_description for initial status changes."""
        # Test initial status settings
        self.assertEqual(
            format_description(
                "status",
                None,
                Status.IN_PROGRESS.value,
                MediaTypes.TV.value,
            ),
            "Marked as currently watching",
        )
        self.assertEqual(
            format_description(
                "status",
                None,
                Status.COMPLETED.value,
                MediaTypes.MANGA.value,
            ),
            "Marked as finished reading",
        )
        self.assertEqual(
            format_description(
                "status",
                None,
                Status.PLANNING.value,
                MediaTypes.GAME.value,
            ),
            "Added to playing list",
        )
        self.assertEqual(
            format_description(
                "status",
                None,
                Status.DROPPED.value,
                MediaTypes.BOOK.value,
            ),
            "Marked as dropped",
        )
        self.assertEqual(
            format_description(
                "status",
                None,
                Status.PAUSED.value,
                MediaTypes.ANIME.value,
            ),
            "Marked as paused watching",
        )

    def test_format_description_status_transitions(self):
        """Test format_description for status transitions."""
        # Test status transitions
        self.assertEqual(
            format_description(
                "status",
                Status.PLANNING.value,
                Status.IN_PROGRESS.value,
                MediaTypes.TV.value,
            ),
            "Currently watching",
        )
        self.assertEqual(
            format_description(
                "status",
                Status.IN_PROGRESS.value,
                Status.COMPLETED.value,
                MediaTypes.MANGA.value,
            ),
            "Finished reading",
        )
        self.assertEqual(
            format_description(
                "status",
                Status.IN_PROGRESS.value,
                Status.PAUSED.value,
                MediaTypes.GAME.value,
            ),
            "Paused playing",
        )
        self.assertEqual(
            format_description(
                "status",
                Status.PAUSED.value,
                Status.IN_PROGRESS.value,
                MediaTypes.BOOK.value,
            ),
            "Resumed reading",
        )
        self.assertEqual(
            format_description(
                "status",
                Status.IN_PROGRESS.value,
                Status.DROPPED.value,
                MediaTypes.ANIME.value,
            ),
            "Stopped watching",
        )
        self.assertEqual(
            format_description("status", "Custom1", "Custom2", MediaTypes.TV.value),
            "Changed status from Custom1 to Custom2",
        )

    def test_format_description_score(self):
        """Test format_description for score changes."""
        # Initial score
        self.assertEqual(
            format_description("score", None, 8.5, MediaTypes.TV.value),
            "Rated 8.5/10",
        )
        self.assertEqual(
            format_description("score", 0, 7.0, MediaTypes.ANIME.value),
            "Rated 7.0/10",
        )
        # Score change
        self.assertEqual(
            format_description("score", 6.5, 8.0, MediaTypes.MOVIE.value),
            "Changed rating from 6.5 to 8.0",
        )

    def test_format_description_progress(self):
        """Test format_description for progress changes."""
        # Initial progress
        self.assertEqual(
            format_description("progress", None, 120, MediaTypes.GAME.value),
            "Played for 2h 00min",
        )
        self.assertEqual(
            format_description("progress", None, 5, MediaTypes.BOOK.value),
            "Read up to page 5",
        )
        self.assertEqual(
            format_description("progress", None, 10, MediaTypes.MANGA.value),
            "Read up to chapter 10",
        )

        # Progress change
        self.assertEqual(
            format_description("progress", 60, 90, MediaTypes.GAME.value),
            "Added 30min of playtime",
        )
        self.assertEqual(
            format_description("progress", 90, 60, MediaTypes.GAME.value),
            "Removed 30min of playtime",
        )
        self.assertEqual(
            format_description("progress", 10, 15, MediaTypes.BOOK.value),
            "Progress set to 15 pages",
        )
        self.assertEqual(
            format_description("progress", 5, 10, MediaTypes.MANGA.value),
            "Progress set to 10 chapters",
        )

    def test_format_description_notes(self):
        """Test format_description for notes changes."""
        # Initial notes
        self.assertEqual(
            format_description("notes", None, "Test notes"),
            "Added notes",
        )

        # Update notes
        self.assertEqual(
            format_description("notes", "Old notes", "New notes"),
            "Updated notes",
        )

        # Remove notes
        self.assertEqual(
            format_description("notes", "Old notes", ""),
            "Removed notes",
        )

    def test_format_description_generic(self):
        """Test format_description for generic field changes."""
        self.assertEqual(
            format_description("custom_field", "old", "new"),
            "Updated custom field from old to new",
        )

    def test_format_description_generic_initial(self):
        self.assertEqual(
            format_description("custom_field", None, "value"),
            "Set custom field to value",
        )

    def test_format_description_date_initial(self):
        user = get_user_model().objects.create_user(
            username="datetest",
            password="12345",
        )
        dt = timezone.make_aware(datetime.datetime(2023, 6, 1, 0, 0))
        result = format_description("start_date", None, dt, user=user)
        self.assertIn("Started", result)

        result = format_description("end_date", None, dt, user=user)
        self.assertIn("Finished", result)

    def test_format_description_date_changes(self):
        user = get_user_model().objects.create_user(
            username="datetest2",
            password="12345",
        )
        old_dt = timezone.make_aware(datetime.datetime(2023, 1, 1, 0, 0))
        new_dt = timezone.make_aware(datetime.datetime(2023, 6, 1, 0, 0))
        result = format_description("start_date", old_dt, new_dt, user=user)
        self.assertIn("Start date changed", result)

        result = format_description("end_date", old_dt, new_dt, user=user)
        self.assertIn("End date changed", result)

    def test_format_description_date_removal(self):
        user = get_user_model().objects.create_user(
            username="datetest3",
            password="12345",
        )
        old_dt = timezone.make_aware(datetime.datetime(2023, 1, 1, 0, 0))
        result = format_description("start_date", old_dt, None, user=user)
        self.assertEqual(result, "Removed start date")

        result = format_description("end_date", old_dt, None, user=user)
        self.assertEqual(result, "Removed end date")

    def test_format_description_date_set_from_empty(self):
        user = get_user_model().objects.create_user(
            username="datetest4",
            password="12345",
        )
        new_dt = timezone.make_aware(datetime.datetime(2023, 6, 1, 0, 0))
        result = format_description("start_date", "", new_dt, user=user)
        self.assertIn("Started", result)

    def test_format_description_notes_added_from_empty(self):
        result = format_description("notes", "", "New notes")
        self.assertEqual(result, "Added notes")


class FakeChange:
    def __init__(self, field, old, new):
        self.field = field
        self.old = old
        self.new = new


class OrganizeChangesTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="organizetest",
            password="12345",
        )

    def test_organize_status_change(self):
        changes = [
            FakeChange("status", Status.PLANNING.value, Status.IN_PROGRESS.value)
        ]
        result = organize_changes(changes, MediaTypes.TV.value, self.user)
        self.assertIsNotNone(result["status_change"])
        self.assertEqual(result["status_change"]["field"], "status")

    def test_organize_end_date_change(self):
        dt = timezone.make_aware(datetime.datetime(2023, 6, 1, 0, 0))
        changes = [FakeChange("end_date", None, dt)]
        result = organize_changes(changes, MediaTypes.TV.value, self.user)
        self.assertIsNotNone(result["date_changes"]["end_date"])

    def test_organize_start_date_change(self):
        dt = timezone.make_aware(datetime.datetime(2023, 6, 1, 0, 0))
        changes = [FakeChange("start_date", None, dt)]
        result = organize_changes(changes, MediaTypes.TV.value, self.user)
        self.assertIsNotNone(result["date_changes"]["start_date"])

    def test_organize_other_change(self):
        changes = [FakeChange("score", 0, 8)]
        result = organize_changes(changes, MediaTypes.TV.value, self.user)
        self.assertEqual(len(result["other_changes"]), 1)

    def test_organize_skips_movie_progress(self):
        changes = [FakeChange("progress", 0, 1)]
        result = organize_changes(changes, MediaTypes.MOVIE.value, self.user)
        self.assertEqual(len(result["other_changes"]), 0)
        self.assertIsNone(result["status_change"])


class ApplyDateStatusIntegrationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="integrationtest",
            password="12345",
        )

    def test_start_date_with_in_progress(self):
        dt = timezone.make_aware(datetime.datetime(2023, 6, 1, 0, 0))
        changes = {
            "date_changes": {
                "start_date": {
                    "description": "old desc",
                    "field": "start_date",
                    "new": dt,
                },
                "end_date": None,
            },
            "status_change": {
                "description": "status desc",
                "field": "status",
                "old": None,
                "new": Status.IN_PROGRESS.value,
            },
            "other_changes": [],
        }
        apply_date_status_integration(changes, self.user)
        self.assertIn(
            "Started on", changes["date_changes"]["start_date"]["description"]
        )
        self.assertIsNone(changes["status_change"])

    def test_end_date_with_completed(self):
        dt = timezone.make_aware(datetime.datetime(2023, 6, 1, 0, 0))
        changes = {
            "date_changes": {
                "start_date": None,
                "end_date": {
                    "description": "old desc",
                    "field": "end_date",
                    "new": dt,
                },
            },
            "status_change": {
                "description": "status desc",
                "field": "status",
                "old": None,
                "new": Status.COMPLETED.value,
            },
            "other_changes": [],
        }
        apply_date_status_integration(changes, self.user)
        self.assertIn("Finished on", changes["date_changes"]["end_date"]["description"])
        self.assertIsNone(changes["status_change"])


class BuildChangesListTests(TestCase):
    def test_build_with_dates_and_status(self):
        processed_entry = {"changes": []}
        changes = {
            "date_changes": {
                "start_date": {
                    "description": "Started on 2023-01-01",
                    "field": "start_date",
                },
                "end_date": {
                    "description": "Finished on 2023-06-01",
                    "field": "end_date",
                },
            },
            "status_change": {"description": "Completed", "field": "status"},
            "other_changes": [{"description": "Rated 8/10", "field": "score"}],
        }
        build_changes_list(changes, processed_entry)
        self.assertEqual(len(processed_entry["changes"]), 4)
        self.assertEqual(processed_entry["changes"][0]["field"], "start_date")
        self.assertEqual(processed_entry["changes"][1]["field"], "end_date")
        self.assertEqual(processed_entry["changes"][2]["field"], "status")
        self.assertEqual(processed_entry["changes"][3]["field"], "score")


class ProcessHistoryEntriesTests(TestCase):
    def setUp(self):
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)

        self.item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )
        self.movie = Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=0,
        )
        self.movie.status = Status.COMPLETED.value
        self.movie.score = 8
        self.movie.save()

    def test_process_entries(self):
        history = self.movie.history.all()
        entries = process_history_entries(
            history,
            MediaTypes.MOVIE.value,
            1,
            self.user,
        )
        self.assertGreater(len(entries), 0)
        for entry in entries:
            self.assertIn("changes", entry)
            self.assertIn("media_entry_number", entry)
            self.assertEqual(entry["media_entry_number"], 1)

    def test_process_creation_entry_with_dates(self):
        movie_item = Item.objects.create(
            media_id="999",
            source=Sources.MANUAL.value,
            media_type=MediaTypes.MOVIE.value,
            title="Date Movie",
            image="http://example.com/image.jpg",
        )
        movie = Movie.objects.create(
            item=movie_item,
            user=self.user,
            status=Status.COMPLETED.value,
            progress=1,
            score=9,
            start_date=timezone.make_aware(
                datetime.datetime(2023, 1, 1, 0, 0),
            ),
            end_date=timezone.make_aware(
                datetime.datetime(2023, 6, 1, 0, 0),
            ),
        )
        history = movie.history.all()
        creation_record = history.last()

        from django.apps import apps

        history_model = apps.get_model(
            app_label="app",
            model_name=f"historical{MediaTypes.MOVIE.value}",
        )
        result = collect_creation_changes(
            creation_record,
            history_model,
            MediaTypes.MOVIE.value,
            self.user,
        )
        has_date_change = (
            result["date_changes"]["start_date"] is not None
            or result["date_changes"]["end_date"] is not None
        )
        self.assertTrue(has_date_change)


class HistoryProcessorBranchTests(TestCase):
    def test_apply_date_status_integration_no_status_change(self):
        changes = {
            "status_change": None,
            "date_changes": {"start_date": None, "end_date": None},
        }
        apply_date_status_integration(changes, user=None)
        self.assertIsNone(changes["status_change"])

    def test_fmt_status_initial_unmapped_returns_default(self):
        result = format_description(
            "status",
            None,
            "made_up",
            media_type=MediaTypes.MOVIE.value,
        )
        self.assertEqual(result, "Set status to made_up")

    def test_fmt_status_change_unknown_transition(self):
        result = format_description(
            "status",
            Status.PAUSED.value,
            Status.DROPPED.value,
            media_type=MediaTypes.MOVIE.value,
        )
        self.assertIn(Status.PAUSED.value, result)
        self.assertIn(Status.DROPPED.value, result)

    def test_fmt_progress_initial_no_media_type(self):
        result = format_description("progress", None, 5)
        self.assertEqual(result, "Set progress to 5")

    def test_fmt_date_change_removed_end_date(self):
        from app.history_processor import _fmt_date_change

        result = _fmt_date_change(
            "end_date",
            "2023-01-01",
            None,
            MediaTypes.MOVIE.value,
        )
        self.assertEqual(result, "Removed end date")

    def test_fmt_date_change_set_when_old_was_none(self):
        from app.history_processor import _fmt_date_change

        result = _fmt_date_change(
            "start_date",
            None,
            "2023-01-01",
            MediaTypes.MOVIE.value,
        )
        self.assertEqual(result, "Started on 2023-01-01")

    def test_should_skip_creation_field_movie_progress(self):
        from django.apps import apps

        from app.history_processor import _should_skip_creation_field

        history_model = apps.get_model(
            app_label="app",
            model_name=f"historical{MediaTypes.MOVIE.value}",
        )
        progress_field = next(
            f for f in history_model._meta.get_fields() if f.name == "progress"
        )

        class _FakeRecord:
            progress = 1

        self.assertTrue(
            _should_skip_creation_field(
                progress_field, _FakeRecord(), MediaTypes.MOVIE.value
            )
        )
