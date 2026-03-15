import re

from playwright.sync_api import Page, expect

from app.models import Item, MediaTypes, Movie, Sources, Status


def test_media_list_shows_tracked_items(
    authenticated_page: Page, live_server, test_user,
):
    item = Item.objects.create(
        media_id="550",
        source=Sources.TMDB.value,
        media_type=MediaTypes.MOVIE.value,
        title="Fight Club",
        image="https://via.placeholder.com/150",
    )
    Movie.objects.create(
        item=item, user=test_user, status=Status.COMPLETED.value,
    )
    authenticated_page.goto(f"{live_server.url}/medialist/movie")
    expect(authenticated_page.get_by_text("Fight Club")).to_be_visible()


def test_search_bar_accepts_input(authenticated_page: Page):
    search = authenticated_page.locator("#global-search")
    expect(search).to_be_visible()
    search.fill("test")
    expect(search).to_have_value("test")


def test_search_submits_to_results_page(
    authenticated_page: Page, live_server,
):
    search = authenticated_page.locator("#global-search")
    search.click()
    search.fill("fight club")
    search.press("Enter")
    expect(authenticated_page).to_have_url(
        re.compile(r".*/search\?.*q=fight\+club"),
    )


def test_search_empty_query_loads_page(
    authenticated_page: Page, live_server,
):
    authenticated_page.goto(f"{live_server.url}/search")
    expect(authenticated_page).to_have_url(re.compile(r".*/search"))


def test_search_keyboard_shortcut(authenticated_page: Page):
    authenticated_page.keyboard.press("/")
    expect(authenticated_page.locator("#global-search")).to_be_focused()


def test_search_shortcut_ignored_in_textarea(
    authenticated_page: Page, live_server,
):
    authenticated_page.goto(f"{live_server.url}/create")
    textarea = authenticated_page.locator("textarea").first
    if textarea.is_visible():
        textarea.click()
        textarea.press("/")
        expect(authenticated_page.locator("#global-search")).not_to_be_focused()


def test_search_with_query_param(
    authenticated_page: Page, live_server,
):
    authenticated_page.goto(f"{live_server.url}/search?q=inception")
    expect(authenticated_page).to_have_url(re.compile(r".*/search"))


def test_create_entry_page_loads(
    authenticated_page: Page, live_server,
):
    authenticated_page.goto(f"{live_server.url}/create")
    expect(authenticated_page.locator("input[name='title']")).to_be_visible()
    expect(
        authenticated_page.locator("select[name='status']"),
    ).to_be_visible()
