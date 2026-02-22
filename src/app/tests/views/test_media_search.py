from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from app.models import (
    Anime,
    Item,
    MediaTypes,
    Movie,
    Sources,
    Status,
)


class MediaSearchViewTests(TestCase):
    """Test the media search view."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    @patch("app.providers.services.search")
    def test_media_search_view(self, mock_search):
        """Test the media search view."""
        mock_search.return_value = {
            "page": 1,
            "total_results": 1,
            "total_pages": 1,
            "results": [
                {
                    "media_id": "238",
                    "title": "Test Movie",
                    "media_type": MediaTypes.MOVIE.value,
                    "source": Sources.TMDB.value,
                    "image": "http://example.com/image.jpg",
                    "synopsis": "A test movie synopsis.",
                },
            ],
        }

        response = self.client.get(
            reverse("search") + "?media_type=movie&q=test",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/search.html")

        self.user.refresh_from_db()
        self.assertEqual(self.user.last_search_type, MediaTypes.MOVIE.value)

        mock_search.assert_called_once_with(
            MediaTypes.MOVIE.value,
            "test",
            1,
            Sources.TMDB.value,
        )

    @patch("app.providers.services.search_all")
    def test_unified_search_view(self, mock_search_all):
        """Test the unified search view with media_type=all."""
        mock_search_all.return_value = [
            {
                "media_type": MediaTypes.ANIME.value,
                "results": [
                    {
                        "media_id": "1",
                        "title": "Test Anime",
                        "media_type": MediaTypes.ANIME.value,
                        "source": Sources.MAL.value,
                        "image": "http://example.com/anime.jpg",
                        "synopsis": "An anime synopsis.",
                    },
                ],
            },
            {
                "media_type": MediaTypes.TV.value,
                "results": [
                    {
                        "media_id": "2",
                        "title": "Test TV",
                        "media_type": MediaTypes.TV.value,
                        "source": Sources.TMDB.value,
                        "image": "http://example.com/tv.jpg",
                        "synopsis": "A TV synopsis.",
                    },
                ],
            },
        ]

        response = self.client.get(
            reverse("search") + "?media_type=all&q=test",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/search_unified.html")

        self.user.refresh_from_db()
        self.assertNotEqual(self.user.last_search_type, "all")

        mock_search_all.assert_called_once()

    @patch("app.providers.services.search_all")
    def test_unified_search_no_results(self, mock_search_all):
        """Test the unified search view with no results."""
        mock_search_all.return_value = []

        response = self.client.get(
            reverse("search") + "?media_type=all&q=nonexistent",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/search_unified.html")
        self.assertEqual(
            response.context["grouped_results"],
            [],
        )


class QuickAddViewTests(TestCase):
    """Test the quick_add view."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    @patch("app.providers.services.get_media_metadata")
    def test_quick_add_creates_planning_media(self, mock_metadata):
        """Test that quick_add creates media with Planning status."""
        mock_metadata.return_value = {
            "title": "Test Movie",
            "image": "http://example.com/image.jpg",
        }

        response = self.client.post(
            reverse("quick_add"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/search_action.html")
        movie = Movie.objects.get(item__media_id="238", user=self.user)
        self.assertEqual(movie.status, Status.PLANNING.value)
        self.assertIsNone(movie.score)
        self.assertEqual(movie.progress, 0)

    @patch("app.providers.services.get_media_metadata")
    def test_quick_add_creates_item(self, mock_metadata):
        """Test that quick_add creates an Item with metadata."""
        mock_metadata.return_value = {
            "title": "Test Anime",
            "image": "http://example.com/anime.jpg",
        }

        self.client.post(
            reverse("quick_add"),
            {
                "media_id": "1",
                "source": Sources.MAL.value,
                "media_type": MediaTypes.ANIME.value,
            },
        )

        item = Item.objects.get(media_id="1", source=Sources.MAL.value)
        self.assertEqual(item.title, "Test Anime")
        self.assertEqual(item.image, "http://example.com/anime.jpg")

    def test_quick_add_already_tracked_no_duplicate(self):
        """Test that quick_add does not create duplicates."""
        item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        response = self.client.post(
            reverse("quick_add"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Movie.objects.filter(item__media_id="238", user=self.user).count(),
            1,
        )

    def test_quick_add_existing_item_skips_metadata_fetch(self):
        """Test that quick_add skips API call when Item already exists."""
        Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )

        with patch(
            "app.providers.services.get_media_metadata",
        ) as mock_metadata:
            self.client.post(
                reverse("quick_add"),
                {
                    "media_id": "238",
                    "source": Sources.TMDB.value,
                    "media_type": MediaTypes.MOVIE.value,
                },
            )
            mock_metadata.assert_not_called()

        self.assertTrue(
            Movie.objects.filter(
                item__media_id="238",
                user=self.user,
            ).exists(),
        )

    def test_quick_add_requires_post(self):
        """Test that quick_add rejects GET requests."""
        response = self.client.get(reverse("quick_add"))
        self.assertEqual(response.status_code, 405)

    @patch("app.providers.services.get_media_metadata")
    def test_quick_add_populates_synopsis(self, mock_metadata):
        """Test that quick_add persists synopsis on the Item."""
        mock_metadata.return_value = {
            "title": "Test Movie",
            "image": "http://example.com/image.jpg",
            "synopsis": "A great movie about testing.",
        }

        self.client.post(
            reverse("quick_add"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        item = Item.objects.get(media_id="238", source=Sources.TMDB.value)
        self.assertEqual(item.synopsis, "A great movie about testing.")


class QuickArchiveViewTests(TestCase):
    """Test the quick_archive view."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

    @patch("app.providers.services.get_media_metadata")
    def test_quick_archive_creates_completed_media(self, mock_metadata):
        """Test that quick_archive creates media with Completed status."""
        mock_metadata.return_value = {
            "title": "Test Movie",
            "image": "http://example.com/image.jpg",
            "max_progress": None,
        }

        response = self.client.post(
            reverse("quick_archive"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/search_action.html")
        movie = Movie.objects.get(item__media_id="238", user=self.user)
        self.assertEqual(movie.status, Status.COMPLETED.value)

    def test_quick_archive_already_tracked_no_duplicate(self):
        """Test that quick_archive does not create duplicates."""
        item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )
        Movie.objects.create(
            item=item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

        response = self.client.post(
            reverse("quick_archive"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Movie.objects.filter(item__media_id="238", user=self.user).count(),
            1,
        )

    @patch("app.providers.services.get_media_metadata")
    def test_quick_archive_existing_item_skips_metadata_fetch(self, mock_metadata):
        """Test that quick_archive reuses existing Item without fetching metadata."""
        mock_metadata.return_value = {"max_progress": None}
        Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )

        self.client.post(
            reverse("quick_archive"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        mock_metadata.assert_called_once()
        movie = Movie.objects.get(item__media_id="238", user=self.user)
        self.assertEqual(movie.status, Status.COMPLETED.value)

    def test_quick_archive_requires_post(self):
        """Test that quick_archive rejects GET requests."""
        response = self.client.get(reverse("quick_archive"))
        self.assertEqual(response.status_code, 405)


class QuickCompleteViewTests(TestCase):
    """Test the quick_complete view."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

        self.item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Test Anime",
            image="http://example.com/image.jpg",
        )
        self.anime = Anime.objects.create(
            item=self.item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )

    def test_quick_complete_marks_completed(self):
        """Test that quick_complete sets status to Completed."""
        response = self.client.post(
            reverse("quick_complete"),
            {
                "media_type": MediaTypes.ANIME.value,
                "instance_id": str(self.anime.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.anime.refresh_from_db()
        self.assertEqual(self.anime.status, Status.COMPLETED.value)

    def test_quick_complete_returns_confirmation_with_archive(self):
        """Test that quick_complete returns confirmation with OOB archive card."""
        response = self.client.post(
            reverse("quick_complete"),
            {
                "media_type": MediaTypes.ANIME.value,
                "instance_id": str(self.anime.id),
            },
        )

        self.assertTemplateUsed(response, "app/components/backlog_completed.html")
        self.assertTemplateUsed(response, "app/components/backlog_card_archived.html")
        self.assertContains(response, "hx-swap-oob")

    def test_quick_complete_updates_archive_count(self):
        """Test that quick_complete response includes OOB archive count update."""
        response = self.client.post(
            reverse("quick_complete"),
            {
                "media_type": MediaTypes.ANIME.value,
                "instance_id": str(self.anime.id),
            },
        )

        content = response.content.decode()
        self.assertIn('id="archive-count"', content)
        self.assertIn("(1)", content)

    def test_quick_complete_archive_count_deduplicates_rewatches(self):
        """Test that rewatched media counts as 1 in archive, not per instance."""
        # First instance: already completed
        self.anime.status = Status.COMPLETED.value
        self.anime.save()

        # Rewatch: second instance of same item, now complete it
        rewatch = Anime.objects.create(
            item=self.item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
        )
        response = self.client.post(
            reverse("quick_complete"),
            {
                "media_type": MediaTypes.ANIME.value,
                "instance_id": str(rewatch.id),
            },
        )

        content = response.content.decode()
        # Two completed instances of same item should count as 1
        self.assertIn("(1)", content)
        self.assertNotIn("(2)", content)

    def test_quick_complete_requires_post(self):
        """Test that quick_complete rejects GET requests."""
        response = self.client.get(reverse("quick_complete"))
        self.assertEqual(response.status_code, 405)


class BacklogSaveViewTests(TestCase):
    """Test the backlog_save view."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

        self.item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Test Anime",
            image="http://example.com/image.jpg",
        )
        self.anime = Anime.objects.create(
            item=self.item,
            user=self.user,
            status=Status.IN_PROGRESS.value,
            progress=5,
        )

    def test_backlog_save_updates_fields(self):
        """Test that backlog_save updates media fields."""
        response = self.client.post(
            reverse("backlog_save"),
            {
                "media_id": "1",
                "source": Sources.MAL.value,
                "media_type": MediaTypes.ANIME.value,
                "instance_id": str(self.anime.id),
                "score": "8.5",
                "progress": "10",
                "status": Status.IN_PROGRESS.value,
                "start_date": "",
                "end_date": "",
                "link": "https://example.com",
                "notes": "Good show",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "app/components/backlog_card.html")
        self.anime.refresh_from_db()
        self.assertEqual(float(self.anime.score), 8.5)
        self.assertEqual(self.anime.progress, 10)
        self.assertEqual(self.anime.link, "https://example.com")
        self.assertEqual(self.anime.notes, "Good show")

    def test_backlog_save_requires_post(self):
        """Test that backlog_save rejects GET requests."""
        response = self.client.get(reverse("backlog_save"))
        self.assertEqual(response.status_code, 405)

    def test_backlog_save_validation_error(self):
        """Test that invalid data returns card with form expanded."""
        response = self.client.post(
            reverse("backlog_save"),
            {
                "media_id": "1",
                "source": Sources.MAL.value,
                "media_type": MediaTypes.ANIME.value,
                "instance_id": str(self.anime.id),
                "score": "15",
                "progress": "5",
                "status": Status.IN_PROGRESS.value,
                "start_date": "",
                "end_date": "",
                "link": "",
                "notes": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("form_errors", response.context)
        self.assertTrue(response.context["show_edit"])

    @patch("app.providers.services.get_media_metadata")
    def test_unflag_rewatch_deletes_planning_instance(self, mock_metadata):
        """Unchecking rewatch on a Planning instance deletes it."""
        mock_metadata.return_value = {"max_progress": None}
        Anime.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
        )
        rewatch = Anime.objects.create(
            item=self.item,
            user=self.user,
            status=Status.PLANNING.value,
            is_rewatch=True,
        )

        response = self.client.post(
            reverse("backlog_save"),
            {
                "media_id": "1",
                "source": Sources.MAL.value,
                "media_type": MediaTypes.ANIME.value,
                "instance_id": str(rewatch.id),
                "score": "",
                "progress": "0",
                "status": Status.PLANNING.value,
                "start_date": "",
                "end_date": "",
                "link": "",
                "notes": "",
                # is_rewatch checkbox NOT included = unchecked
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Anime.objects.filter(id=rewatch.id).exists())
        self.assertTrue("HX-Refresh" in response)


class QuickRewatchViewTests(TestCase):
    """Test the quick_rewatch view."""

    def setUp(self):
        """Create a user and log in."""
        self.credentials = {"username": "test", "password": "12345"}
        self.user = get_user_model().objects.create_user(**self.credentials)
        self.client.login(**self.credentials)

        self.item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )

    @patch("app.providers.services.get_media_metadata")
    def test_quick_rewatch_creates_planning_instance(self, mock_metadata):
        """Test that quick_rewatch creates a new Planning instance."""
        mock_metadata.return_value = {"max_progress": None}
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
        )

        response = self.client.post(
            reverse("quick_rewatch"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        self.assertEqual(response.status_code, 200)
        movies = Movie.objects.filter(item=self.item, user=self.user)
        self.assertEqual(movies.count(), 2)
        newest = movies.order_by("-created_at").first()
        self.assertEqual(newest.status, Status.PLANNING.value)

    @patch("app.providers.services.get_media_metadata")
    def test_quick_rewatch_returns_completed_with_has_active(self, mock_metadata):
        """Test that quick_rewatch returns archived state with has_active."""
        mock_metadata.return_value = {"max_progress": None}
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
        )

        response = self.client.post(
            reverse("quick_rewatch"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        self.assertTemplateUsed(response, "app/components/search_action.html")
        self.assertEqual(response.context["media"].status, Status.COMPLETED.value)
        self.assertTrue(response.context["has_active"])

        content = response.content.decode()
        self.assertIn("Completed", content)
        self.assertNotIn("Rewatch", content)
        self.assertNotIn("quick_rewatch", content)
        self.assertNotIn("Planning", content)

    def test_quick_rewatch_prevents_duplicate_active(self):
        """Test that quick_rewatch returns existing active instead of creating."""
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.PLANNING.value,
        )

        response = self.client.post(
            reverse("quick_rewatch"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            Movie.objects.filter(item=self.item, user=self.user).count(),
            1,
        )

    @patch("app.providers.services.get_media_metadata")
    def test_quick_rewatch_archive_context(self, mock_metadata):
        """Test that source_context=archive returns confirmation template."""
        mock_metadata.return_value = {"max_progress": None}
        Movie.objects.create(
            item=self.item,
            user=self.user,
            status=Status.COMPLETED.value,
        )

        response = self.client.post(
            reverse("quick_rewatch"),
            {
                "media_id": "238",
                "source": Sources.TMDB.value,
                "media_type": MediaTypes.MOVIE.value,
                "source_context": "archive",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response, "app/components/backlog_rewatch_confirmed.html"
        )

    def test_quick_rewatch_requires_post(self):
        """Test that quick_rewatch rejects GET requests."""
        response = self.client.get(reverse("quick_rewatch"))
        self.assertEqual(response.status_code, 405)
