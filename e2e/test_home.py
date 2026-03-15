import re

from playwright.sync_api import Page, expect

from app.models import Item, MediaTypes, Movie, Sources, Status


def _create_movie(test_user, media_id, title, status, **kwargs):
    item = Item.objects.create(
        media_id=media_id,
        source=Sources.TMDB.value,
        media_type=MediaTypes.MOVIE.value,
        title=title,
        image="https://via.placeholder.com/150",
    )
    return Movie.objects.create(
        item=item, user=test_user, status=status, **kwargs,
    )


def test_home_empty_has_no_cards(authenticated_page: Page):
    expect(authenticated_page.locator("[id^='backlog-card-']")).to_have_count(0)


def test_sidebar_links_navigate_correctly(
    authenticated_page: Page, live_server,
):
    nav_targets = {
        "Explore": "/explore",
        "Statistics": "/statistics",
        "Calendar": "/calendar",
        "Lists": "/lists",
    }
    for link_name, expected_path in nav_targets.items():
        authenticated_page.get_by_role("link", name=link_name).click()
        expect(authenticated_page).to_have_url(
            re.compile(rf".*{re.escape(expected_path)}"),
        )
        authenticated_page.goto(f"{live_server.url}/")


def test_home_displays_in_progress_media(
    authenticated_page: Page, test_user,
):
    _create_movie(test_user, "550", "Fight Club", Status.IN_PROGRESS.value)
    authenticated_page.reload()
    expect(authenticated_page.get_by_text("Fight Club")).to_be_visible()


def test_home_groups_by_status(authenticated_page: Page, test_user):
    _create_movie(test_user, "550", "Fight Club", Status.IN_PROGRESS.value)
    _create_movie(test_user, "551", "Inception", Status.PLANNING.value)
    authenticated_page.reload()
    expect(authenticated_page.get_by_text("Fight Club")).to_be_visible()
    expect(authenticated_page.get_by_text("Inception")).to_be_visible()


def test_backlog_card_edit_form_expands(
    authenticated_page: Page, test_user,
):
    _create_movie(test_user, "550", "Fight Club", Status.IN_PROGRESS.value)
    authenticated_page.reload()

    card = authenticated_page.locator("[id^='backlog-card-']").first
    expect(card.locator("select[name='status']")).to_be_hidden()

    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()

    expect(card.locator("select[name='status']")).to_be_visible()


def test_backlog_save_updates_score_via_htmx(
    authenticated_page: Page, test_user,
):
    movie = _create_movie(
        test_user, "550", "Fight Club", Status.IN_PROGRESS.value, score=5,
    )
    authenticated_page.reload()

    card = authenticated_page.locator("[id^='backlog-card-']").first
    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()

    card.locator("input[name='score']").fill("9")

    with authenticated_page.expect_response(re.compile(r".*/backlog_save")):
        card.locator("button[type='submit']").click()

    movie.refresh_from_db()
    assert movie.score == 9


def test_quick_complete_changes_status(
    authenticated_page: Page, test_user,
):
    movie = _create_movie(
        test_user, "550", "Fight Club", Status.IN_PROGRESS.value,
    )
    authenticated_page.reload()

    done_button = authenticated_page.locator(
        "button[hx-post*='quick_complete']",
    ).first

    if done_button.is_visible():
        with authenticated_page.expect_response(
            re.compile(r".*/quick_complete"),
        ):
            done_button.click()

        movie.refresh_from_db()
        assert movie.status == Status.COMPLETED.value


def test_home_excludes_completed_media(
    authenticated_page: Page, test_user,
):
    _create_movie(test_user, "550", "Fight Club", Status.COMPLETED.value)
    authenticated_page.reload()
    expect(authenticated_page.get_by_text("Fight Club")).not_to_be_visible()
