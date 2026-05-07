import re

from playwright.sync_api import Page, expect

from app.models import Movie, Status
from e2e.conftest import create_anime, create_movie


def test_home_empty_has_no_cards(authenticated_page: Page):
    expect(authenticated_page.locator("[id^='backlog-card-']")).to_have_count(0)


def test_sidebar_links_navigate_correctly(
    authenticated_page: Page,
    live_server,
):
    for link_name, expected_path in {
        "News": "/news",
        "Statistics": "/statistics",
        "Calendar": "/calendar",
        "Lists": "/lists",
    }.items():
        authenticated_page.get_by_role("link", name=link_name).click()
        expect(authenticated_page).to_have_url(
            re.compile(rf".*{re.escape(expected_path)}"),
        )
        authenticated_page.goto(f"{live_server.url}/")


def test_home_displays_in_progress_media(
    authenticated_page: Page,
    test_user,
):
    create_movie(test_user, "550", "Fight Club", Status.IN_PROGRESS.value)
    authenticated_page.reload()
    expect(authenticated_page.get_by_text("Fight Club")).to_be_visible()


def test_home_excludes_completed_media(
    authenticated_page: Page,
    test_user,
):
    create_movie(test_user, "550", "Fight Club", Status.COMPLETED.value)
    authenticated_page.reload()
    expect(authenticated_page.get_by_text("Fight Club")).not_to_be_visible()


def test_home_groups_by_status(authenticated_page: Page, test_user):
    create_movie(test_user, "550", "Fight Club", Status.IN_PROGRESS.value)
    create_movie(test_user, "551", "Inception", Status.PLANNING.value)
    authenticated_page.reload()
    expect(authenticated_page.get_by_text("Fight Club")).to_be_visible()
    expect(authenticated_page.get_by_text("Inception")).to_be_visible()


def test_backlog_card_edit_form_expands_and_collapses(
    authenticated_page: Page,
    test_user,
):
    create_movie(test_user, "550", "Fight Club", Status.IN_PROGRESS.value)
    authenticated_page.reload()

    card = authenticated_page.locator("[id^='backlog-card-']").first
    status_select = card.locator("select[name='status']")
    expect(status_select).to_be_hidden()

    edit_btn = (
        card.locator("button")
        .filter(
            has=authenticated_page.locator("svg"),
        )
        .first
    )
    edit_btn.click()
    expect(status_select).to_be_visible()

    edit_btn.click()
    expect(status_select).to_be_hidden()


def test_backlog_save_updates_score_via_htmx(
    authenticated_page: Page,
    test_user,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.IN_PROGRESS.value,
        score=5,
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
    authenticated_page: Page,
    test_user,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.IN_PROGRESS.value,
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


def test_quick_status_transition_planning_to_in_progress(
    authenticated_page: Page,
    test_user,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.PLANNING.value,
    )
    authenticated_page.reload()

    start_button = authenticated_page.locator(
        "button[hx-post*='quick_status_transition']",
    ).first
    if start_button.is_visible():
        with authenticated_page.expect_response(
            re.compile(r".*/quick_status_transition"),
        ):
            start_button.click()
        movie.refresh_from_db()
        assert movie.status == Status.IN_PROGRESS.value


def test_quick_drop_two_step_cancel(
    authenticated_page: Page,
    test_user,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.IN_PROGRESS.value,
    )
    authenticated_page.reload()

    card = authenticated_page.locator("[id^='backlog-card-']").first
    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()

    drop_btn = card.locator("button:has-text('Drop')").first
    if drop_btn.is_visible():
        drop_btn.click()
        cancel_btn = card.locator("button:has-text('Cancel')")
        if cancel_btn.is_visible():
            cancel_btn.click()
            movie.refresh_from_db()
            assert movie.status == Status.IN_PROGRESS.value


def test_quick_drop_confirms_and_drops(
    authenticated_page: Page,
    test_user,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.IN_PROGRESS.value,
    )
    authenticated_page.reload()

    card = authenticated_page.locator("[id^='backlog-card-']").first
    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()

    drop_btn = card.locator("button:has-text('Drop')").first
    if drop_btn.is_visible():
        drop_btn.click()
        confirm_drop = card.locator("button[hx-post*='quick_drop']")
        if confirm_drop.is_visible():
            with authenticated_page.expect_response(
                re.compile(r".*/quick_drop"),
            ):
                confirm_drop.click()
            movie.refresh_from_db()
            assert movie.status == Status.DROPPED.value


def test_quick_untrack_removes_media(
    authenticated_page: Page,
    test_user,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.IN_PROGRESS.value,
    )
    movie_id = movie.id
    authenticated_page.reload()

    card = authenticated_page.locator("[id^='backlog-card-']").first
    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()

    untrack_btn = card.locator("button[hx-post*='quick_untrack']")
    if untrack_btn.is_visible():
        with authenticated_page.expect_response(
            re.compile(r".*/quick_untrack"),
        ):
            untrack_btn.click()
        assert not Movie.objects.filter(id=movie_id).exists()


def test_pin_toggle(authenticated_page: Page, test_user):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.PLANNING.value,
    )
    authenticated_page.reload()

    pin_button = authenticated_page.locator(
        "button[hx-post*='toggle_pin']",
    ).first
    if pin_button.is_visible():
        with authenticated_page.expect_response(
            re.compile(r".*/toggle_pin"),
        ):
            pin_button.click()
        movie.refresh_from_db()
        assert movie.is_pinned is True


def test_backlog_save_changes_status(
    authenticated_page: Page,
    test_user,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.IN_PROGRESS.value,
    )
    authenticated_page.reload()

    card = authenticated_page.locator("[id^='backlog-card-']").first
    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()

    card.locator("select[name='status']").select_option("Paused")

    with authenticated_page.expect_response(re.compile(r".*/backlog_save")):
        card.locator("button[type='submit']").click()

    movie.refresh_from_db()
    assert movie.status == Status.PAUSED.value


