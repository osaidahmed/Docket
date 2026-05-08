from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from app.models import TV, Anime, Item, MediaTypes, Movie, Sources, Status
from lists.models import CustomList, CustomListItem


class ListsViewFilterTests(TestCase):
    """Tests for lists view search, sorting, HTMX, and pagination."""

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

    @patch.object(get_user_model(), "update_preference")
    def test_lists_view_search_filter(self, mock_update_preference):
        mock_update_preference.return_value = "name"
        self.client.login(**self.credentials)

        response = self.client.get(reverse("lists") + "?q=List 1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["custom_lists"]), 1)
        self.assertEqual(response.context["custom_lists"][0].name, "Test List 1")

        response = self.client.get(reverse("lists") + "?q=Description 2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["custom_lists"]), 1)
        self.assertEqual(response.context["custom_lists"][0].name, "Test List 2")

    @patch.object(get_user_model(), "update_preference")
    def test_lists_view_sorting(self, mock_update_preference):
        self.client.login(**self.credentials)

        mock_update_preference.return_value = "name"
        response = self.client.get(reverse("lists") + "?sort=name")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_sort"], "name")

        mock_update_preference.return_value = "items_count"
        response = self.client.get(reverse("lists") + "?sort=items_count")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_sort"], "items_count")

        mock_update_preference.return_value = "newest_first"
        response = self.client.get(reverse("lists") + "?sort=newest_first")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_sort"], "newest_first")

        mock_update_preference.return_value = "last_item_added"
        response = self.client.get(reverse("lists"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_sort"], "last_item_added")

    @patch.object(get_user_model(), "update_preference")
    def test_lists_view_htmx_request(self, mock_update_preference):
        mock_update_preference.return_value = "name"
        self.client.login(**self.credentials)

        response = self.client.get(
            reverse("lists"),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "lists/components/list_grid.html")
        self.assertIn("custom_lists", response.context)

    @patch.object(get_user_model(), "update_preference")
    def test_lists_view_pagination(self, mock_update_preference):
        mock_update_preference.return_value = "name"
        self.client.login(**self.credentials)

        for i in range(25):
            CustomList.objects.create(
                name=f"Paginated List {i}",
                owner=self.user,
            )

        response = self.client.get(reverse("lists"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["custom_lists"]), 20)

        response = self.client.get(reverse("lists") + "?page=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["custom_lists"]), 7)


class ApplyListsSortOrderingTests(TestCase):
    """Pin actual ordering of _apply_lists_sort branches with distinguishable fixtures."""

    @classmethod
    def setUpTestData(cls):
        cls.credentials = {"username": "sortuser", "password": "12345"}
        cls.user = get_user_model().objects.create_user(**cls.credentials)
        cls.alpha = CustomList.objects.create(
            name="Alpha",
            description="A",
            owner=cls.user,
        )
        cls.beta = CustomList.objects.create(
            name="Beta",
            description="B",
            owner=cls.user,
        )
        cls.gamma = CustomList.objects.create(
            name="Gamma",
            description="C",
            owner=cls.user,
        )
        for i in range(3):
            item = Item.objects.create(
                media_id=f"alpha-{i}",
                source=Sources.TMDB.value,
                media_type=MediaTypes.MOVIE.value,
                title=f"Alpha Item {i}",
            )
            CustomListItem.objects.create(custom_list=cls.alpha, item=item)
        item = Item.objects.create(
            media_id="beta-0",
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title="Beta Item",
        )
        CustomListItem.objects.create(custom_list=cls.beta, item=item)

    def setUp(self):
        self.client.login(**self.credentials)

    def _names(self, response):
        return [lst.name for lst in response.context["custom_lists"]]

    @patch.object(get_user_model(), "update_preference")
    def test_name_sort_returns_alphabetical(self, mock_update_preference):
        mock_update_preference.return_value = "name"
        response = self.client.get(reverse("lists") + "?sort=name")
        assert self._names(response) == ["Alpha", "Beta", "Gamma"]

    @patch.object(get_user_model(), "update_preference")
    def test_items_count_sort_returns_descending(self, mock_update_preference):
        mock_update_preference.return_value = "items_count"
        response = self.client.get(reverse("lists") + "?sort=items_count")
        names = self._names(response)
        assert names[0] == "Alpha"
        assert names[-1] == "Gamma"

    @patch.object(get_user_model(), "update_preference")
    def test_newest_first_sort_returns_newest_id_first(self, mock_update_preference):
        mock_update_preference.return_value = "newest_first"
        response = self.client.get(reverse("lists") + "?sort=newest_first")
        assert self._names(response) == ["Gamma", "Beta", "Alpha"]

    @patch.object(get_user_model(), "update_preference")
    def test_unknown_sort_falls_back_to_default(self, mock_update_preference):
        mock_update_preference.return_value = "garbage_sort_value"
        response = self.client.get(reverse("lists") + "?sort=garbage_sort_value")
        names = self._names(response)
        assert set(names) == {"Alpha", "Beta", "Gamma"}


class ListDetailFilterTests(TestCase):
    """Tests for list detail filtering, sorting, search, and HTMX."""

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
    def test_list_detail_view_filter_by_media_type(
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

        response = self.client.get(
            reverse("list_detail", args=[self.custom_list.id])
            + f"?type={MediaTypes.MOVIE.value}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["items"]), 1)
        self.assertEqual(
            response.context["items"][0].media_type,
            MediaTypes.MOVIE.value,
        )

    @patch.object(get_user_model(), "update_preference")
    @patch.object(CustomList, "user_can_view")
    def test_list_detail_view_filter_by_status(
        self,
        mock_user_can_view,
        mock_update_preference,
    ):
        mock_update_preference.side_effect = ["date_added", Status.PLANNING.value]
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

        response = self.client.get(
            reverse("list_detail", args=[self.custom_list.id])
            + f"?status={Status.PLANNING.value}",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["current_status"],
            Status.PLANNING.value,
        )
        self.assertEqual(len(response.context["items"]), 1)
        self.assertEqual(
            response.context["items"][0].media_type,
            MediaTypes.ANIME.value,
        )

    @patch.object(get_user_model(), "update_preference")
    @patch.object(CustomList, "user_can_view")
    def test_list_detail_view_search(
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

        response = self.client.get(
            reverse("list_detail", args=[self.custom_list.id]) + "?q=Anime",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["items"]), 1)
        self.assertEqual(response.context["items"][0].title, "Test Anime")

    @patch.object(get_user_model(), "update_preference")
    @patch.object(CustomList, "user_can_view")
    def test_list_detail_view_sorting(
        self,
        mock_user_can_view,
        mock_update_preference,
    ):
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

        mock_update_preference.side_effect = ["title", None]
        response = self.client.get(
            reverse("list_detail", args=[self.custom_list.id]) + "?sort=title",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_sort"], "title")

        mock_update_preference.side_effect = ["media_type", None]
        response = self.client.get(
            reverse("list_detail", args=[self.custom_list.id]) + "?sort=media_type",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_sort"], "media_type")

    @patch.object(get_user_model(), "update_preference")
    @patch.object(CustomList, "user_can_view")
    def test_list_detail_view_htmx_request(
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

        response = self.client.get(
            reverse("list_detail", args=[self.custom_list.id]),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "lists/components/media_grid.html")
        self.assertNotIn("form", response.context)

    @patch.object(get_user_model(), "update_preference")
    def test_list_detail_handles_non_integer_page(self, mock_update_preference):
        mock_update_preference.return_value = "date_added"
        url = reverse("list_detail", args=[self.custom_list.id])
        response = self.client.get(url + "?page=garbage")
        self.assertEqual(response.status_code, 200)

    @patch.object(get_user_model(), "update_preference")
    def test_list_detail_handles_negative_page(self, mock_update_preference):
        mock_update_preference.return_value = "date_added"
        url = reverse("list_detail", args=[self.custom_list.id])
        response = self.client.get(url + "?page=-5")
        self.assertEqual(response.status_code, 200)

    @patch.object(get_user_model(), "update_preference")
    def test_list_detail_handles_huge_page(self, mock_update_preference):
        mock_update_preference.return_value = "date_added"
        url = reverse("list_detail", args=[self.custom_list.id])
        response = self.client.get(url + "?page=99999")
        self.assertEqual(response.status_code, 200)
