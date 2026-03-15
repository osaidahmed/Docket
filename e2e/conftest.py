import os
import time

import pytest
from django.contrib.auth import get_user_model
from playwright.sync_api import expect

os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"


def login(page, live_server, username="e2etest", password="e2epass12345"):
    for attempt in range(5):
        page.goto(f"{live_server.url}/accounts/login/")
        page.get_by_placeholder("Enter your username").fill(username)
        page.get_by_placeholder("Enter your password").fill(password)
        page.get_by_role("button", name="Sign In").click()
        try:
            expect(page).to_have_url(f"{live_server.url}/", timeout=10000)
            return
        except AssertionError:
            if attempt < 4:
                time.sleep(2)
            else:
                raise


@pytest.fixture()
def test_user(transactional_db):
    from django.db import connection

    # ensure previous test's DB flush is visible to this connection
    connection.ensure_connection()

    User = get_user_model()
    user = User.objects.create_user(username="e2etest", password="e2epass12345")
    for field in user._meta.get_fields():
        if field.name.endswith("_enabled") and hasattr(field, "default"):
            setattr(user, field.name, True)
    user.save()
    return user


@pytest.fixture()
def authenticated_page(page, live_server, test_user):
    login(page, live_server)
    return page
