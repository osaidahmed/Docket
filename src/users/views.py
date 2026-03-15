import logging

import apprise
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.core.cache import cache
from django.db import IntegrityError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.defaultfilters import pluralize
from django.views.decorators.http import require_GET, require_http_methods, require_POST
from django_celery_beat.models import PeriodicTask

from app.models import Item, MediaTypes
from users.forms import NotificationSettingsForm, PasswordChangeForm, UserUpdateForm
from users.models import (
    DateFormatChoices,
    HomeTruncationChoices,
    QuickWatchDateChoices,
    TimeFormatChoices,
)

logger = logging.getLogger(__name__)


def _handle_username_update(request):
    form = UserUpdateForm(request.POST, instance=request.user)
    if not form.is_valid():
        logger.warning(
            "Failed username change for user: %s - %s",
            request.user.username,
            list(form.errors.keys()),
        )
        return form, None
    form.save()
    messages.success(request, "Your username has been updated!")
    logger.info("Successful username change for user: %s", request.user.username)
    return form, redirect("account")


def _handle_password_update(request):
    form = PasswordChangeForm(user=request.user, data=request.POST)
    if not form.is_valid():
        logger.warning(
            "Failed password change for user: %s - %s",
            request.user.username,
            list(form.errors.keys()),
        )
        return form, None
    user = form.save()
    update_session_auth_hash(request, user)
    messages.success(request, "Your password has been updated!")
    logger.info("Successful password change for user: %s", request.user.username)
    return form, redirect("account")


@require_http_methods(["GET", "POST"])
def account(request):
    """Update the user's account and import/export data."""
    user_form = UserUpdateForm(instance=request.user)
    password_form = PasswordChangeForm(user=request.user)

    if request.method == "POST":
        if "username" in request.POST:
            user_form, response = _handle_username_update(request)
            if response:
                return response
        elif any(
            key in request.POST
            for key in ["old_password", "new_password1", "new_password2"]
        ):
            password_form, response = _handle_password_update(request)
            if response:
                return response

    return render(
        request,
        "users/account.html",
        {"user_form": user_form, "password_form": password_form},
    )


@require_http_methods(["GET", "POST"])
def notifications(request):
    """Render the notifications settings page."""
    if request.method == "GET":
        form = NotificationSettingsForm(instance=request.user)
        return render(request, "users/notifications.html", {"form": form})

    form = NotificationSettingsForm(request.POST, instance=request.user)
    if not form.is_valid():
        for errors in form.errors.values():
            for error in errors:
                messages.error(request, error)
        return redirect("notifications")

    form.save()
    messages.success(request, "Notification settings updated successfully!")
    return redirect("notifications")


@require_GET
def search_items(request):
    """Search for items to exclude from notifications."""
    query = request.GET.get("q", "").strip()

    if not query or len(query) <= 1:
        return render(
            request,
            "users/components/search_results.html",
        )

    # Search for items that match the query
    items = (
        Item.objects.filter(
            Q(title__icontains=query),
        )
        .exclude(
            id__in=request.user.notification_excluded_items.values_list(
                "id",
                flat=True,
            ),
        )
        .distinct()[:10]
    )

    return render(
        request,
        "users/components/search_results.html",
        {"items": items, "query": query},
    )


def _toggle_excluded_item(request, add):
    item = get_object_or_404(Item, id=request.POST["item_id"])
    m2m = request.user.notification_excluded_items
    if add:
        m2m.add(item)
    else:
        m2m.remove(item)
    return render(
        request,
        "users/components/excluded_items.html",
        {"excluded_items": m2m.all()},
    )


@require_POST
def exclude_item(request):
    """Exclude an item from notifications."""
    return _toggle_excluded_item(request, add=True)


@require_POST
def include_item(request):
    """Remove an item from the exclusion list."""
    return _toggle_excluded_item(request, add=False)


@require_GET
def test_notification(request):
    """Send a test notification to the user."""
    try:
        # Create Apprise instance
        apobj = apprise.Apprise()

        # Add all notification URLs
        notification_urls = [
            url.strip()
            for url in request.user.notification_urls.splitlines()
            if url.strip()
        ]
        if not notification_urls:
            messages.error(request, "No notification URLs configured.")
            return redirect("notifications")

        for url in notification_urls:
            apobj.add(url)

        # Send test notification
        result = apobj.notify(
            title="Yamtrack Test Notification",
            body=(
                "This is a test notification from Yamtrack. "
                "If you're seeing this, your notifications are working correctly!"
            ),
        )

        if result:
            messages.success(request, "Test notification sent successfully!")
        else:
            messages.error(request, "Failed to send test notification.")
    except Exception:
        logger.exception("Error sending notification")

    return redirect("notifications")


