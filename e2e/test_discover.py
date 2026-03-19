from playwright.sync_api import Page, expect


def test_discover_tab_visible_for_anime(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/explore/anime")
    expect(
        authenticated_page.get_by_role("link", name="Discover"),
    ).to_be_visible()


def test_discover_tab_not_visible_for_book(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/explore/book")
    expect(
        authenticated_page.get_by_role("link", name="Discover"),
    ).not_to_be_visible()


def test_discover_view_loads_sections(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/explore/anime?view=discover")
    expect(
        authenticated_page.get_by_role("heading", name="Trending"),
    ).to_be_visible()


def test_browse_is_default_view(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/explore/movie")
    browse_tab = authenticated_page.get_by_role("link", name="Browse")
    expect(browse_tab).to_be_visible()


def test_discover_card_has_image(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/explore/anime?view=discover")
    card_img = authenticated_page.locator("img[loading='lazy']").first
    expect(card_img).to_be_visible()


def test_discover_schedule_visible_for_anime(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/explore/anime?view=discover")
    expect(
        authenticated_page.get_by_role("heading", name="Estimated Schedule"),
    ).to_be_visible()


def test_discover_unauthenticated_redirects(
    page: Page,
    live_server,
):
    page.goto(f"{live_server.url}/explore/anime?view=discover")
    expect(page).to_have_url(
        f"{live_server.url}/accounts/login/?next=/explore/anime%3Fview%3Ddiscover",
    )
