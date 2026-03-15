import re

from playwright.sync_api import Page, expect

from app.models import Item, MediaTypes, Movie, Sources, Status
from e2e.conftest import create_movie


def _post_score_via_fetch(page, live_server, movie_id, score_value):
    return page.evaluate(
        f"""async () => {{
            const csrf = document.cookie.match(/csrftoken=([^;]+)/)?.[1] || '';
            const resp = await fetch('{live_server.url}/update-score/movie/{movie_id}/', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': csrf
                }},
                body: 'score={score_value}'
            }});
            return resp.status;
        }}""",
    )


def test_score_infinity(authenticated_page: Page, live_server, test_user):
    movie = create_movie(
        test_user, "550", "Fight Club", Status.COMPLETED.value, score=5,
    )
    authenticated_page.goto(
        f"{live_server.url}/details/tmdb/movie/550/Fight-Club",
    )
    _post_score_via_fetch(
        authenticated_page, live_server, movie.id, "Infinity",
    )
    authenticated_page.wait_for_timeout(500)
    movie.refresh_from_db()
    assert movie.score != float("inf")


def test_score_nan(authenticated_page: Page, live_server, test_user):
    movie = create_movie(
        test_user, "550", "Fight Club", Status.COMPLETED.value, score=5,
    )
    authenticated_page.goto(
        f"{live_server.url}/details/tmdb/movie/550/Fight-Club",
    )
    _post_score_via_fetch(
        authenticated_page, live_server, movie.id, "NaN",
    )
    authenticated_page.wait_for_timeout(500)
    movie.refresh_from_db()


def test_score_float(authenticated_page: Page, live_server, test_user):
    movie = create_movie(
        test_user, "550", "Fight Club", Status.COMPLETED.value, score=5,
    )
    authenticated_page.goto(
        f"{live_server.url}/details/tmdb/movie/550/Fight-Club",
    )
    _post_score_via_fetch(
        authenticated_page, live_server, movie.id, "7.5",
    )
    authenticated_page.wait_for_timeout(500)
    movie.refresh_from_db()


def test_unicode_title_in_create_entry(
    authenticated_page: Page, live_server, test_user,
):
    authenticated_page.goto(f"{live_server.url}/create")

    movie_btn = authenticated_page.locator(
        "button[type='button']",
    ).filter(has_text="Movie")
    if movie_btn.is_visible():
        movie_btn.click()

    authenticated_page.locator("input[name='title']").fill(
        "テスト映画 🎬 فيلم",
    )
    authenticated_page.locator("select[name='status']").select_option(
        "Completed",
    )
    authenticated_page.get_by_role("button", name="Create Entry").click()
    authenticated_page.wait_for_load_state("networkidle")

    assert Item.objects.filter(title="テスト映画 🎬 فيلم").exists()


def test_very_long_title(
    authenticated_page: Page, live_server, test_user,
):
    authenticated_page.goto(f"{live_server.url}/create")

    movie_btn = authenticated_page.locator(
        "button[type='button']",
    ).filter(has_text="Movie")
    if movie_btn.is_visible():
        movie_btn.click()

    long_title = "A" * 5000
    authenticated_page.locator("input[name='title']").fill(long_title)
    authenticated_page.locator("select[name='status']").select_option(
        "Completed",
    )
    authenticated_page.get_by_role("button", name="Create Entry").click()
    authenticated_page.wait_for_load_state("networkidle")


def test_html_injection_in_notes(
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

    notes = card.locator("textarea[name='notes']")
    if notes.is_visible():
        notes.fill('<img src=x onerror=alert(1)>')

        with authenticated_page.expect_response(
            re.compile(r".*/backlog_save"),
        ):
            card.locator("button[type='submit']").click()

        movie.refresh_from_db()
        assert "<img" in movie.notes

        authenticated_page.reload()
        expect(
            authenticated_page.locator("img[onerror]"),
        ).to_have_count(0)


def test_html_injection_in_list_name(
    authenticated_page: Page, live_server, test_user,
):
    authenticated_page.goto(f"{live_server.url}/lists")

    new_btn = authenticated_page.get_by_role("button", name="New List")
    if new_btn.is_visible():
        new_btn.click()
        name_input = authenticated_page.locator("input[name='name']").first
        expect(name_input).to_be_visible(timeout=3000)
        name_input.fill('<script>alert("xss")</script>')

        authenticated_page.locator(
            "button[type='submit']",
        ).last.click()
        authenticated_page.wait_for_load_state("networkidle")

        authenticated_page.goto(f"{live_server.url}/lists")
        expect(
            authenticated_page.locator("script:text('alert')"),
        ).to_have_count(0)


def test_status_value_tampered(
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

    authenticated_page.evaluate(
        """() => {
            const select = document.querySelector('select[name="status"]');
            if (select) {
                const opt = document.createElement('option');
                opt.value = 'InvalidStatus';
                opt.text = 'Invalid';
                select.add(opt);
                select.value = 'InvalidStatus';
            }
        }""",
    )

    with authenticated_page.expect_response(re.compile(r".*/backlog_save")):
        card.locator("button[type='submit']").click()

    movie.refresh_from_db()
    assert movie.status in (
        Status.IN_PROGRESS.value,
        Status.COMPLETED.value,
        Status.PLANNING.value,
        Status.PAUSED.value,
        Status.DROPPED.value,
    )


def test_media_type_tampered(
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

    authenticated_page.evaluate(
        """() => {
            const input = document.querySelector('input[name="media_type"]');
            if (input) input.value = 'invalidtype';
        }""",
    )

    with authenticated_page.expect_response(
        re.compile(r".*/backlog_save"),
    ) as response_info:
        card.locator("button[type='submit']").click()
    response = response_info.value


def test_instance_id_tampered_to_other_user(
    authenticated_page: Page, live_server, test_user,
):
    from django.contrib.auth import get_user_model

    user_b = get_user_model().objects.create_user(
        username="victim", password="pass12345",
    )
    victim_movie = create_movie(
        user_b, "551", "Inception", Status.IN_PROGRESS.value, score=5,
    )

    movie = create_movie(
        test_user, "550", "Fight Club", Status.IN_PROGRESS.value,
    )
    authenticated_page.reload()

    card = authenticated_page.locator("[id^='backlog-card-']").first
    card.locator("button").filter(
        has=authenticated_page.locator("svg"),
    ).first.click()

    authenticated_page.evaluate(
        f"""() => {{
            const input = document.querySelector('input[name="instance_id"]');
            if (input) input.value = '{victim_movie.id}';
        }}""",
    )

    card.locator("input[name='score']").fill("10")

    with authenticated_page.expect_response(re.compile(r".*/backlog_save")):
        card.locator("button[type='submit']").click()

    victim_movie.refresh_from_db()
    assert victim_movie.score == 5
