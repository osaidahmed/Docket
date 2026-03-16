import re
from datetime import date

from playwright.sync_api import Page, expect


def test_calendar_has_month_navigation(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/calendar")
    expect(
        authenticated_page.get_by_role("heading", name="Calendar"),
    ).to_be_visible()
    expect(
        authenticated_page.locator("a[href*='month=']").first,
    ).to_be_visible()


def test_calendar_next_month_changes_url(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/calendar")
    authenticated_page.locator("a[href*='month=']").last.click()
    expect(authenticated_page).to_have_url(
        re.compile(r".*/calendar\?.*month="),
    )


def test_calendar_prev_month(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/calendar")
    authenticated_page.locator("a[href*='month=']").first.click()
    expect(authenticated_page).to_have_url(
        re.compile(r".*/calendar\?.*month="),
    )


def test_calendar_has_export_link(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/calendar")
    export_input = authenticated_page.locator("input[readonly]").first
    if export_input.is_visible():
        value = export_input.input_value()
        assert "calendar/download" in value


def test_calendar_view_toggle_to_list(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/calendar")
    list_link = authenticated_page.locator("a[href*='view=list']").first
    if list_link.is_visible():
        list_link.click()
        expect(authenticated_page).to_have_url(
            re.compile(r".*view=list"),
        )


def test_calendar_view_toggle_to_grid(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/calendar?view=list")
    grid_link = authenticated_page.locator("a[href*='view=grid']").first
    if grid_link.is_visible():
        grid_link.click()
        expect(authenticated_page).to_have_url(
            re.compile(r".*view=grid"),
        )


def test_calendar_today_button(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(
        f"{live_server.url}/calendar?month=1&year=2020",
    )
    today = date.today()
    today_link = authenticated_page.locator(
        f"a[href*='month={today.month}'][href*='year={today.year}']",
    ).first
    if today_link.is_visible():
        today_link.click()
        expect(authenticated_page).to_have_url(
            re.compile(rf".*month={today.month}"),
        )
