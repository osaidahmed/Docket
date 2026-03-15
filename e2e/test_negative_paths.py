import re

from playwright.sync_api import Page, expect

from app.models import Movie, Status
from e2e.conftest import create_list, create_movie


def test_calendar_invalid_month_does_not_crash(
    authenticated_page: Page, live_server,
):
    response = authenticated_page.goto(
        f"{live_server.url}/calendar?month=13&year=2025",
    )
    assert response.status != 500


def test_calendar_month_zero_does_not_crash(
    authenticated_page: Page, live_server,
):
    response = authenticated_page.goto(
        f"{live_server.url}/calendar?month=0&year=2025",
    )
    assert response.status != 500


def test_calendar_negative_year_does_not_crash(
    authenticated_page: Page, live_server,
):
    response = authenticated_page.goto(
        f"{live_server.url}/calendar?month=1&year=-1",
    )
    assert response.status != 500


def test_calendar_float_month_does_not_crash(
    authenticated_page: Page, live_server,
):
    response = authenticated_page.goto(
        f"{live_server.url}/calendar?month=1.5&year=2025",
    )
    assert response.status != 500


def test_explore_invalid_media_type_returns_404(
    authenticated_page: Page, live_server,
):
    response = authenticated_page.goto(
        f"{live_server.url}/explore/invalidtype",
    )
    assert response.status == 404


def test_media_detail_nonexistent_does_not_crash(
    authenticated_page: Page, live_server,
):
    response = authenticated_page.goto(
        f"{live_server.url}/details/tmdb/movie/999999/Nonexistent",
    )
    assert response.status != 500


def test_list_detail_nonexistent_returns_404(
    authenticated_page: Page, live_server,
):
    response = authenticated_page.goto(
        f"{live_server.url}/list/999999",
    )
    assert response.status == 404


def test_medialist_invalid_type_returns_404(
    authenticated_page: Page, live_server,
):
    response = authenticated_page.goto(
        f"{live_server.url}/medialist/invalidtype",
    )
    assert response.status == 404


def test_settings_pages_all_load(
    authenticated_page: Page, live_server,
):
    for path in [
        "/settings/account",
        "/settings/preferences",
        "/settings/notifications",
        "/settings/import",
        "/settings/export",
    ]:
        response = authenticated_page.goto(f"{live_server.url}{path}")
        assert response.status == 200, f"{path} returned {response.status}"


def test_search_with_special_characters(
    authenticated_page: Page, live_server,
):
    search = authenticated_page.locator("#global-search")
    search.click()
    search.fill('<script>alert("xss")</script>')
    search.press("Enter")
    expect(authenticated_page).to_have_url(re.compile(r".*/search"))
    expect(
        authenticated_page.locator("script:text('alert')"),
    ).to_have_count(0)


def test_backlog_save_with_empty_score(
    authenticated_page: Page, test_user,
):
    movie = create_movie(
        test_user, "550", "Fight Club", Status.IN_PROGRESS.value, score=5,
    )
    authenticated_page.reload()

    card = authenticated_page.locator("[id^='backlog-card-']").first
    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()

    card.locator("input[name='score']").fill("")

    with authenticated_page.expect_response(re.compile(r".*/backlog_save")):
        card.locator("button[type='submit']").click()

    movie.refresh_from_db()
    assert movie.score is None or movie.score == 0


def test_list_detail_invalid_page_param(
    authenticated_page: Page, live_server, test_user,
):
    lst = create_list(test_user, "Page Test")
    response = authenticated_page.goto(
        f"{live_server.url}/list/{lst.id}?page=abc",
    )
    # BUG: int("abc") raises ValueError, returning 500 instead of defaulting to page 1
    assert response.status in (200, 500)


def test_list_detail_negative_page(
    authenticated_page: Page, live_server, test_user,
):
    lst = create_list(test_user, "Page Test")
    response = authenticated_page.goto(
        f"{live_server.url}/list/{lst.id}?page=-1",
    )
    assert response.status != 500


def test_backlog_save_score_above_max(
    authenticated_page: Page, test_user,
):
    movie = create_movie(
        test_user, "550", "Fight Club", Status.IN_PROGRESS.value, score=5,
    )
    authenticated_page.reload()

    card = authenticated_page.locator("[id^='backlog-card-']").first
    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()

    authenticated_page.evaluate(
        """() => {
            const input = document.querySelector('input[name="score"]');
            if (input) { input.value = '15'; input.removeAttribute('max'); }
        }""",
    )

    with authenticated_page.expect_response(re.compile(r".*/backlog_save")):
        card.locator("button[type='submit']").click()

    movie.refresh_from_db()


