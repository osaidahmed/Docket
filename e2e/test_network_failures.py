from playwright.sync_api import Page, expect

from app.models import Status
from e2e.conftest import create_movie


def test_htmx_500_on_backlog_save(
    authenticated_page: Page,
    test_user,
    live_server,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.IN_PROGRESS.value,
        score=5,
    )
    authenticated_page.reload()

    authenticated_page.route(
        "**/backlog_save",
        lambda route: route.fulfill(status=500, body="Server Error"),
    )

    card = authenticated_page.locator("[id^='backlog-card-']").first
    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()
    card.locator("input[name='score']").fill("9")
    card.locator("button[type='submit']").click()

    authenticated_page.wait_for_timeout(1000)

    movie.refresh_from_db()
    assert movie.score == 5

    authenticated_page.unroute("**/backlog_save")


def test_htmx_network_error_on_toggle_pin(
    authenticated_page: Page,
    test_user,
    live_server,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.PLANNING.value,
    )
    authenticated_page.reload()

    authenticated_page.route(
        "**/toggle_pin",
        lambda route: route.abort("connectionrefused"),
    )

    pin_btn = authenticated_page.locator(
        "button[hx-post*='toggle_pin']",
    ).first
    if pin_btn.is_visible():
        pin_btn.click()
        authenticated_page.wait_for_timeout(1000)

        movie.refresh_from_db()
        assert movie.is_pinned is False

    authenticated_page.unroute("**/toggle_pin")


def test_htmx_500_on_quick_complete(
    authenticated_page: Page,
    test_user,
    live_server,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.IN_PROGRESS.value,
    )
    authenticated_page.reload()

    authenticated_page.route(
        "**/quick_complete",
        lambda route: route.fulfill(status=500, body="Error"),
    )

    done_btn = authenticated_page.locator(
        "button[hx-post*='quick_complete']",
    ).first
    if done_btn.is_visible():
        done_btn.click()
        authenticated_page.wait_for_timeout(1000)

        movie.refresh_from_db()
        assert movie.status == Status.IN_PROGRESS.value

    authenticated_page.unroute("**/quick_complete")


def test_page_reload_after_failed_htmx(
    authenticated_page: Page,
    test_user,
    live_server,
):
    create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.IN_PROGRESS.value,
    )
    authenticated_page.reload()

    authenticated_page.route(
        "**/backlog_save",
        lambda route: route.fulfill(status=500, body="Error"),
    )

    card = authenticated_page.locator("[id^='backlog-card-']").first
    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()
    card.locator("input[name='score']").fill("9")
    card.locator("button[type='submit']").click()
    authenticated_page.wait_for_timeout(500)

    authenticated_page.unroute("**/backlog_save")

    authenticated_page.reload()
    expect(authenticated_page.get_by_text("Fight Club")).to_be_visible()


def test_htmx_empty_response_on_score_update(
    authenticated_page: Page,
    test_user,
    live_server,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.COMPLETED.value,
        score=5,
    )
    authenticated_page.goto(
        f"{live_server.url}/details/tmdb/movie/550/Fight-Club",
    )

    authenticated_page.route(
        "**/update-score/**",
        lambda route: route.fulfill(status=200, body=""),
    )

    score_trigger = authenticated_page.locator(
        "[x-data*='showRatingPopup']",
    ).first
    if score_trigger.is_visible():
        score_trigger.click()
        score_buttons = authenticated_page.locator(
            "button[hx-post*='update-score']",
        )
        if score_buttons.first.is_visible(timeout=3000):
            score_buttons.nth(7).click()
            authenticated_page.wait_for_timeout(1000)

            movie.refresh_from_db()
            assert movie.score == 5

    authenticated_page.unroute("**/update-score/**")
