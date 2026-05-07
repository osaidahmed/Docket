import re

from playwright.sync_api import Page, expect

from e2e.conftest import login


def test_login_page_has_form_elements(page: Page, live_server, db):
    page.goto(f"{live_server.url}/accounts/login/")
    expect(page.get_by_placeholder("Enter your username")).to_be_visible()
    expect(page.get_by_placeholder("Enter your password")).to_be_visible()
    expect(page.get_by_role("button", name="Sign In")).to_be_visible()
    expect(page.get_by_role("link", name="Register now")).to_be_visible()


def test_login_success_redirects_to_home(page: Page, live_server, test_user):
    login(page, live_server)
    expect(page).to_have_url(f"{live_server.url}/")
    expect(page.get_by_role("link", name="Home")).to_be_visible()


def test_login_failure_shows_error(page: Page, live_server, test_user):
    page.goto(f"{live_server.url}/accounts/login/")
    page.get_by_placeholder("Enter your username").fill("e2etest")
    page.get_by_placeholder("Enter your password").fill("wrongpassword")
    page.get_by_role("button", name="Sign In").click()
    expect(page).to_have_url(re.compile(r".*/accounts/login/"))
    expect(page.get_by_text("username and/or password")).to_be_visible()
    expect(page.get_by_placeholder("Enter your username")).to_be_visible()


def test_empty_login_stays_on_page(page: Page, live_server, db):
    page.goto(f"{live_server.url}/accounts/login/")
    page.get_by_role("button", name="Sign In").click()
    expect(page).to_have_url(re.compile(r".*/accounts/login/"))


def test_protected_routes_redirect_to_login(page: Page, live_server, db):
    for path in ["/", "/news", "/statistics", "/lists", "/calendar"]:
        page.goto(f"{live_server.url}{path}")
        expect(page).to_have_url(re.compile(r".*/accounts/login/"))


def test_logout_clears_session(authenticated_page: Page, live_server):
    authenticated_page.get_by_role("button", name="Sign Out").click()
    expect(authenticated_page).to_have_url(re.compile(r".*/accounts/login/"))
    authenticated_page.goto(f"{live_server.url}/")
    expect(authenticated_page).to_have_url(re.compile(r".*/accounts/login/"))


def test_login_redirects_back_to_requested_page(
    page: Page,
    live_server,
    test_user,
):
    page.goto(f"{live_server.url}/statistics")
    expect(page).to_have_url(re.compile(r".*/accounts/login/.*next=.*statistics"))
    page.get_by_placeholder("Enter your username").fill("e2etest")
    page.get_by_placeholder("Enter your password").fill("e2epass12345")
    page.get_by_role("button", name="Sign In").click()
    expect(page).to_have_url(re.compile(r".*/statistics"))
