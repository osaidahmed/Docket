from playwright.sync_api import Page, expect


def test_discover_anime_page_loads(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/discover/anime")
    expect(authenticated_page.get_by_role("heading", name="Discover")).to_be_visible()


def test_discover_movie_page_loads(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/discover/movie")
    expect(authenticated_page.get_by_role("heading", name="Discover")).to_be_visible()


def test_discover_has_section_headings(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/discover/anime")
    expect(
        authenticated_page.get_by_role("heading", name="Trending"),
    ).to_be_visible()


def test_discover_invalid_type_returns_404(
    authenticated_page: Page,
    live_server,
):
    response = authenticated_page.goto(
        f"{live_server.url}/discover/invalidtype",
    )
    assert response.status == 404


def test_discover_unauthenticated_redirects(
    page: Page,
    live_server,
):
    page.goto(f"{live_server.url}/discover/anime")
    expect(page).to_have_url(
        f"{live_server.url}/accounts/login/?next=/discover/anime",
    )


def test_discover_card_has_image(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/discover/anime")
    card_img = authenticated_page.locator("img[data-src]").first
    expect(card_img).to_be_visible()


def test_discover_card_links_to_detail(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/discover/anime")
    detail_link = authenticated_page.locator("a[href*='/details/']").first
    expect(detail_link).to_have_attribute("href", value=lambda v: "/details/" in v)


def test_discover_schedule_visible_for_anime(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/discover/anime")
    expect(
        authenticated_page.get_by_role("heading", name="Estimated Schedule"),
    ).to_be_visible()


def test_discover_spotlight_visible_for_tv(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/discover/tv")
    spotlight = authenticated_page.locator("[class*='aspect-']").first
    expect(spotlight).to_be_visible()
