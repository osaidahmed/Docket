from playwright.sync_api import Page, expect


def test_account_page_loads(authenticated_page: Page, live_server):
    authenticated_page.goto(f"{live_server.url}/settings/account")
    expect(
        authenticated_page.get_by_role("heading", name="Settings"),
    ).to_be_visible()


def test_preferences_page_has_save_button(
    authenticated_page: Page, live_server,
):
    authenticated_page.goto(f"{live_server.url}/settings/preferences")
    expect(
        authenticated_page.get_by_role("button", name="Save Preferences"),
    ).to_be_visible()


def test_preferences_toggle_persists(
    authenticated_page: Page, live_server, test_user,
):
    authenticated_page.goto(f"{live_server.url}/settings/preferences")

    initial_state = test_user.clickable_media_cards

    # sr-only checkbox requires JS toggle — Playwright can't click through the overlay
    authenticated_page.evaluate(
        """() => {
            const cb = document.querySelector('input[name="clickable_media_cards"]');
            cb.checked = !cb.checked;
        }""",
    )

    authenticated_page.get_by_role("button", name="Save Preferences").click()
    authenticated_page.wait_for_load_state("networkidle")

    test_user.refresh_from_db()
    assert test_user.clickable_media_cards != initial_state


def test_settings_navigation_between_sections(
    authenticated_page: Page, live_server,
):
    authenticated_page.goto(f"{live_server.url}/settings/account")

    for link_text in ["Notifications", "Import", "Export"]:
        link = authenticated_page.get_by_role("link", name=link_text)
        if link.is_visible():
            link.click()
            authenticated_page.wait_for_load_state("networkidle")
            authenticated_page.goto(f"{live_server.url}/settings/account")


def test_import_page_shows_import_sources(
    authenticated_page: Page, live_server,
):
    authenticated_page.goto(f"{live_server.url}/settings/import")
    found = sum(
        1
        for src in ["Trakt", "MAL", "AniList"]
        if authenticated_page.get_by_text(src).first.is_visible()
    )
    assert found > 0


def test_export_page_loads(authenticated_page: Page, live_server):
    authenticated_page.goto(f"{live_server.url}/settings/export")
    expect(authenticated_page).to_have_url(
        f"{live_server.url}/settings/export",
    )
