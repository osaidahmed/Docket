"""E2E tests for the Discover tab on the medialist page."""

from playwright.sync_api import Page, expect


def test_discover_tab_visible_for_anime(
    authenticated_page: Page,
    live_server,
):
    """Discover tab button is visible on /medialist/anime."""
    authenticated_page.goto(f"{live_server.url}/medialist/anime")
    expect(
        authenticated_page.get_by_role("button", name="Discover"),
    ).to_be_visible()


def test_discover_tab_not_visible_for_book(
    authenticated_page: Page,
    live_server,
):
    """Book medialist has no Discover tab (no DISCOVER_SECTIONS for book)."""
    authenticated_page.goto(f"{live_server.url}/medialist/book")
    expect(
        authenticated_page.get_by_role("button", name="Discover"),
    ).not_to_be_visible()


def test_discover_view_loads_sections(
    authenticated_page: Page,
    live_server,
):
    """Visiting /medialist/anime?tab=discover loads the trending section."""
    authenticated_page.goto(f"{live_server.url}/medialist/anime?tab=discover")
    expect(
        authenticated_page.get_by_role("heading", name="Trending"),
    ).to_be_visible()


def test_browse_tab_visible_on_movie(
    authenticated_page: Page,
    live_server,
):
    """Movie medialist has a Browse tab button."""
    authenticated_page.goto(f"{live_server.url}/medialist/movie")
    browse_button = authenticated_page.get_by_role("button", name="Browse")
    expect(browse_button).to_be_visible()


def test_discover_card_has_image(
    authenticated_page: Page,
    live_server,
):
    """Discover cards render with lazy-loaded poster images inside the visible tab."""
    authenticated_page.goto(f"{live_server.url}/medialist/anime?tab=discover")
    # Wait for the discover content to swap in
    expect(
        authenticated_page.get_by_role("heading", name="Trending"),
    ).to_be_visible()
    # Scope to the discover tab's swap target (the only one with hx-get for ?tab=discover)
    card_img = authenticated_page.locator(
        "[hx-get*='tab=discover'] img[loading='lazy']"
    ).first
    expect(card_img).to_be_visible()


def test_discover_schedule_visible_for_anime(
    authenticated_page: Page,
    live_server,
):
    """The anime Discover view includes the airing schedule section."""
    authenticated_page.goto(f"{live_server.url}/medialist/anime?tab=discover")
    expect(
        authenticated_page.get_by_role("heading", name="Estimated Schedule"),
    ).to_be_visible()


def test_discover_unauthenticated_redirects(
    page: Page,
    live_server,
):
    """Unauthenticated discover request redirects through login."""
    page.goto(f"{live_server.url}/medialist/anime?tab=discover")
    expect(page).to_have_url(
        f"{live_server.url}/accounts/login/?next=/medialist/anime%3Ftab%3Ddiscover",
    )