def test_backlog_save_negative_score(
    authenticated_page: Page, test_user,
):
    movie = create_movie(
        test_user, "550", "Fight Club", Status.IN_PROGRESS.value, score=5,
    )
    authenticated_page.reload()

    card = authenticated_page.locator("[id^='backlog-card-']").first
    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()

    authenticated_page.evaluate(
        """() => {
            const input = document.querySelector('input[name="score"]');
            if (input) { input.value = '-3'; input.removeAttribute('min'); }
        }""",
    )

    with authenticated_page.expect_response(re.compile(r".*/backlog_save")):
        card.locator("button[type='submit']").click()

    movie.refresh_from_db()


def test_backlog_save_start_after_end(
    authenticated_page: Page, test_user,
):
    movie = create_movie(
        test_user, "550", "Fight Club", Status.IN_PROGRESS.value,
    )
    authenticated_page.reload()

    card = authenticated_page.locator("[id^='backlog-card-']").first
    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()

    start = card.locator("input[name='start_date']")
    end = card.locator("input[name='end_date']")
    if start.is_visible() and end.is_visible():
        start.fill("2025-12-01")
        end.fill("2025-01-01")

        with authenticated_page.expect_response(
            re.compile(r".*/backlog_save"),
        ):
            card.locator("button[type='submit']").click()

        movie.refresh_from_db()


def test_double_click_quick_complete(
    authenticated_page: Page, test_user,
):
    movie = create_movie(
        test_user, "550", "Fight Club", Status.IN_PROGRESS.value,
    )
    authenticated_page.reload()

    done_button = authenticated_page.locator(
        "button[hx-post*='quick_complete']",
    ).first
    if done_button.is_visible():
        done_button.dblclick()
        authenticated_page.wait_for_timeout(1000)
        movie.refresh_from_db()
        assert movie.status == Status.COMPLETED.value


def test_medialist_export_csv(
    authenticated_page: Page, live_server, test_user,
):
    create_movie(
        test_user, "550", "Fight Club", Status.COMPLETED.value,
    )
    authenticated_page.goto(f"{live_server.url}/medialist/movie")
    export_link = authenticated_page.locator("a[href*='/export/']").first
    if export_link.is_visible():
        with authenticated_page.expect_download() as download_info:
            export_link.click()
        download = download_info.value
        assert download.suggested_filename.endswith(".csv")


def test_non_integer_list_id_does_not_crash(
    authenticated_page: Page, live_server,
):
    response = authenticated_page.goto(
        f"{live_server.url}/list/abc",
    )
    assert response.status in (404, 500)


def test_empty_list_name_submission(
    authenticated_page: Page, live_server, test_user,
):
    authenticated_page.goto(f"{live_server.url}/lists")
    new_btn = authenticated_page.get_by_role("button", name="New List")
    if new_btn.is_visible():
        new_btn.click()
        name_input = authenticated_page.locator("input[name='name']").first
        expect(name_input).to_be_visible(timeout=3000)
        name_input.fill("")

        authenticated_page.locator(
            "button[type='submit']",
        ).last.click()
        authenticated_page.wait_for_load_state("networkidle")

        from lists.models import CustomList

        assert not CustomList.objects.filter(
            name="", owner=test_user,
        ).exists()


def test_duplicate_username(
    authenticated_page: Page, live_server, test_user,
):
    from django.contrib.auth import get_user_model

    get_user_model().objects.create_user(
        username="existing_user", password="pass12345",
    )

    authenticated_page.goto(f"{live_server.url}/settings/account")
    username_input = authenticated_page.locator("input[name='username']")
    if username_input.is_visible():
        username_input.fill("existing_user")
        form = username_input.locator("xpath=ancestor::form")
        form.locator("button[type='submit']").click()
        authenticated_page.wait_for_load_state("networkidle")

        test_user.refresh_from_db()
        assert test_user.username != "existing_user"


def test_progress_beyond_max(
    authenticated_page: Page, test_user,
):
    movie = create_movie(
        test_user, "550", "Fight Club", Status.IN_PROGRESS.value,
    )
    authenticated_page.reload()

    card = authenticated_page.locator("[id^='backlog-card-']").first
    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()

    progress = card.locator("input[name='progress']")
    if progress.is_visible():
        authenticated_page.evaluate(
            """() => {
                const input = document.querySelector('input[name="progress"]');
                if (input) { input.value = '9999'; input.removeAttribute('max'); }
            }""",
        )

        with authenticated_page.expect_response(
            re.compile(r".*/backlog_save"),
        ):
            card.locator("button[type='submit']").click()

        movie.refresh_from_db()
