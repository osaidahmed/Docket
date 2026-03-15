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
