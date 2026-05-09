import datetime
from decimal import Decimal
from unittest.mock import MagicMock

from defusedxml.ElementTree import fromstring as xml_fromstring
from django.test import TestCase

from app._types import MediaTypes, Sources, Status
from app.services.mal_xml import format_mal_xml


def _make_media(
    *,
    source=Sources.MAL.value,
    media_id="1",
    title="Cowboy Bebop",
    status=Status.IN_PROGRESS.value,
    score=None,
    progress=2,
    start_date=None,
    end_date=None,
    notes="",
    repeats=1,
):
    media = MagicMock()
    media.item.media_id = media_id
    media.item.source = source
    media.item.title = title
    media.status = status
    media.score = score
    media.progress = progress
    media.start_date = start_date
    media.end_date = end_date
    media.notes = notes
    media.repeats = repeats
    return media


def _parse(body):
    return xml_fromstring(body)


def _find(root, path):
    elem = root.find(path)
    assert elem is not None, f"missing element: {path}"
    return elem


def _text(root, path):
    return _find(root, path).text


class AnimeStructureTests(TestCase):
    def test_root_and_declaration(self):
        body, _ = format_mal_xml([_make_media()], "alice", MediaTypes.ANIME.value)
        self.assertTrue(body.startswith("<?xml"))
        self.assertEqual(_parse(body).tag, "myanimelist")

    def test_myinfo_export_type_anime(self):
        body, _ = format_mal_xml([_make_media()], "alice", MediaTypes.ANIME.value)
        root = _parse(body)
        self.assertEqual(_text(root, "myinfo/user_export_type"), "1")
        self.assertEqual(_text(root, "myinfo/user_name"), "alice")
        self.assertEqual(_text(root, "myinfo/user_total_anime"), "1")

    def test_anime_status_mapping_all_five(self):
        cases = {
            Status.COMPLETED.value: "Completed",
            Status.IN_PROGRESS.value: "Watching",
            Status.PLANNING.value: "Plan to Watch",
            Status.PAUSED.value: "On-Hold",
            Status.DROPPED.value: "Dropped",
        }
        for docket_status, mal_status in cases.items():
            body, _ = format_mal_xml(
                [_make_media(status=docket_status)],
                "u",
                MediaTypes.ANIME.value,
            )
            self.assertEqual(_text(_parse(body), "anime/my_status"), mal_status)

    def test_score_rounding_and_null(self):
        cases = [(Decimal("7.8"), "7"), (Decimal("10.0"), "10"), (None, "0")]
        for score, expected in cases:
            body, _ = format_mal_xml(
                [_make_media(score=score)], "u", MediaTypes.ANIME.value
            )
            self.assertEqual(_text(_parse(body), "anime/my_score"), expected)

    def test_date_formatting_and_null(self):
        dt = datetime.datetime(2023, 6, 1, 12, 0)
        body, _ = format_mal_xml(
            [_make_media(start_date=dt, end_date=None)],
            "u",
            MediaTypes.ANIME.value,
        )
        root = _parse(body)
        self.assertEqual(_text(root, "anime/my_start_date"), "2023-06-01")
        self.assertEqual(_text(root, "anime/my_finish_date"), "0000-00-00")

    def test_update_on_import_present(self):
        body, _ = format_mal_xml(
            [_make_media(), _make_media(media_id="2")],
            "u",
            MediaTypes.ANIME.value,
        )
        for entry in _parse(body).findall("anime"):
            self.assertEqual(entry.findtext("update_on_import"), "1")

    def test_repeats_times_watched(self):
        body, _ = format_mal_xml([_make_media(repeats=3)], "u", MediaTypes.ANIME.value)
        self.assertEqual(_text(_parse(body), "anime/my_times_watched"), "2")

    def test_xml_special_chars_escaped(self):
        body, _ = format_mal_xml(
            [_make_media(title="A & B <Tachikoma>")],
            "u",
            MediaTypes.ANIME.value,
        )
        self.assertIn("A &amp; B &lt;Tachikoma&gt;", body)
        self.assertEqual(_text(_parse(body), "anime/series_title"), "A & B <Tachikoma>")

    def test_series_animedb_id_is_int_string(self):
        body, _ = format_mal_xml(
            [_make_media(media_id="42")], "u", MediaTypes.ANIME.value
        )
        self.assertEqual(_text(_parse(body), "anime/series_animedb_id"), "42")


