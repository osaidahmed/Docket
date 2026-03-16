from playwright.sync_api import Page, expect

from app.models import Item


def test_create_entry_page_has_form(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/create")
    expect(authenticated_page.locator("input[name='title']")).to_be_visible()
    expect(
        authenticated_page.locator("select[name='status']"),
    ).to_be_visible()
    expect(
        authenticated_page.get_by_role("button", name="Create Entry"),
    ).to_be_visible()


def test_create_movie_entry(
    authenticated_page: Page,
    live_server,
    test_user,
):
    authenticated_page.goto(f"{live_server.url}/create")

    movie_btn = authenticated_page.locator(
        "button[type='button']",
    ).filter(has_text="Movie")
    if movie_btn.is_visible():
        movie_btn.click()

    authenticated_page.locator("input[name='title']").fill("My Custom Movie")
    authenticated_page.locator("select[name='status']").select_option(
        "Completed",
    )

    authenticated_page.get_by_role("button", name="Create Entry").click()
    authenticated_page.wait_for_load_state("networkidle")

    assert Item.objects.filter(title="My Custom Movie").exists()


def test_add_by_link_page_loads(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/add_by_link")
    expect(
        authenticated_page.locator("textarea[name='links'], textarea[id='links']"),
    ).to_be_visible()


def test_add_by_link_empty_submission(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/add_by_link")
    submit = authenticated_page.get_by_role(
        "button",
        name="Process Links",
    )
    if submit.is_visible():
        submit.click()
        authenticated_page.wait_for_load_state("networkidle")
