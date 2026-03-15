import re

from playwright.sync_api import Page, expect


def test_explore_has_media_type_links(
    authenticated_page: Page, live_server,
):
    authenticated_page.goto(f"{live_server.url}/explore")
    expect(
        authenticated_page.get_by_role("heading", name="Explore"),
    ).to_be_visible()
    expect(
        authenticated_page.locator("a[href*='/explore/']").first,
    ).to_be_visible()


def test_explore_type_page_loads(
    authenticated_page: Page, live_server,
):
    authenticated_page.goto(f"{live_server.url}/explore/movie")
    expect(authenticated_page).to_have_url(
        f"{live_server.url}/explore/movie",
    )


def test_explore_invalid_type_returns_404(
    authenticated_page: Page, live_server,
):
    response = authenticated_page.goto(
        f"{live_server.url}/explore/invalidtype",
    )
    assert response.status == 404


def test_explore_media_type_navigation(
    authenticated_page: Page, live_server,
):
    authenticated_page.goto(f"{live_server.url}/explore")
    type_link = authenticated_page.locator("a[href*='/explore/']").first
    type_link.click()
    expect(authenticated_page).to_have_url(
        re.compile(r".*/explore/\w+"),
    )


def test_explore_type_page_has_content(
    authenticated_page: Page, live_server,
):
    authenticated_page.goto(f"{live_server.url}/explore/movie")
    expect(authenticated_page.locator("main")).to_be_visible()


def test_mobile_viewport_hides_sidebar(
    page, live_server, test_user,
):
    from e2e.conftest import login

    page.set_viewport_size({"width": 375, "height": 812})
    login(page, live_server)

    sidebar_link = page.get_by_role("link", name="Explore")
    expect(sidebar_link).not_to_be_in_viewport()