class MangaStructureTests(TestCase):
    def test_myinfo_export_type_manga(self):
        body, _ = format_mal_xml([_make_media()], "u", MediaTypes.MANGA.value)
        root = _parse(body)
        self.assertEqual(_text(root, "myinfo/user_export_type"), "2")
        self.assertEqual(_text(root, "myinfo/user_total_manga"), "1")

    def test_manga_status_mapping(self):
        cases = {
            Status.IN_PROGRESS.value: "Reading",
            Status.PLANNING.value: "Plan to Read",
            Status.COMPLETED.value: "Completed",
            Status.PAUSED.value: "On-Hold",
            Status.DROPPED.value: "Dropped",
        }
        for docket_status, mal_status in cases.items():
            body, _ = format_mal_xml(
                [_make_media(status=docket_status)],
                "u",
                MediaTypes.MANGA.value,
            )
            self.assertEqual(_text(_parse(body), "manga/my_status"), mal_status)

    def test_read_volumes_zero(self):
        body, _ = format_mal_xml(
            [_make_media(progress=42)], "u", MediaTypes.MANGA.value
        )
        root = _parse(body)
        self.assertEqual(_text(root, "manga/my_read_volumes"), "0")
        self.assertEqual(_text(root, "manga/my_read_chapters"), "42")

    def test_repeats_times_read(self):
        body, _ = format_mal_xml([_make_media(repeats=4)], "u", MediaTypes.MANGA.value)
        self.assertEqual(_text(_parse(body), "manga/my_times_read"), "3")


class SkipAndCountingTests(TestCase):
    def test_skip_non_mal_source(self):
        entries = [
            _make_media(),
            _make_media(source=Sources.MANUAL.value, media_id="1"),
        ]
        body, skipped = format_mal_xml(entries, "u", MediaTypes.ANIME.value)
        self.assertEqual(skipped, 1)
        self.assertIn("Skipped 1 entries without MAL IDs", body)
        self.assertEqual(len(_parse(body).findall("anime")), 1)

    def test_skip_unparseable_media_id(self):
        entries = [_make_media(), _make_media(media_id="abc")]
        body, skipped = format_mal_xml(entries, "u", MediaTypes.ANIME.value)
        self.assertEqual(skipped, 1)
        self.assertEqual(len(_parse(body).findall("anime")), 1)

    def test_empty_list_valid_xml(self):
        body, skipped = format_mal_xml([], "u", MediaTypes.ANIME.value)
        self.assertEqual(skipped, 0)
        root = _parse(body)
        self.assertEqual(root.tag, "myanimelist")
        self.assertEqual(_text(root, "myinfo/user_total_anime"), "0")
        self.assertEqual(_text(root, "myinfo/user_total_watching"), "0")
        self.assertEqual(root.findall("anime"), [])

    def test_myinfo_totals_count_post_mapping(self):
        entries = [
            _make_media(status=Status.COMPLETED.value, media_id="1"),
            _make_media(status=Status.COMPLETED.value, media_id="2"),
            _make_media(status=Status.COMPLETED.value, media_id="3"),
            _make_media(status=Status.IN_PROGRESS.value, media_id="4"),
        ]
        body, _ = format_mal_xml(entries, "u", MediaTypes.ANIME.value)
        root = _parse(body)
        self.assertEqual(_text(root, "myinfo/user_total_completed"), "3")
        self.assertEqual(_text(root, "myinfo/user_total_watching"), "1")
        self.assertEqual(_text(root, "myinfo/user_total_onhold"), "0")
        self.assertEqual(_text(root, "myinfo/user_total_dropped"), "0")
        self.assertEqual(_text(root, "myinfo/user_total_plantowatch"), "0")

    def test_manga_myinfo_totals_use_manga_tags(self):
        entries = [
            _make_media(status=Status.IN_PROGRESS.value, media_id="1"),
            _make_media(status=Status.PLANNING.value, media_id="2"),
        ]
        body, _ = format_mal_xml(entries, "u", MediaTypes.MANGA.value)
        root = _parse(body)
        self.assertEqual(_text(root, "myinfo/user_total_reading"), "1")
        self.assertEqual(_text(root, "myinfo/user_total_plantoread"), "1")
