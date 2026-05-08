from django.test import TestCase

from app.models import Status
from integrations.imports import _simkl_helpers
from integrations.imports.kitsu import KitsuImporter
from integrations.imports.mal import MyAnimeListImporter


class MalStatusMappingTests(TestCase):
    def setUp(self):
        self.importer = MyAnimeListImporter.__new__(MyAnimeListImporter)

    def test_completed(self):
        assert self.importer._get_status("completed") == Status.COMPLETED.value

    def test_reading_is_in_progress(self):
        assert self.importer._get_status("reading") == Status.IN_PROGRESS.value

    def test_watching_is_in_progress(self):
        assert self.importer._get_status("watching") == Status.IN_PROGRESS.value

    def test_plan_to_watch(self):
        assert self.importer._get_status("plan_to_watch") == Status.PLANNING.value

    def test_plan_to_read(self):
        assert self.importer._get_status("plan_to_read") == Status.PLANNING.value

    def test_on_hold(self):
        assert self.importer._get_status("on_hold") == Status.PAUSED.value

    def test_dropped(self):
        assert self.importer._get_status("dropped") == Status.DROPPED.value


class KitsuStatusMappingTests(TestCase):
    def setUp(self):
        self.importer = KitsuImporter.__new__(KitsuImporter)

    def test_completed(self):
        assert self.importer._get_status("completed") == Status.COMPLETED.value

    def test_current(self):
        assert self.importer._get_status("current") == Status.IN_PROGRESS.value

    def test_planned(self):
        assert self.importer._get_status("planned") == Status.PLANNING.value

    def test_on_hold(self):
        assert self.importer._get_status("on_hold") == Status.PAUSED.value

    def test_dropped(self):
        assert self.importer._get_status("dropped") == Status.DROPPED.value


class SimklStatusMappingTests(TestCase):
    def test_completed(self):
        assert _simkl_helpers.map_status("completed") == Status.COMPLETED.value

    def test_watching(self):
        assert _simkl_helpers.map_status("watching") == Status.IN_PROGRESS.value

    def test_plantowatch(self):
        assert _simkl_helpers.map_status("plantowatch") == Status.PLANNING.value

    def test_hold(self):
        assert _simkl_helpers.map_status("hold") == Status.PAUSED.value

    def test_dropped(self):
        assert _simkl_helpers.map_status("dropped") == Status.DROPPED.value

    def test_unknown_falls_back_to_in_progress(self):
        assert _simkl_helpers.map_status("garbage") == Status.IN_PROGRESS.value
        assert _simkl_helpers.map_status("") == Status.IN_PROGRESS.value
        assert _simkl_helpers.map_status(None) == Status.IN_PROGRESS.value
