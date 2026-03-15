from playwright.sync_api import Page, expect

from lists.models import CustomList


def test_lists_empty_state(authenticated_page: Page, live_server):
    authenticated_page.goto(f"{live_server.url}/lists")
    expect(
        authenticated_page.get_by_role("heading", name="Lists", exact=True),
    ).to_be_visible()
    expect(
        authenticated_page.get_by_text("No Lists Created Yet"),
    ).to_be_visible()


def test_lists_page_shows_existing_lists(
    authenticated_page: Page, live_server, test_user,
):
    CustomList.objects.create(
        name="My Favorites", description="Best of the best", owner=test_user,
    )
    CustomList.objects.create(
        name="Watch Later", description="To watch", owner=test_user,
    )
    authenticated_page.goto(f"{live_server.url}/lists")
    expect(authenticated_page.get_by_text("My Favorites")).to_be_visible()
    expect(authenticated_page.get_by_text("Watch Later")).to_be_visible()


def test_list_detail_page(
    authenticated_page: Page, live_server, test_user,
):
    lst = CustomList.objects.create(
        name="My Favorites", description="Best of the best", owner=test_user,
    )
    authenticated_page.goto(f"{live_server.url}/list/{lst.id}")
    expect(
        authenticated_page.get_by_role("heading", name="My Favorites"),
    ).to_be_visible()
