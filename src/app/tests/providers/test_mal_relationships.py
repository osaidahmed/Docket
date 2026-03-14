from django.test import TestCase

from app.models import Item, ItemRelationship, MediaTypes, Sources

_IMG = "http://example.com/image.jpg"


def _make_item(media_id, title="Existing Anime"):
    return Item.objects.create(
        media_id=media_id,
        source=Sources.MAL.value,
        media_type=MediaTypes.ANIME.value,
        title=title,
        image=_IMG,
    )


class SaveAnimeRelationshipsTests(TestCase):
    """Test _save_anime_relationships from the MAL provider."""

    def test_creates_relationship_for_sequel(self):
        from app.providers.mal import _save_anime_relationships

        item = _make_item("100", "Main Anime")
        related = [
            {
                "media_id": 200,
                "title": "Sequel Anime",
                "image": _IMG,
                "relation_type": "sequel",
            }
        ]
        _save_anime_relationships(100, related)
        self.assertEqual(ItemRelationship.objects.count(), 1)
        rel = ItemRelationship.objects.first()
        self.assertEqual(rel.from_item, item)
        self.assertEqual(rel.relation_type, "sequel")

    def test_creates_relationship_for_prequel(self):
        from app.providers.mal import _save_anime_relationships

        _make_item("101", "Main Anime")
        related = [
            {
                "media_id": 201,
                "title": "Prequel Anime",
                "image": _IMG,
                "relation_type": "prequel",
            }
        ]
        _save_anime_relationships(101, related)
        self.assertEqual(ItemRelationship.objects.count(), 1)

    def test_skips_non_groupable_relation_types(self):
        from app.providers.mal import _save_anime_relationships

        _make_item("102", "Main Anime")
        related = [
            {
                "media_id": 202,
                "title": "Side Story",
                "image": _IMG,
                "relation_type": "side_story",
            },
            {
                "media_id": 203,
                "title": "Spin Off",
                "image": _IMG,
                "relation_type": "spin_off",
            },
        ]
        _save_anime_relationships(102, related)
        self.assertEqual(ItemRelationship.objects.count(), 0)

    def test_skips_when_from_item_does_not_exist(self):
        from app.providers.mal import _save_anime_relationships

        related = [
            {
                "media_id": 204,
                "title": "Sequel",
                "image": _IMG,
                "relation_type": "sequel",
            }
        ]
        _save_anime_relationships(999, related)
        self.assertEqual(ItemRelationship.objects.count(), 0)
        self.assertFalse(
            Item.objects.filter(media_id="999").exists(),
            "Should NOT create stub Item for from_item",
        )

    def test_creates_stub_item_for_to_item_with_title(self):
        from app.providers.mal import _save_anime_relationships

        _make_item("103", "Main Anime")
        related = [
            {
                "media_id": 303,
                "title": "Related Anime Title",
                "image": _IMG,
                "relation_type": "sequel",
            }
        ]
        _save_anime_relationships(103, related)
        stub = Item.objects.get(media_id="303")
        self.assertEqual(
            stub.title,
            "Related Anime Title",
            "Stub item should have title from API, not empty",
        )

    def test_does_not_overwrite_existing_to_item_title(self):
        from app.providers.mal import _save_anime_relationships

        _make_item("104", "Main Anime")
        existing = _make_item("304", "Original Title")
        related = [
            {
                "media_id": 304,
                "title": "API Title",
                "image": _IMG,
                "relation_type": "sequel",
            }
        ]
        _save_anime_relationships(104, related)
        existing.refresh_from_db()
        self.assertEqual(
            existing.title,
            "Original Title",
            "get_or_create should not overwrite existing title",
        )

    def test_empty_related_list(self):
        from app.providers.mal import _save_anime_relationships

        _make_item("105", "Main Anime")
        _save_anime_relationships(105, [])
        self.assertEqual(ItemRelationship.objects.count(), 0)

    def test_duplicate_relationship_not_created(self):
        from app.providers.mal import _save_anime_relationships

        _make_item("106", "Main")
        related = [
            {
                "media_id": 306,
                "title": "Sequel",
                "image": _IMG,
                "relation_type": "sequel",
            }
        ]
        _save_anime_relationships(106, related)
        _save_anime_relationships(106, related)
        self.assertEqual(
            ItemRelationship.objects.count(),
            1,
            "Should not create duplicate relationships",
        )
