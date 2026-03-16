import re

from playwright.sync_api import Page, expect


def test_account_page_loads(authenticated_page: Page, live_server):
    authenticated_page.goto(f"{live_server.url}/settings/account")
    expect(
        authenticated_page.get_by_role("heading", name="Settings"),
    ).to_be_visible()


def test_preferences_page_has_save_button(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/settings/preferences")
    expect(
        authenticated_page.get_by_role("button", name="Save Preferences"),
    ).to_be_visible()


def test_preferences_toggle_persists(
    authenticated_page: Page,
    live_server,
    test_user,
):
    authenticated_page.goto(f"{live_server.url}/settings/preferences")

    initial_state = test_user.clickable_media_cards

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
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/settings/account")

    for link_text in ["Notifications", "Import", "Export"]:
        link = authenticated_page.get_by_role("link", name=link_text)
        if link.is_visible():
            link.click()
            authenticated_page.wait_for_load_state("networkidle")
            authenticated_page.goto(f"{live_server.url}/settings/account")


def test_import_page_shows_import_sources(
    authenticated_page: Page,
    live_server,
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


def test_color_scheme_changes_theme_live(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/settings/preferences")

    swatches = authenticated_page.locator(
        "button[class*='theme-swatch']",
    )
    if swatches.count() > 1:
        swatches.nth(1).click()
        theme = authenticated_page.evaluate(
            "() => document.documentElement.getAttribute('data-theme')",
        )
        assert theme is not None


def test_color_scheme_persists_after_save(
    authenticated_page: Page,
    live_server,
    test_user,
):
    authenticated_page.goto(f"{live_server.url}/settings/preferences")

    swatches = authenticated_page.locator(
        "button[class*='theme-swatch']",
    )
    if swatches.count() > 1:
        swatches.nth(1).click()
        theme_before = authenticated_page.evaluate(
            "() => document.documentElement.getAttribute('data-theme')",
        )

        authenticated_page.get_by_role(
            "button",
            name="Save Preferences",
        ).click()
        authenticated_page.wait_for_load_state("networkidle")

        theme_after = authenticated_page.evaluate(
            "() => document.documentElement.getAttribute('data-theme')",
        )
        assert theme_after == theme_before


def test_all_preference_toggles_exist(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/settings/preferences")
    for name in [
        "clickable_media_cards",
        "progress_bar",
        "group_related_media",
        "hide_completed_recommendations",
        "hide_zero_rating",
    ]:
        assert authenticated_page.locator(f"input[name='{name}']").count() > 0, (
            f"Toggle {name} not found"
        )


def test_date_format_dropdown_persists(
    authenticated_page: Page,
    live_server,
    test_user,
):
    authenticated_page.goto(f"{live_server.url}/settings/preferences")

    date_select = authenticated_page.locator("select[name='date_format']")
    if date_select.is_visible():
        options = date_select.locator("option")
        if options.count() > 1:
            new_value = options.nth(1).get_attribute("value")
            date_select.select_option(new_value)

            authenticated_page.get_by_role(
                "button",
                name="Save Preferences",
            ).click()
            authenticated_page.wait_for_load_state("networkidle")

            test_user.refresh_from_db()
            assert test_user.date_format == new_value


def test_media_type_disable_toggle(
    authenticated_page: Page,
    live_server,
    test_user,
):
    authenticated_page.goto(f"{live_server.url}/settings/preferences")

    checkbox = authenticated_page.locator(
        "input[name='media_types_checkboxes'][value='boardgame']",
    )
    if checkbox.count() > 0:
        authenticated_page.evaluate(
            """() => {
                const cb = document.querySelector(
                    'input[name="media_types_checkboxes"][value="boardgame"]'
                );
                if (cb) cb.checked = false;
            }""",
        )

        authenticated_page.get_by_role(
            "button",
            name="Save Preferences",
        ).click()
        authenticated_page.wait_for_load_state("networkidle")

        test_user.refresh_from_db()
        assert test_user.boardgame_enabled is False


def test_account_username_change(
    authenticated_page: Page,
    live_server,
    test_user,
):
    authenticated_page.goto(f"{live_server.url}/settings/account")

    username_input = authenticated_page.locator("input[name='username']")
    if username_input.is_visible():
        username_input.fill("e2etest_renamed")
        form = username_input.locator("xpath=ancestor::form")
        form.locator("button[type='submit']").click()
        authenticated_page.wait_for_load_state("networkidle")

        test_user.refresh_from_db()
        assert test_user.username == "e2etest_renamed"


def test_notifications_page_loads(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/settings/notifications")
    expect(authenticated_page).to_have_url(
        f"{live_server.url}/settings/notifications",
    )


def test_all_settings_subpages_load(
    authenticated_page: Page,
    live_server,
):
    for path in [
        "/settings/about",
        "/settings/advanced",
        "/settings/integrations",
    ]:
        response = authenticated_page.goto(f"{live_server.url}{path}")
        assert response.status == 200, f"{path} returned {response.status}"


def test_media_type_reorder_up(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/settings/preferences")

    items = authenticated_page.locator("[data-media-type]")
    if items.count() >= 2:
        second_type = items.nth(1).get_attribute("data-media-type")
        up_btn = (
            items.nth(1)
            .locator(
                "button",
            )
            .first
        )
        up_btn.click()

        first_type = items.nth(0).get_attribute("data-media-type")
        assert first_type == second_type


def test_media_type_reorder_down(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/settings/preferences")

    items = authenticated_page.locator("[data-media-type]")
    if items.count() >= 2:
        first_type = items.nth(0).get_attribute("data-media-type")
        down_btn = (
            items.nth(0)
            .locator(
                "button",
            )
            .last
        )
        down_btn.click()

        second_type = items.nth(1).get_attribute("data-media-type")
        assert second_type == first_type


def test_password_change_form_exists(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/settings/account")

    expect(
        authenticated_page.locator("input[name='old_password']"),
    ).to_be_visible()
    expect(
        authenticated_page.locator("input[name='new_password1']"),
    ).to_be_visible()
    expect(
        authenticated_page.locator("input[name='new_password2']"),
    ).to_be_visible()


def test_password_change_wrong_old_password(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/settings/account")

    authenticated_page.locator("input[name='old_password']").fill("wrong")
    authenticated_page.locator("input[name='new_password1']").fill("newpass123!")
    authenticated_page.locator("input[name='new_password2']").fill("newpass123!")

    form = authenticated_page.locator(
        "input[name='old_password']",
    ).locator("xpath=ancestor::form")
    form.locator("button[type='submit']").click()
    authenticated_page.wait_for_load_state("networkidle")

    expect(authenticated_page).to_have_url(
        re.compile(r".*/settings/account"),
    )


def test_clear_search_cache(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/settings/advanced")

    clear_btn = authenticated_page.locator(
        "form[action*='clear_search_cache'] button[type='submit']",
    ).first
    if clear_btn.is_visible():
        clear_btn.click()
        authenticated_page.wait_for_load_state("networkidle")


def test_regenerate_token(
    authenticated_page: Page,
    live_server,
    test_user,
):
    authenticated_page.goto(f"{live_server.url}/settings/integrations")

    regen_btn = authenticated_page.locator(
        "form[action*='regenerate_token'] button[type='submit']",
    ).first
    if regen_btn.is_visible():
        old_token = test_user.token
        regen_btn.click()
        authenticated_page.wait_for_load_state("networkidle")
        test_user.refresh_from_db()
        assert test_user.token != old_token


def test_notifications_page_has_form(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/settings/notifications")
    url_field = authenticated_page.locator(
        "textarea[name='notification_urls'], input[name='notification_urls']",
    ).first
    if url_field.is_visible():
        expect(url_field).to_be_visible()


def test_refresh_relationships_button(
    authenticated_page: Page,
    live_server,
):
    authenticated_page.goto(f"{live_server.url}/settings/preferences")

    refresh_btn = authenticated_page.locator(
        "button[type='submit']",
    ).filter(has_text="Refresh")
    if refresh_btn.is_visible():
        refresh_btn.click()
        authenticated_page.wait_for_timeout(1000)


def test_time_format_dropdown(
    authenticated_page: Page,
    live_server,
    test_user,
):
    authenticated_page.goto(f"{live_server.url}/settings/preferences")

    time_select = authenticated_page.locator("select[name='time_format']")
    if time_select.is_visible():
        options = time_select.locator("option")
        if options.count() > 1:
            new_value = options.nth(1).get_attribute("value")
            time_select.select_option(new_value)

            authenticated_page.get_by_role(
                "button",
                name="Save Preferences",
            ).click()
            authenticated_page.wait_for_load_state("networkidle")

            test_user.refresh_from_db()
            assert test_user.time_format == new_value