def _update_preferences_from_post(user, post_data, all_types):
    user.clickable_media_cards = "clickable_media_cards" in post_data
    user.quick_watch_date = post_data.get(
        "quick_watch_date",
        QuickWatchDateChoices.CURRENT_DATE,
    )
    user.home_truncation = post_data.get(
        "home_truncation",
        HomeTruncationChoices.ALL,
    )
    user.progress_bar = "progress_bar" in post_data
    user.hide_completed_recommendations = "hide_completed_recommendations" in post_data
    user.hide_zero_rating = "hide_zero_rating" in post_data
    user.group_related_media = "group_related_media" in post_data

    color_scheme = post_data.get("color_scheme", "charcoal")
    valid_schemes = {c[0] for c in user.COLOR_SCHEME_CHOICES}
    if color_scheme in valid_schemes:
        user.color_scheme = color_scheme

    user.date_format = post_data.get("date_format", DateFormatChoices.ISO)
    user.time_format = post_data.get("time_format", TimeFormatChoices.HOUR_24)

    media_types_checked = post_data.getlist("media_types_checkboxes")
    for media_type in all_types:
        setattr(user, f"{media_type}_enabled", media_type in media_types_checked)

    order_json = post_data.get("media_type_order", "")
    if order_json:
        import contextlib  # noqa: PLC0415
        import json  # noqa: PLC0415

        with contextlib.suppress(json.JSONDecodeError, TypeError):
            user.media_type_order = json.loads(order_json)

    user.save()


@require_POST
def refresh_relationships(request):
    """Trigger background task to refresh anime relationship data."""
    from app.tasks import refresh_anime_relationships_task  # noqa: PLC0415

    refresh_anime_relationships_task.delay(request.user.id)
    return HttpResponse(
        status=200,
        content='<span class="text-xs text-emerald-400">Refreshing...</span>',
    )


@require_http_methods(["GET", "POST"])
def preferences(request):
    """Render the preferences settings page."""
    all_types = [mt for mt in MediaTypes.values if mt != MediaTypes.EPISODE.value]

    if request.method == "POST":
        if request.user.is_demo:
            messages.error(request, "This section is view-only for demo accounts.")
            return redirect("preferences")
        _update_preferences_from_post(request.user, request.POST, all_types)
        messages.success(request, "Settings updated.")
        return redirect("preferences")

    seen = set()
    ordered = []
    for mt in list(request.user.media_type_order or []) + all_types:
        if mt not in seen and mt in all_types:
            ordered.append(mt)
            seen.add(mt)

    return render(
        request,
        "users/preferences.html",
        {
            "media_types": ordered,
            "quick_watch_date_choices": QuickWatchDateChoices.choices,
            "home_truncation_choices": HomeTruncationChoices.choices,
            "date_format_choices": DateFormatChoices.choices,
            "time_format_choices": TimeFormatChoices.choices,
            "color_scheme_choices": request.user.COLOR_SCHEME_CHOICES,
        },
    )


@require_GET
def integrations(request):
    """Render the integrations settings page."""
    return render(request, "users/integrations.html")


@require_GET
def import_data(request):
    """Render the import data settings page."""
    import_tasks = request.user.get_import_tasks()
    return render(request, "users/import_data.html", {"import_tasks": import_tasks})


@require_GET
def export_data(request):
    """Render the export data settings page."""
    return render(request, "users/export_data.html")


@require_GET
def advanced(request):
    """Render the advanced settings page."""
    return render(request, "users/advanced.html")


@require_GET
def about(request):
    """Render the about page."""
    return render(request, "users/about.html", {"version": settings.VERSION})


@require_POST
def delete_import_schedule(request):
    """Delete an import schedule."""
    task_name = request.POST.get("task_name")
    try:
        task = PeriodicTask.objects.get(
            name=task_name,
            kwargs__contains=f'"user_id": {request.user.id}',
        )
        task.delete()
        messages.success(request, "Import schedule deleted.")
    except PeriodicTask.DoesNotExist:
        messages.error(request, "Import schedule not found.")
    return redirect("import_data")


@require_POST
def regenerate_token(request):
    """Regenerate the token for the user."""
    while True:
        try:
            request.user.regenerate_token()
            messages.success(request, "Token regenerated successfully.")
            break
        except IntegrityError:
            continue
    return redirect("integrations")


@require_POST
def update_plex_usernames(request):
    """Update the Plex usernames for the user."""
    usernames = request.POST.get("plex_usernames", "")

    username_list = [u.strip() for u in usernames.split(",") if u.strip()]

    seen = set()
    deduplicated_usernames = [
        u for u in username_list if not (u in seen or seen.add(u))
    ]

    # Reconstruct with comma-space separation
    cleaned_usernames = ", ".join(deduplicated_usernames)

    if cleaned_usernames != request.user.plex_usernames:
        request.user.plex_usernames = cleaned_usernames
        request.user.save(update_fields=["plex_usernames"])
        messages.success(request, "Plex usernames updated successfully.")

    return redirect("integrations")


@require_POST
def clear_search_cache(request):
    """Clear all cached search entries."""
    deleted = cache.delete_pattern("search_*")

    messages.success(
        request,
        f"Successfully cleared {deleted} search entr{pluralize(deleted, 'y,ies')}",
    )
    logger.info(
        "Successfully cleared %s search entries",
        deleted,
    )

    return redirect("advanced")
