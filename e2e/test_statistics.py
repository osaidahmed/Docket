from playwright.sync_api import Page, expect

from app.models import Status
from e2e.conftest import create_anime, create_movie


def test_statistics_page_loads(authenticated_page: Page, live_server):
    authenticated_page.goto(f"{live_server.url}/statistics")
    expect(
        authenticated_page.get_by_role("heading", name="Statistics"),
    ).to_be_visible()


def test_statistics_with_data(
    authenticated_page: Page,
    live_server,
    test_user,
):
    create_movie(test_user, "550", "Fight Club", Status.COMPLETED.value, score=9)
    create_movie(test_user, "551", "Inception", Status.COMPLETED.value, score=8)
    create_anime(test_user, "1", "Cowboy Bebop", Status.COMPLETED.value, score=10)

    authenticated_page.goto(f"{live_server.url}/statistics")
    expect(
        authenticated_page.get_by_role("heading", name="Statistics"),
    ).to_be_visible()
