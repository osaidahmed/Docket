"""E2E tests for the /news page (replaces the old /explore landing) and legacy redirects."""

from playwright.sync_api import Page, expect


def test_news_page_loads(
    authenticated_page: Page,
    live_server,
):
    """The news aggregator at /news renders with the News heading."""
    authenticated_page.goto(f"{live_server.url}/news")
    expect(
        authenticated_page.get_by_role("heading", name="News", exact=True),
    ).to_be_visible()


def test_legacy_explore_redirects_to_medialist_browse_tab(
    authenticated_page: Page,
    live_server,
):
    """Old /explore/<type> URLs redirect to /medialist/<type>?tab=browse."""
    authenticated_page.goto(f"{live_server.url}/explore/movie")
    expect(authenticated_page).to_have_url(
        f"{live_server.url}/medialist/movie?tab=browse",
    )


def test_legacy_explore_view_discover_redirects(
    authenticated_page: Page,
    live_server,
):
    """Old ?view=discover redirects to ?tab=discover on medialist."""
    authenticated_page.goto(f"{live_server.url}/explore/anime?view=discover")
    expect(authenticated_page).to_have_url(
        f"{live_server.url}/medialist/anime?tab=discover",
    )


def test_explore_invalid_type_returns_404(
    authenticated_page: Page,
    live_server,
):
    """Unknown media type still returns 404 via the URL converter."""
    response = authenticated_page.goto(
        f"{live_server.url}/explore/invalidtype",
    )
    assert response.status == 404


def test_medialist_browse_tab_loads(
    authenticated_page: Page,
    live_server,
):
    """The medialist page with Browse tab active shows the tab strip."""
    authenticated_page.goto(f"{live_server.url}/medialist/movie?tab=browse")
    expect(authenticated_page.locator("main")).to_be_visible()
    expect(
        authenticated_page.get_by_role("button", name="Browse"),
    ).to_be_visible()


def test_mobile_viewport_hides_sidebar(
    page,
    live_server,
    test_user,
):
    """The News sidebar entry is off-screen on mobile (sidebar collapses)."""
    from e2e.conftest import login

    page.set_viewport_size({"width": 375, "height": 812})
    login(page, live_server)

    sidebar_link = page.get_by_role("link", name="News")
    expect(sidebar_link).not_to_be_in_viewport()
