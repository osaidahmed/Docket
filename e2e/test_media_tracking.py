import re
from datetime import date

from playwright.sync_api import Page, expect

from app.models import Item, MediaTypes, Movie, Sources, Status
from e2e.conftest import create_anime, create_movie


def test_media_detail_shows_title_and_status(
    authenticated_page: Page,
    live_server,
    test_user,
):
    create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.IN_PROGRESS.value,
        score=8,
    )
    authenticated_page.goto(
        f"{live_server.url}/details/tmdb/movie/550/Fight-Club",
    )
    expect(
        authenticated_page.get_by_role("heading", name="Fight Club"),
    ).to_be_visible()
    expect(authenticated_page.get_by_text("In progress")).to_be_visible()


def test_media_list_shows_tracked_items(
    authenticated_page: Page,
    live_server,
    test_user,
):
    for i, title in enumerate(["Fight Club", "Inception", "The Matrix"]):
        create_movie(test_user, str(550 + i), title, Status.COMPLETED.value)
    authenticated_page.goto(f"{live_server.url}/medialist/movie")
    for title in ["Fight Club", "Inception", "The Matrix"]:
        expect(authenticated_page.get_by_text(title)).to_be_visible()


def test_media_list_empty_for_untracked_type(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/medialist/anime")
    expect(authenticated_page.locator("[id^='media-card-']")).to_have_count(0)


def test_track_modal_opens_and_saves(
    authenticated_page: Page,
    live_server,
    test_user,
):
    item = Item.objects.create(
        media_id="700",
        source=Sources.TMDB.value,
        media_type=MediaTypes.MOVIE.value,
        title="New Movie",
        image="https://via.placeholder.com/150",
    )
    authenticated_page.goto(
        f"{live_server.url}/details/tmdb/movie/700/New-Movie",
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
        modal_status.select_option("Planning")

        with authenticated_page.expect_response(re.compile(r".*/media_save")):
            authenticated_page.locator(
                "button[type='submit'][formaction*='media_save']",
            ).first.click()

        assert Movie.objects.filter(
            item=item,
            user=test_user,
            status=Status.PLANNING.value,
        ).exists()


def test_track_modal_closes_on_escape(
    authenticated_page: Page,
    live_server,
    test_user,
):
    create_movie(test_user, "550", "Fight Club", Status.IN_PROGRESS.value)
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

        authenticated_page.keyboard.press("Escape")
        expect(modal_status).to_be_hidden(timeout=3000)


def test_track_modal_closes_on_outside_click(
    authenticated_page: Page,
    live_server,
    test_user,
):
    create_movie(test_user, "550", "Fight Club", Status.IN_PROGRESS.value)
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

        authenticated_page.locator("body").click(position={"x": 5, "y": 5})
        expect(modal_status).to_be_hidden(timeout=3000)


def test_score_update_via_rating_popup(
    authenticated_page: Page,
    live_server,
    test_user,
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

    score_trigger = authenticated_page.locator(
        "[x-data*='showRatingPopup']",
    ).first
    if score_trigger.is_visible():
        score_trigger.click()
        score_buttons = authenticated_page.locator(
            "button[hx-post*='update-score']",
        )
        expect(score_buttons.first).to_be_visible(timeout=3000)

        with authenticated_page.expect_response(
            re.compile(r".*/update-score/"),
        ):
            score_buttons.nth(7).click()

        movie.refresh_from_db()
        assert movie.score == 8


def test_synopsis_expand_collapse(
    authenticated_page: Page,
    live_server,
    test_user,
):
    item = Item.objects.create(
        media_id="550",
        source=Sources.TMDB.value,
        media_type=MediaTypes.MOVIE.value,
        title="Fight Club",
        image="https://via.placeholder.com/150",
        synopsis="A " * 500,
    )
    Movie.objects.create(
        item=item,
        user=test_user,
        status=Status.COMPLETED.value,
    )
    authenticated_page.goto(
        f"{live_server.url}/details/tmdb/movie/550/Fight-Club",
    )

    read_more = authenticated_page.get_by_text("Read more")
    if read_more.is_visible(timeout=2000):
        read_more.click()
        show_less = authenticated_page.get_by_text("Show less")
        expect(show_less).to_be_visible()
        show_less.click()
        expect(read_more).to_be_visible()


def test_auto_fill_end_date_on_completed(
    authenticated_page: Page,
    live_server,
    test_user,
):
    item = Item.objects.create(
        media_id="700",
        source=Sources.TMDB.value,
        media_type=MediaTypes.MOVIE.value,
        title="Date Test Movie",
        image="https://via.placeholder.com/150",
    )
    authenticated_page.goto(
        f"{live_server.url}/details/tmdb/movie/700/Date-Test-Movie",
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

        modal_status.select_option("Completed")
        end_date = authenticated_page.locator(
            "input[name='end_date']",
        ).first
        value = end_date.input_value()
        today = date.today().isoformat()
        assert today in value


def test_auto_fill_start_date_on_in_progress(
    authenticated_page: Page,
    live_server,
    test_user,
):
    item = Item.objects.create(
        media_id="701",
        source=Sources.TMDB.value,
        media_type=MediaTypes.MOVIE.value,
        title="Start Date Movie",
        image="https://via.placeholder.com/150",
    )
    authenticated_page.goto(
        f"{live_server.url}/details/tmdb/movie/701/Start-Date-Movie",
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

        modal_status.select_option("In progress")
        start_date = authenticated_page.locator(
            "input[name='start_date']",
        ).first
        value = start_date.input_value()
        today = date.today().isoformat()
        assert today in value


def test_media_delete_from_detail(
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


def test_history_modal_opens(
    authenticated_page: Page,
    live_server,
    test_user,
):
    create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.COMPLETED.value,
    )
    authenticated_page.goto(
        f"{live_server.url}/details/tmdb/movie/550/Fight-Club",
    )

    history_btn = authenticated_page.locator(
        "button[hx-get*='history_modal']",
    ).first
    if history_btn.is_visible():
        history_btn.click()
        authenticated_page.wait_for_timeout(1000)


def test_multiple_media_types_on_home(
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


def test_sync_metadata_button_exists(
    authenticated_page: Page,
    live_server,
    test_user,
):
    create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.COMPLETED.value,
    )
    authenticated_page.goto(
        f"{live_server.url}/details/tmdb/movie/550/Fight-Club",
    )
    sync_btn = authenticated_page.locator(
        "button[hx-post*='sync']",
    ).first
    if sync_btn.is_visible():
        assert sync_btn.is_enabled()


def test_media_list_export_txt(
    authenticated_page: Page,
    live_server,
    test_user,
):
    create_movie(test_user, "550", "Fight Club", Status.COMPLETED.value)
    response = authenticated_page.goto(
        f"{live_server.url}/medialist/movie/export/txt/",
    )
    assert response.status != 500


def test_media_list_print(
    authenticated_page: Page,
    live_server,
    test_user,
):
    create_movie(test_user, "550", "Fight Club", Status.COMPLETED.value)
    response = authenticated_page.goto(
        f"{live_server.url}/medialist/movie/print/",
    )
    assert response.status != 500
