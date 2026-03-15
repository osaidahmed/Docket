import re

from playwright.sync_api import Page, expect


def test_calendar_has_month_navigation(
    authenticated_page: Page, live_server,
):
    authenticated_page.goto(f"{live_server.url}/calendar")
    expect(
        authenticated_page.get_by_role("heading", name="Calendar"),
    ).to_be_visible()
    expect(
        authenticated_page.locator("a[href*='month=']").first,
    ).to_be_visible()


def test_calendar_next_month_changes_url(
    authenticated_page: Page, live_server,
):
    authenticated_page.goto(f"{live_server.url}/calendar")
    authenticated_page.locator("a[href*='month=']").last.click()
    expect(authenticated_page).to_have_url(
        re.compile(r".*/calendar\?.*month="),
    )


def test_calendar_has_export_link(
    authenticated_page: Page, live_server,
):
    authenticated_page.goto(f"{live_server.url}/calendar")
    export_input = authenticated_page.locator("input[readonly]").first
    if export_input.is_visible():
        value = export_input.input_value()
        assert "calendar/download" in value
