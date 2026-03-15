import re

from playwright.sync_api import Page, expect

from app.models import Anime, Item, MediaTypes, Movie, Sources, Status
from e2e.conftest import create_movie


def test_home_with_100_items(authenticated_page: Page, test_user):
    items = Item.objects.bulk_create([
        Item(
            media_id=str(70000 + i),
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title=f"Anime {i}",
            image="https://via.placeholder.com/150",
        )
        for i in range(100)
    ])
    Anime.objects.bulk_create([
        Anime(item=item, user=test_user, status=Status.IN_PROGRESS.value)
        for item in items
    ])

    authenticated_page.reload()
    expect(
        authenticated_page.locator("[id^='backlog-card-']").first,
    ).to_be_visible(timeout=15000)

    card_count = authenticated_page.locator(
        "[id^='backlog-card-']",
    ).count()
    assert card_count > 0


def test_media_list_with_many_items(
    authenticated_page: Page, live_server, test_user,
):
    items = Item.objects.bulk_create([
        Item(
            media_id=str(60000 + i),
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title=f"Anime List {i}",
            image="https://via.placeholder.com/150",
        )
        for i in range(200)
    ])
    Anime.objects.bulk_create([
        Anime(item=item, user=test_user, status=Status.COMPLETED.value)
        for item in items
    ])

    authenticated_page.goto(f"{live_server.url}/medialist/anime")
    expect(authenticated_page.locator("main")).to_be_visible(timeout=15000)


def test_list_with_many_items(
    authenticated_page: Page, live_server, test_user,
):
    from lists.models import CustomList, CustomListItem

    lst = CustomList.objects.create(
        name="Big List", owner=test_user,
    )
    items = Item.objects.bulk_create([
        Item(
            media_id=str(50000 + i),
            source=Sources.MAL.value,
            media_type=MediaTypes.ANIME.value,
            title=f"List Item {i}",
            image="https://via.placeholder.com/150",
        )
        for i in range(100)
    ])
    CustomListItem.objects.bulk_create([
        CustomListItem(custom_list=lst, item=item)
        for item in items
    ])

    authenticated_page.goto(f"{live_server.url}/list/{lst.id}")
    expect(
        authenticated_page.get_by_role("heading", name="Big List"),
    ).to_be_visible(timeout=15000)


def test_rapid_score_updates(
    authenticated_page: Page, live_server, test_user,
):
    movie = create_movie(
        test_user, "550", "Fight Club", Status.COMPLETED.value, score=5,
    )
    authenticated_page.goto(
        f"{live_server.url}/details/tmdb/movie/550/Fight-Club",
    )

    csrf = authenticated_page.evaluate(
        "document.cookie.match(/csrftoken=([^;]+)/)?.[1] || ''",
    )

    for score in range(1, 11):
        authenticated_page.evaluate(
            f"""
            fetch('{live_server.url}/update-score/movie/{movie.id}/', {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': '{csrf}'
                }},
                body: 'score={score}'
            }})
            """,
        )

    authenticated_page.wait_for_timeout(3000)

    movie.refresh_from_db()
    assert 1 <= movie.score <= 10


def test_rapid_status_transitions(
    authenticated_page: Page, live_server, test_user,
):
    movie = create_movie(
        test_user, "550", "Fight Club", Status.PLANNING.value,
    )
    authenticated_page.goto(f"{live_server.url}/")

    start_btn = authenticated_page.locator(
        "button[hx-post*='quick_status_transition']",
    ).first
    if start_btn.is_visible():
        with authenticated_page.expect_response(
            re.compile(r".*/quick_status_transition"),
        ):
            start_btn.click()

        movie.refresh_from_db()
        assert movie.status == Status.IN_PROGRESS.value

        done_btn = authenticated_page.locator(
            "button[hx-post*='quick_complete']",
        ).first
        if done_btn.is_visible():
            with authenticated_page.expect_response(
                re.compile(r".*/quick_complete"),
            ):
                done_btn.click()

            movie.refresh_from_db()
            assert movie.status == Status.COMPLETED.value
