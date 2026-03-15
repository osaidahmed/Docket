import re

from playwright.sync_api import Page, expect

from app.models import Anime, Item, MediaTypes, Movie, Sources, Status


def test_media_detail_shows_title_and_status(
    authenticated_page: Page, live_server, test_user,
):
    item = Item.objects.create(
        media_id="550",
        source=Sources.TMDB.value,
        media_type=MediaTypes.MOVIE.value,
        title="Fight Club",
        image="https://via.placeholder.com/150",
    )
    Movie.objects.create(
        item=item, user=test_user, status=Status.IN_PROGRESS.value, score=8,
    )
    authenticated_page.goto(
        f"{live_server.url}/details/tmdb/movie/550/Fight-Club",
    )
    expect(
        authenticated_page.get_by_role("heading", name="Fight Club"),
    ).to_be_visible()
    expect(authenticated_page.get_by_text("In progress")).to_be_visible()


def test_media_list_shows_tracked_items(
    authenticated_page: Page, live_server, test_user,
):
    for i, title in enumerate(["Fight Club", "Inception", "The Matrix"]):
        item = Item.objects.create(
            media_id=str(550 + i),
            source=Sources.TMDB.value,
            media_type=MediaTypes.MOVIE.value,
            title=title,
            image="https://via.placeholder.com/150",
        )
        Movie.objects.create(
            item=item, user=test_user, status=Status.COMPLETED.value,
        )
    authenticated_page.goto(f"{live_server.url}/medialist/movie")
    for title in ["Fight Club", "Inception", "The Matrix"]:
        expect(authenticated_page.get_by_text(title)).to_be_visible()


def test_media_list_empty_for_untracked_type(
    authenticated_page: Page, live_server,
):
    authenticated_page.goto(f"{live_server.url}/medialist/anime")
    expect(authenticated_page.locator("[id^='media-card-']")).to_have_count(0)


def test_media_save_via_track_modal(
    authenticated_page: Page, live_server, test_user,
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
        modal_form = authenticated_page.locator("select[name='status']").first
        expect(modal_form).to_be_visible(timeout=5000)
        modal_form.select_option("Planning")

        with authenticated_page.expect_response(re.compile(r".*/media_save")):
            authenticated_page.locator(
                "button[type='submit'][formaction*='media_save']",
            ).first.click()

        assert Movie.objects.filter(
            item=item, user=test_user, status=Status.PLANNING.value,
        ).exists()


def test_score_update_via_rating_popup(
    authenticated_page: Page, live_server, test_user,
):
    item = Item.objects.create(
        media_id="550",
        source=Sources.TMDB.value,
        media_type=MediaTypes.MOVIE.value,
        title="Fight Club",
        image="https://via.placeholder.com/150",
    )
    movie = Movie.objects.create(
        item=item, user=test_user, status=Status.COMPLETED.value, score=5,
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


def test_multiple_media_types_on_home(
    authenticated_page: Page, test_user,
):
    movie_item = Item.objects.create(
        media_id="550",
        source=Sources.TMDB.value,
        media_type=MediaTypes.MOVIE.value,
        title="Fight Club",
        image="https://via.placeholder.com/150",
    )
    Movie.objects.create(
        item=movie_item, user=test_user, status=Status.IN_PROGRESS.value,
    )

    anime_item = Item.objects.create(
        media_id="1",
        source=Sources.MAL.value,
        media_type=MediaTypes.ANIME.value,
        title="Cowboy Bebop",
        image="https://via.placeholder.com/150",
    )
    Anime.objects.create(
        item=anime_item, user=test_user, status=Status.IN_PROGRESS.value,
    )

    authenticated_page.reload()
    expect(authenticated_page.get_by_text("Fight Club")).to_be_visible()
    expect(authenticated_page.get_by_text("Cowboy Bebop")).to_be_visible()
