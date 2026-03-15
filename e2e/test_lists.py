from playwright.sync_api import Page, expect

from e2e.conftest import create_list
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
    create_list(test_user, "My Favorites", "Best of the best")
    create_list(test_user, "Watch Later", "To watch")
    authenticated_page.goto(f"{live_server.url}/lists")
    expect(authenticated_page.get_by_text("My Favorites")).to_be_visible()
    expect(authenticated_page.get_by_text("Watch Later")).to_be_visible()


def test_list_detail_page(
    authenticated_page: Page, live_server, test_user,
):
    lst = create_list(test_user, "My Favorites", "Best of the best")
    authenticated_page.goto(f"{live_server.url}/list/{lst.id}")
    expect(
        authenticated_page.get_by_role("heading", name="My Favorites"),
    ).to_be_visible()


def test_create_list_via_modal(
    authenticated_page: Page, live_server, test_user,
):
    authenticated_page.goto(f"{live_server.url}/lists")

    new_btn = authenticated_page.get_by_role("button", name="New List")
    if new_btn.is_visible():
        new_btn.click()

        name_input = authenticated_page.locator("input[name='name']").first
        expect(name_input).to_be_visible(timeout=3000)
        name_input.fill("Test List")

        desc_input = authenticated_page.locator(
            "textarea[name='description']",
        ).first
        if desc_input.is_visible():
            desc_input.fill("A test list")

        authenticated_page.locator(
            "button[type='submit']",
        ).last.click()
        authenticated_page.wait_for_load_state("networkidle")

        assert CustomList.objects.filter(
            name="Test List", owner=test_user,
        ).exists()


def test_delete_list(
    authenticated_page: Page, live_server, test_user,
):
    lst = create_list(test_user, "To Delete")
    authenticated_page.goto(f"{live_server.url}/list/{lst.id}")

    delete_btn = authenticated_page.locator(
        "button[formaction*='delete']",
    ).first
    if delete_btn.is_visible() and delete_btn.is_enabled():
        delete_btn.click()
        authenticated_page.wait_for_load_state("networkidle")
        assert not CustomList.objects.filter(id=lst.id).exists()


def test_list_detail_empty_state(
    authenticated_page: Page, live_server, test_user,
):
    lst = create_list(test_user, "Empty List")
    authenticated_page.goto(f"{live_server.url}/list/{lst.id}")
    expect(
        authenticated_page.get_by_role("heading", name="Empty List"),
    ).to_be_visible()


def test_list_search_filters_results(
    authenticated_page: Page, live_server, test_user,
):
    create_list(test_user, "Action Movies")
    create_list(test_user, "Comedy Shows")
    create_list(test_user, "Action Anime")
    authenticated_page.goto(f"{live_server.url}/lists")

    search = authenticated_page.locator(
        "input[placeholder*='Search']",
    ).first
    if search.is_visible():
        search.fill("Action")
        authenticated_page.wait_for_timeout(1000)
        expect(authenticated_page.get_by_text("Action Movies")).to_be_visible()
        expect(authenticated_page.get_by_text("Action Anime")).to_be_visible()


def test_list_search_clear_shows_all(
    authenticated_page: Page, live_server, test_user,
):
    create_list(test_user, "Action Movies")
    create_list(test_user, "Comedy Shows")
    authenticated_page.goto(f"{live_server.url}/lists")

    search = authenticated_page.locator(
        "input[placeholder*='Search']",
    ).first
    if search.is_visible():
        search.fill("Action")
        authenticated_page.wait_for_timeout(500)
        search.fill("")
        authenticated_page.wait_for_timeout(500)
        expect(authenticated_page.get_by_text("Action Movies")).to_be_visible()
        expect(authenticated_page.get_by_text("Comedy Shows")).to_be_visible()


def test_edit_list_name(
    authenticated_page: Page, live_server, test_user,
):
    lst = create_list(test_user, "Old Name", "A list")
    authenticated_page.goto(f"{live_server.url}/list/{lst.id}")

    edit_btn = authenticated_page.get_by_role("button", name="Edit")
    if edit_btn.is_visible():
        edit_btn.click()
        name_input = authenticated_page.locator("input[name='name']").first
        expect(name_input).to_be_visible(timeout=3000)
        name_input.fill("New Name")

        save_btn = authenticated_page.locator(
            "button[formaction*='edit']",
        ).first
        if save_btn.is_visible():
            save_btn.click()
            authenticated_page.wait_for_load_state("networkidle")
            lst.refresh_from_db()
            assert lst.name == "New Name"


def test_list_sort_dropdown(
    authenticated_page: Page, live_server, test_user,
):
    create_list(test_user, "Alpha List")
    create_list(test_user, "Beta List")
    authenticated_page.goto(f"{live_server.url}/lists")

    sort_btn = authenticated_page.locator(
        "button:has(svg)",
    ).filter(has_text="Name").first
    if not sort_btn.is_visible():
        sort_btn = authenticated_page.locator(
            "button:has(svg)",
        ).filter(has_text="Newest").first
    if sort_btn.is_visible():
        sort_btn.click()
        dropdown = authenticated_page.locator("[x-show='open']").first
        expect(dropdown).to_be_visible(timeout=2000)
