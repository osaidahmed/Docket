import re

from playwright.sync_api import Page, expect

from app.models import Movie, Status
from e2e.conftest import create_list, create_movie


def test_full_media_lifecycle(
    authenticated_page: Page,
    live_server,
    test_user,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.PLANNING.value,
    )

    authenticated_page.goto(f"{live_server.url}/")
    expect(authenticated_page.get_by_text("Fight Club")).to_be_visible()

    start_btn = authenticated_page.locator(
        "button[hx-post*='quick_status_transition']",
    ).first
    if start_btn.is_visible():
        with authenticated_page.expect_response(
            re.compile(r".*/quick_status_transition"),
        ):
            start_btn.click()
        movie.refresh_from_db()
        assert movie.status == Status.IN_PROGRESS.value

    done_btn = authenticated_page.locator(
        "button[hx-post*='quick_complete']",
    ).first
    if done_btn.is_visible():
        with authenticated_page.expect_response(
            re.compile(r".*/quick_complete"),
        ):
            done_btn.click()
        movie.refresh_from_db()
        assert movie.status == Status.COMPLETED.value

    authenticated_page.goto(f"{live_server.url}/medialist/movie")
    expect(authenticated_page.get_by_text("Fight Club")).to_be_visible()


def test_list_management_journey(
    authenticated_page: Page,
    live_server,
    test_user,
):
    lst = create_list(test_user, "Journey List", "For testing")

    authenticated_page.goto(f"{live_server.url}/lists")
    expect(authenticated_page.get_by_text("Journey List")).to_be_visible()

    authenticated_page.goto(f"{live_server.url}/list/{lst.id}")
    expect(
        authenticated_page.get_by_role("heading", name="Journey List"),
    ).to_be_visible()

    from lists.models import CustomList

    edit_btn = authenticated_page.get_by_role("button", name="Edit")
    if edit_btn.is_visible():
        edit_btn.click()
        delete_btn = authenticated_page.locator(
            "button[formaction*='delete']",
        ).first
        if delete_btn.is_visible() and delete_btn.is_enabled():
            delete_btn.click()
            authenticated_page.wait_for_load_state("networkidle")
            assert not CustomList.objects.filter(id=lst.id).exists()

            authenticated_page.goto(f"{live_server.url}/lists")
            expect(
                authenticated_page.get_by_text("Journey List"),
            ).not_to_be_visible()


def test_preferences_affect_home(
    authenticated_page: Page,
    live_server,
    test_user,
):
    authenticated_page.goto(f"{live_server.url}/settings/preferences")

    authenticated_page.evaluate(
        """() => {
            const cb = document.querySelector(
                'input[name="media_types_checkboxes"][value="boardgame"]'
            );
            if (cb) cb.checked = false;
        }""",
    )

    authenticated_page.get_by_role(
        "button",
        name="Save Preferences",
    ).click()
    authenticated_page.wait_for_load_state("networkidle")

    authenticated_page.goto(f"{live_server.url}/")

    test_user.refresh_from_db()
    assert test_user.boardgame_enabled is False


def test_disable_media_type_hides_in_explore(
    authenticated_page: Page,
    live_server,
    test_user,
):
    authenticated_page.goto(f"{live_server.url}/settings/preferences")

    authenticated_page.evaluate(
        """() => {
            const cb = document.querySelector(
                'input[name="media_types_checkboxes"][value="boardgame"]'
            );
            if (cb) cb.checked = false;
        }""",
    )

    authenticated_page.get_by_role(
        "button",
        name="Save Preferences",
    ).click()
    authenticated_page.wait_for_load_state("networkidle")

    authenticated_page.goto(f"{live_server.url}/explore")
    boardgame_link = authenticated_page.locator(
        "a[href*='/explore/boardgame']",
    )
    expect(boardgame_link).to_have_count(0)


def test_track_delete_retrack(
    authenticated_page: Page,
    live_server,
    test_user,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.COMPLETED.value,
    )
    movie_id = movie.id

    authenticated_page.goto(
        f"{live_server.url}/details/tmdb/movie/550/Fight-Club",
    )

    track_btn = authenticated_page.locator(
        "button[hx-get*='track_modal']",
    ).first
    if track_btn.is_visible():
        track_btn.click()
        modal_status = authenticated_page.locator(
            "select[name='status']",
        ).first
        expect(modal_status).to_be_visible(timeout=5000)

        delete_btn = authenticated_page.locator(
            "button[type='submit'][formaction*='media_delete']",
        ).first
        if delete_btn.is_visible() and delete_btn.is_enabled():
            delete_btn.click()
            authenticated_page.wait_for_load_state("networkidle")

            assert not Movie.objects.filter(id=movie_id).exists()


def test_edit_score_then_verify_on_detail(
    authenticated_page: Page,
    live_server,
    test_user,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.IN_PROGRESS.value,
        score=5,
    )
    authenticated_page.goto(f"{live_server.url}/")

    card = authenticated_page.locator("[id^='backlog-card-']").first
    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()
    card.locator("input[name='score']").fill("8")

    with authenticated_page.expect_response(re.compile(r".*/backlog_save")):
        card.locator("button[type='submit']").click()

    movie.refresh_from_db()
    assert movie.score == 8

    authenticated_page.goto(
        f"{live_server.url}/details/tmdb/movie/550/Fight-Club",
    )
    expect(authenticated_page.get_by_text("In progress")).to_be_visible()