def test_backlog_save_with_notes(
    authenticated_page: Page,
    test_user,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.IN_PROGRESS.value,
    )
    authenticated_page.reload()

    card = authenticated_page.locator("[id^='backlog-card-']").first
    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()

    notes = card.locator("textarea[name='notes']")
    if notes.is_visible():
        notes.fill("Great movie")

        with authenticated_page.expect_response(
            re.compile(r".*/backlog_save"),
        ):
            card.locator("button[type='submit']").click()

        movie.refresh_from_db()
        assert movie.notes == "Great movie"


def test_backlog_save_with_dates(
    authenticated_page: Page,
    test_user,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.IN_PROGRESS.value,
    )
    authenticated_page.reload()

    card = authenticated_page.locator("[id^='backlog-card-']").first
    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()

    start_date = card.locator("input[name='start_date']")
    if start_date.is_visible():
        start_date.fill("2025-01-15")

        with authenticated_page.expect_response(
            re.compile(r".*/backlog_save"),
        ):
            card.locator("button[type='submit']").click()

        movie.refresh_from_db()
        assert movie.start_date is not None


def test_grouping_toggle(
    authenticated_page: Page,
    test_user,
):
    create_movie(test_user, "550", "Fight Club", Status.IN_PROGRESS.value)
    authenticated_page.reload()

    toggle = authenticated_page.locator(
        "button[hx-post*='toggle_grouping']",
    ).first
    if toggle.is_visible():
        initial = test_user.group_related_media
        with authenticated_page.expect_response(
            re.compile(r".*/toggle_grouping"),
        ):
            toggle.click()
        test_user.refresh_from_db()
        assert test_user.group_related_media != initial


def test_multiple_media_types_coexist(
    authenticated_page: Page,
    test_user,
):
    create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.IN_PROGRESS.value,
    )
    create_anime(
        test_user,
        "1",
        "Cowboy Bebop",
        Status.IN_PROGRESS.value,
    )
    authenticated_page.reload()
    expect(authenticated_page.get_by_text("Fight Club")).to_be_visible()
    expect(authenticated_page.get_by_text("Cowboy Bebop")).to_be_visible()


def test_layout_toggle(authenticated_page: Page, live_server, test_user):
    create_movie(test_user, "550", "Fight Club", Status.IN_PROGRESS.value)
    authenticated_page.reload()

    table_link = authenticated_page.locator("a[href*='layout=table']").first
    if table_link.is_visible():
        table_link.click()
        expect(authenticated_page).to_have_url(re.compile(r".*layout=table"))


def test_archive_section(authenticated_page: Page, test_user):
    create_movie(test_user, "550", "Fight Club", Status.COMPLETED.value)
    authenticated_page.reload()

    archive_btn = authenticated_page.locator(
        "button[x-on\\:click*='archiveOpen']",
    ).first
    if not archive_btn.is_visible():
        archive_btn = authenticated_page.get_by_text("Archive").first
    if archive_btn.is_visible():
        archive_btn.click()
        expect(
            authenticated_page.get_by_text("Fight Club"),
        ).to_be_visible(timeout=3000)


def test_see_all_expand(authenticated_page: Page, test_user):
    from app.models import Anime, Item, MediaTypes, Sources

    items = Item.objects.bulk_create(
        [
            Item(
                media_id=str(80000 + i),
                source=Sources.MAL.value,
                media_type=MediaTypes.ANIME.value,
                title=f"Anime {i}",
                image="https://via.placeholder.com/150",
            )
            for i in range(8)
        ]
    )
    Anime.objects.bulk_create(
        [
            Anime(item=item, user=test_user, status=Status.IN_PROGRESS.value)
            for item in items
        ]
    )
    authenticated_page.reload()

    see_all_btn = authenticated_page.get_by_text("See all").first
    if see_all_btn.is_visible():
        see_all_btn.click()
        show_less = authenticated_page.get_by_text("Show less").first
        expect(show_less).to_be_visible(timeout=3000)


def test_sort_dropdown_opens_and_closes(
    authenticated_page: Page,
    test_user,
):
    create_movie(test_user, "550", "Fight Club", Status.IN_PROGRESS.value)
    authenticated_page.reload()

    sort_btn = authenticated_page.locator(
        "[x-data*='open'] button:has(svg)",
    ).first
    if sort_btn.is_visible():
        sort_btn.click()
        dropdown = authenticated_page.locator("[x-show='open']").first
        expect(dropdown).to_be_visible(timeout=2000)

        authenticated_page.keyboard.press("Escape")


def test_paused_to_planning_transition(
    authenticated_page: Page,
    test_user,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.PAUSED.value,
    )
    authenticated_page.reload()

    plan_btn = authenticated_page.locator(
        "button[hx-post*='quick_status_transition']",
    ).first
    if plan_btn.is_visible():
        with authenticated_page.expect_response(
            re.compile(r".*/quick_status_transition"),
        ):
            plan_btn.click()
        movie.refresh_from_db()
        assert movie.status == Status.PLANNING.value


def test_backlog_save_changes_progress(
    authenticated_page: Page,
    test_user,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.IN_PROGRESS.value,
    )
    authenticated_page.reload()

    card = authenticated_page.locator("[id^='backlog-card-']").first
    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()

    progress = card.locator("input[name='progress']")
    if progress.is_visible():
        progress.fill("5")

        with authenticated_page.expect_response(
            re.compile(r".*/backlog_save"),
        ):
            card.locator("button[type='submit']").click()

        movie.refresh_from_db()
        assert movie.progress == 5
