from django.contrib.auth import get_user_model
from playwright.sync_api import expect

from app.models import Status
from e2e.conftest import create_list, create_movie, login


def _create_user_b():
    User = get_user_model()
    return User.objects.create_user(username="user_b", password="pass12345")


def test_cannot_access_other_users_list(
    live_server,
    test_user,
    browser,
):
    lst = create_list(test_user, "Private List")
    _create_user_b()

    ctx = browser.new_context()
    page = ctx.new_page()
    login(page, live_server, username="user_b", password="pass12345")

    response = page.goto(f"{live_server.url}/list/{lst.id}")
    assert response.status == 404

    ctx.close()


def test_cannot_delete_other_users_list(
    live_server,
    test_user,
    browser,
):
    lst = create_list(test_user, "Protected List")
    _create_user_b()

    ctx = browser.new_context()
    page = ctx.new_page()
    login(page, live_server, username="user_b", password="pass12345")

    csrf = page.evaluate(
        "document.cookie.match(/csrftoken=([^;]+)/)?.[1] || ''",
    )
    page.evaluate(
        f"""
        fetch('{live_server.url}/lists/delete/', {{
            method: 'POST',
            headers: {{
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': '{csrf}'
            }},
            body: 'list_id={lst.id}'
        }})
        """,
    )
    page.wait_for_timeout(1000)

    from lists.models import CustomList

    assert CustomList.objects.filter(id=lst.id).exists()

    ctx.close()


def test_cannot_edit_other_users_media(
    live_server,
    test_user,
    browser,
):
    movie = create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.IN_PROGRESS.value,
        score=5,
    )
    _create_user_b()

    ctx = browser.new_context()
    page = ctx.new_page()
    login(page, live_server, username="user_b", password="pass12345")

    csrf = page.evaluate(
        "document.cookie.match(/csrftoken=([^;]+)/)?.[1] || ''",
    )
    page.evaluate(
        f"""
        fetch('{live_server.url}/backlog_save', {{
            method: 'POST',
            headers: {{
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-CSRFToken': '{csrf}'
            }},
            body: 'instance_id={movie.id}&media_type=movie&source=tmdb&media_id=550&score=10&status=In+progress&progress=&start_date=&end_date=&notes=&link='
        }})
        """,
    )
    page.wait_for_timeout(1000)

    movie.refresh_from_db()
    assert movie.score == 5

    ctx.close()


def test_user_b_sees_empty_statistics(
    live_server,
    test_user,
    browser,
):
    create_movie(
        test_user,
        "550",
        "Fight Club",
        Status.COMPLETED.value,
        score=9,
    )
    _create_user_b()

    ctx = browser.new_context()
    page = ctx.new_page()
    login(page, live_server, username="user_b", password="pass12345")

    page.goto(f"{live_server.url}/statistics")
    expect(page.get_by_role("heading", name="Statistics")).to_be_visible()

    ctx.close()


def test_demo_user_cannot_change_preferences(
    live_server,
    browser,
    transactional_db,
):
    User = get_user_model()
    demo = User.objects.create_user(
        username="demo",
        password="demo12345",
        is_demo=True,
    )

    ctx = browser.new_context()
    page = ctx.new_page()
    login(page, live_server, username="demo", password="demo12345")

    page.goto(f"{live_server.url}/settings/preferences")
    page.evaluate(
        """() => {
            const cb = document.querySelector('input[name="clickable_media_cards"]');
            if (cb) cb.checked = !cb.checked;
        }""",
    )

    save_btn = page.get_by_role("button", name="Save Preferences")
    if save_btn.is_visible():
        save_btn.click()
        page.wait_for_load_state("networkidle")

    demo.refresh_from_db()
    assert demo.clickable_media_cards is False

    ctx.close()


def test_demo_user_cannot_change_username(
    live_server,
    browser,
    transactional_db,
):
    User = get_user_model()
    User.objects.create_user(
        username="demo",
        password="demo12345",
        is_demo=True,
    )

    ctx = browser.new_context()
    page = ctx.new_page()
    login(page, live_server, username="demo", password="demo12345")

    page.goto(f"{live_server.url}/settings/account")
    username_input = page.locator("input[name='username']")
    if username_input.is_visible():
        username_input.fill("hacked_demo")
        form = username_input.locator("xpath=ancestor::form")
        form.locator("button[type='submit']").click()
        page.wait_for_load_state("networkidle")

    from django.contrib.auth import get_user_model as gum

    demo = gum().objects.get(username="demo")
    assert demo.username == "demo"

    ctx.close()
