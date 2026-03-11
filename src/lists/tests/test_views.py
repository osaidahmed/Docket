from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from app.models import TV, Anime, Item, MediaTypes, Movie, Sources, Status
from lists.models import CustomList, CustomListItem


class ListsViewRenderTests(TestCase):
    """Tests for the lists view rendering."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.collaborator_credentials = {
            "username": "collaborator",
            "password": "12345",
        }
        cls.collaborator = get_user_model().objects.create_user(
            **cls.collaborator_credentials,
        )

        cls.list1 = CustomList.objects.create(
            name="Test List 1",
            description="Description 1",
            owner=cls.user,
        )
        cls.list2 = CustomList.objects.create(
            name="Test List 2",
            description="Description 2",
            owner=cls.user,
        )

        cls.list1.collaborators.add(cls.collaborator)

        cls.item1 = Item.objects.create(
            media_id="1",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
        )
        cls.item2 = Item.objects.create(
            media_id="2",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Test TV Show",
        )

        CustomListItem.objects.create(
            custom_list=cls.list1,
            item=cls.item1,
        )
        CustomListItem.objects.create(
            custom_list=cls.list2,
            item=cls.item2,
        )

    def setUp(self):
        self.factory = RequestFactory()

    def test_lists_owner_view(self):
        self.client.login(**self.credentials)
        response = self.client.get(reverse("lists"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "lists/custom_lists.html")
        self.assertIn("custom_lists", response.context)
        self.assertIn("form", response.context)

    def test_lists_collaborator_view(self):
        self.client.login(**self.collaborator_credentials)
        response = self.client.get(reverse("lists"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "lists/custom_lists.html")
        self.assertIn("custom_lists", response.context)
        self.assertIn("form", response.context)


class ListDetailRenderTests(TestCase):
    """Tests for list detail view rendering and authorization."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "testuser", "password": "testpassword"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.other_user = get_user_model().objects.create_user(
            username="otheruser",
            password="testpassword",
        )

        cls.custom_list = CustomList.objects.create(
            name="Test List",
            description="Test Description",
            owner=cls.user,
        )

        cls.movie_item = Item.objects.create(
            media_id="238",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
        )
        cls.tv_item = Item.objects.create(
            media_id="1668",
            source=Sources.TMDB.value,
            media_type=MediaTypes.TV.value,
            title="Test TV Show",
        )
        cls.anime_item = Item.objects.create(
            media_id="1",
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title="Test Anime",
        )

        CustomListItem.objects.create(
            custom_list=cls.custom_list,
            item=cls.movie_item,
        )
        CustomListItem.objects.create(
            custom_list=cls.custom_list,
            item=cls.tv_item,
        )
        CustomListItem.objects.create(
            custom_list=cls.custom_list,
            item=cls.anime_item,
        )

    def setUp(self):
        self.factory = RequestFactory()
        self.client.login(**self.credentials)

    @patch.object(get_user_model(), "update_preference")
    @patch.object(CustomList, "user_can_view")
    def test_list_detail_view(
        self,
        mock_user_can_view,
        mock_update_preference,
    ):
        mock_update_preference.side_effect = ["date_added", None]
        mock_user_can_view.return_value = True

        Movie.objects.create(
            item=self.movie_item,
            status=Status.COMPLETED.value,
            user=self.user,
        )
        TV.objects.create(
            item=self.tv_item,
            status=Status.IN_PROGRESS.value,
            user=self.user,
        )
        Anime.objects.create(
            item=self.anime_item,
            status=Status.PLANNING.value,
            user=self.user,
        )

        response = self.client.get(reverse("list_detail", args=[self.custom_list.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "lists/list_detail.html")

        self.assertEqual(response.context["custom_list"], self.custom_list)
        self.assertEqual(len(response.context["items"]), 3)
        self.assertEqual(response.context["current_sort"], "date_added")
        self.assertEqual(response.context["items_count"], 3)

    @patch.object(get_user_model(), "update_preference")
    @patch.object(CustomList, "user_can_view")
    def test_list_detail_view_unauthorized(
        self,
        mock_user_can_view,
        mock_update_preference,
    ):
        mock_update_preference.side_effect = ["date_added", None]
        mock_user_can_view.return_value = False

        response = self.client.get(reverse("list_detail", args=[self.custom_list.id]))
        self.assertEqual(response.status_code, 404)


class CreateListViewTest(TestCase):
    """Test case for the create list view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

    def setUp(self):
        self.client = Client()
        self.client.login(**self.credentials)

    def test_create_list(self):
        self.client.post(
            reverse("list_create"),
            {"name": "New List", "description": "New Description"},
        )
        self.assertEqual(CustomList.objects.count(), 1)
        new_list = CustomList.objects.first()
        self.assertEqual(new_list.name, "New List")
        self.assertEqual(new_list.description, "New Description")
        self.assertEqual(new_list.owner, self.user)


class EditListViewTest(TestCase):
    """Test case for the edit list view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.collaborator_credentials = {
            "username": "collaborator",
            "password": "12345",
        }
        cls.collaborator = get_user_model().objects.create_user(
            **cls.collaborator_credentials,
        )
        cls.list = CustomList.objects.create(name="Test List", owner=cls.user)
        cls.list.collaborators.add(cls.collaborator)

    def setUp(self):
        self.client = Client()

    def test_edit_list(self):
        self.client.login(**self.credentials)
        self.client.post(
            reverse("list_edit"),
            {
                "list_id": self.list.id,
                "name": "Updated List",
                "description": "Updated Description",
            },
        )
        self.list.refresh_from_db()
        self.assertEqual(self.list.name, "Updated List")
        self.assertEqual(self.list.description, "Updated Description")

    def test_edit_list_collaborator(self):
        self.client.login(**self.collaborator_credentials)
        self.client.post(
            reverse("list_edit"),
            {
                "list_id": self.list.id,
                "name": "Updated List",
                "description": "Updated Description",
            },
        )
        self.list.refresh_from_db()
        self.assertEqual(self.list.name, "Updated List")
        self.assertEqual(self.list.description, "Updated Description")


class DeleteListViewTest(TestCase):
    """Test the delete view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.collaborator_credentials = {
            "username": "collaborator",
            "password": "12345",
        }
        cls.collaborator = get_user_model().objects.create_user(
            **cls.collaborator_credentials,
        )
        cls.list = CustomList.objects.create(name="Test List", owner=cls.user)
        cls.list.collaborators.add(cls.collaborator)

    def setUp(self):
        self.client = Client()

    def test_delete_list(self):
        self.client.login(**self.credentials)
        self.client.post(reverse("list_delete"), {"list_id": self.list.id})
        self.assertEqual(CustomList.objects.count(), 0)

    def test_delete_list_collaborator(self):
        self.client.login(**self.collaborator_credentials)
        self.client.post(reverse("list_delete"), {"list_id": self.list.id})
        self.assertEqual(CustomList.objects.count(), 1)


class ListsModalViewTests(TestCase):
    """Tests for the lists_modal view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.list1 = CustomList.objects.create(
            name="Test List 1",
            owner=cls.user,
        )
        cls.list2 = CustomList.objects.create(
            name="Test List 2",
            owner=cls.user,
        )

    def setUp(self):
        self.client = Client()
        self.client.login(**self.credentials)

    def test_lists_modal_view(self):
        response = self.client.get(
            reverse(
                "lists_modal",
                args=[Sources.TMDB.value, MediaTypes.MOVIE.value, 10494],
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "lists/components/fill_lists.html")
        self.assertIn("item", response.context)
        self.assertIn("custom_lists", response.context)

    @patch("app.providers.services.get_media_metadata")
    @patch("lists.models.CustomList.objects.get_user_lists_with_item")
    def test_lists_modal_view_with_existing_item(
        self,
        mock_get_lists,
        mock_get_metadata,
    ):
        Item.objects.create(
            media_id="123",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Existing Movie",
            image="http://example.com/image.jpg",
        )

        mock_get_lists.return_value = [self.list1, self.list2]

        mock_get_metadata.return_value = {
            "title": "Existing Movie",
            "image": "http://example.com/image.jpg",
        }

        response = self.client.get(
            reverse(
                "lists_modal",
                args=[Sources.TMDB.value, MediaTypes.MOVIE.value, "123"],
            ),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "lists/components/fill_lists.html")

        self.assertEqual(response.context["item"].media_id, "123")
        self.assertEqual(response.context["item"].title, "Existing Movie")
        self.assertEqual(len(response.context["custom_lists"]), 2)

    @patch("app.providers.services.get_media_metadata")
    @patch("lists.models.CustomList.objects.get_user_lists_with_item")
    def test_lists_modal_view_with_new_item(self, mock_get_lists, mock_get_metadata):
        mock_get_lists.return_value = [self.list1, self.list2]

        mock_get_metadata.return_value = {
            "title": "New Movie",
            "image": "http://example.com/new_image.jpg",
        }

        response = self.client.get(
            reverse(
                "lists_modal",
                args=[Sources.TMDB.value, MediaTypes.MOVIE.value, "999"],
            ),
        )
        self.assertEqual(response.status_code, 200)

        self.assertTrue(
            Item.objects.filter(media_id="999", source=Sources.TMDB.value).exists(),
        )
        new_item = Item.objects.get(media_id="999", source=Sources.TMDB.value)
        self.assertEqual(new_item.title, "New Movie")
        self.assertEqual(new_item.image, "http://example.com/new_image.jpg")

    @patch("app.providers.services.get_media_metadata")
    @patch("lists.models.CustomList.objects.get_user_lists_with_item")
    def test_lists_modal_view_with_season(self, mock_get_lists, mock_get_metadata):
        mock_get_lists.return_value = [self.list1, self.list2]

        mock_get_metadata.return_value = {
            "title": "TV Show Season 1",
            "image": "http://example.com/season.jpg",
        }

        response = self.client.get(
            reverse(
                "lists_modal",
                args=[Sources.TMDB.value, MediaTypes.SEASON.value, "123", "1"],
            ),
        )
        self.assertEqual(response.status_code, 200)

        self.assertTrue(
            Item.objects.filter(
                media_id="123",
                source=Sources.TMDB.value,
                media_type=MediaTypes.SEASON.value,
                season_number=1,
            ).exists(),
        )


class ListItemToggleTests(TestCase):
    """Tests for the list_item_toggle view."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "test", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)

        cls.collaborator_credentials = {
            "username": "collaborator",
            "password": "12345",
        }
        cls.collaborator = get_user_model().objects.create_user(
            **cls.collaborator_credentials,
        )

        cls.other_credentials = {
            "username": "otheruser",
            "password": "testpassword",
        }
        cls.other_user = get_user_model().objects.create_user(
            **cls.other_credentials,
        )

        cls.list = CustomList.objects.create(name="Test List", owner=cls.user)
        cls.list.collaborators.add(cls.collaborator)

        cls.item = Item.objects.create(
            media_id=1,
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Test Movie",
            image="http://example.com/image.jpg",
        )

    def setUp(self):
        self.client = Client()

    def test_list_item_owner_toggle(self):
        self.client.login(**self.credentials)
        response = self.client.post(
            reverse("list_item_toggle"),
            {
                "item_id": self.item.id,
                "custom_list_id": self.list.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.item, self.list.items.all())

    def test_list_item_owner_toggle_remove(self):
        self.client.login(**self.credentials)
        self.list.items.add(self.item)
        response = self.client.post(
            reverse("list_item_toggle"),
            {
                "item_id": self.item.id,
                "custom_list_id": self.list.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.item, self.list.items.all())

    def test_list_item_collaborator_toggle(self):
        self.client.login(**self.collaborator_credentials)
        response = self.client.post(
            reverse("list_item_toggle"),
            {
                "item_id": self.item.id,
                "custom_list_id": self.list.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.item, self.list.items.all())

    def test_list_item_collaborator_toggle_remove(self):
        self.client.login(**self.collaborator_credentials)
        self.list.items.add(self.item)
        response = self.client.post(
            reverse("list_item_toggle"),
            {
                "item_id": self.item.id,
                "custom_list_id": self.list.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.item, self.list.items.all())

    def test_list_item_toggle_nonexistent_list(self):
        self.client.login(**self.credentials)
        response = self.client.post(
            reverse("list_item_toggle"),
            {
                "item_id": self.item.id,
                "custom_list_id": 999,
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_list_item_toggle_nonexistent_item(self):
        self.client.login(**self.credentials)
        response = self.client.post(
            reverse("list_item_toggle"),
            {
                "item_id": 999,
                "custom_list_id": self.list.id,
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_list_item_toggle_unauthorized_list(self):
        self.client.login(**self.credentials)

        other_list = CustomList.objects.create(
            name="Other User's List",
            owner=self.other_user,
        )

        response = self.client.post(
            reverse("list_item_toggle"),
            {
                "item_id": self.item.id,
                "custom_list_id": other_list.id,
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_list_item_toggle_template_context(self):
        self.client.login(**self.credentials)
        response = self.client.post(
            reverse("list_item_toggle"),
            {
                "item_id": self.item.id,
                "custom_list_id": self.list.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "lists/components/list_item_button.html")

        self.assertEqual(response.context["custom_list"], self.list)
        self.assertEqual(response.context["item"], self.item)
        self.assertTrue(response.context["has_item"])

        response = self.client.post(
            reverse("list_item_toggle"),
            {
                "item_id": self.item.id,
                "custom_list_id": self.list.id,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_item"])
