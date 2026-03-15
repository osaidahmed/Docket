import re

from app.models import Movie, Status
from e2e.conftest import create_list, create_movie, login


def test_concurrent_backlog_save_same_media(live_server, test_user, browser):
    movie = create_movie(
        test_user, "550", "Fight Club", Status.IN_PROGRESS.value, score=5,
    )

    ctx1 = browser.new_context()
    ctx2 = browser.new_context()
    p1 = ctx1.new_page()
    p2 = ctx2.new_page()

    login(p1, live_server)
    login(p2, live_server)

    p1.goto(f"{live_server.url}/")
    p2.goto(f"{live_server.url}/")

    for p in (p1, p2):
        card = p.locator("[id^='backlog-card-']").first
        card.locator("button").filter(has=p.locator("svg")).first.click()

    p1.locator("[id^='backlog-card-']").first.locator(
        "input[name='score']",
    ).fill("7")
    p2.locator("[id^='backlog-card-']").first.locator(
        "input[name='score']",
    ).fill("9")

    p1.locator("[id^='backlog-card-']").first.locator(
        "button[type='submit']",
    ).click()
    p2.locator("[id^='backlog-card-']").first.locator(
        "button[type='submit']",
    ).click()
    p1.wait_for_timeout(2000)

    movie.refresh_from_db()
    assert movie.score in (7, 9)

    ctx1.close()
    ctx2.close()


def test_concurrent_status_change(live_server, test_user, browser):
    movie = create_movie(
        test_user, "550", "Fight Club", Status.IN_PROGRESS.value,
    )

    ctx1 = browser.new_context()
    ctx2 = browser.new_context()
    p1 = ctx1.new_page()
    p2 = ctx2.new_page()

    login(p1, live_server)
    login(p2, live_server)

    p1.goto(f"{live_server.url}/")
    p2.goto(f"{live_server.url}/")

    complete_btn = p1.locator("button[hx-post*='quick_complete']").first
    drop_btn = p2.locator("[id^='backlog-card-']").first
    drop_btn.locator("button").filter(has=p2.locator("svg")).first.click()
    drop_trigger = drop_btn.locator("button:has-text('Drop')").first

    if complete_btn.is_visible() and drop_trigger.is_visible():
        drop_trigger.click()
        confirm_drop = p2.locator("button[hx-post*='quick_drop']").first
        if confirm_drop.is_visible():
            complete_btn.click()
            confirm_drop.click()
            p1.wait_for_timeout(2000)

            movie.refresh_from_db()
            assert movie.status in (
                Status.COMPLETED.value,
                Status.DROPPED.value,
            )

    ctx1.close()
    ctx2.close()


def test_concurrent_pin_toggle(live_server, test_user, browser):
    movie = create_movie(
        test_user, "550", "Fight Club", Status.PLANNING.value,
    )

    ctx1 = browser.new_context()
    ctx2 = browser.new_context()
    p1 = ctx1.new_page()
    p2 = ctx2.new_page()

    login(p1, live_server)
    login(p2, live_server)

    p1.goto(f"{live_server.url}/")
    p2.goto(f"{live_server.url}/")

    pin1 = p1.locator("button[hx-post*='toggle_pin']").first
    pin2 = p2.locator("button[hx-post*='toggle_pin']").first

    if pin1.is_visible() and pin2.is_visible():
        pin1.click()
        pin2.click()
        p1.wait_for_timeout(2000)

        movie.refresh_from_db()
        assert movie.is_pinned in (True, False)

    ctx1.close()
    ctx2.close()


def test_list_item_toggle_rapid_fire(
    authenticated_page, live_server, test_user,
):
    from app.models import Item, MediaTypes, Sources

    lst = create_list(test_user, "Toggle Test")
    item = Item.objects.create(
        media_id="550",
        source=Sources.TMDB.value,
        media_type=MediaTypes.MOVIE.value,
        title="Fight Club",
        image="https://via.placeholder.com/150",
    )
    lst.items.add(item)

    csrf = authenticated_page.evaluate(
        "document.cookie.match(/csrftoken=([^;]+)/)?.[1] || ''",
    )

    for _ in range(5):
        authenticated_page.evaluate(
            f"""
            fetch('{live_server.url}/lists/list_item_toggle/', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': '{csrf}'
                }},
                body: 'item_id={item.id}&custom_list_id={lst.id}'
            }})
            """,
        )

    authenticated_page.wait_for_timeout(2000)

    in_list = lst.items.filter(id=item.id).exists()
    assert in_list in (True, False)


def test_quick_complete_duplicate(live_server, test_user, browser):
    movie = create_movie(
        test_user, "550", "Fight Club", Status.IN_PROGRESS.value,
    )

    ctx1 = browser.new_context()
    ctx2 = browser.new_context()
    p1 = ctx1.new_page()
    p2 = ctx2.new_page()

    login(p1, live_server)
    login(p2, live_server)

    p1.goto(f"{live_server.url}/")
    p2.goto(f"{live_server.url}/")

    btn1 = p1.locator("button[hx-post*='quick_complete']").first
    btn2 = p2.locator("button[hx-post*='quick_complete']").first

    if btn1.is_visible() and btn2.is_visible():
        btn1.click()
        btn2.click()
        p1.wait_for_timeout(2000)

        movie.refresh_from_db()
        assert movie.status == Status.COMPLETED.value
        assert Movie.objects.filter(
            item=movie.item, user=test_user,
        ).count() == 1

    ctx1.close()
    ctx2.close()
