import calendar as cal
import logging
from datetime import UTC, date, timedelta

import icalendar
from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from events import tasks
from events.models import Event
from users.models import User

logger = logging.getLogger(__name__)


def _parse_calendar_date(request):
    """Parse month/year from request, falling back to today."""
    month = request.GET.get("month")
    year = request.GET.get("year")
    try:
        current_date = (
            date(int(year), int(month), 1) if month and year else timezone.localdate()
        )
        return current_date.month, current_date.year
    except (ValueError, TypeError):
        logger.warning("Invalid month or year provided: %s, %s", month, year)
        today = timezone.localdate()
        return today.month, today.year


def _calendar_navigation(month, year):
    """Compute prev/next month+year and the first/last day of the month."""
    is_december = month == 12  # noqa: PLR2004
    is_january = month == 1
    first_day = date(year, month, 1)
    last_day = date(
        year + 1 if is_december else year,
        1 if is_december else month + 1,
        1,
    ) - timedelta(days=1)
    return {
        "prev_month": 12 if is_january else month - 1,
        "prev_year": year - 1 if is_january else year,
        "next_month": 1 if is_december else month + 1,
        "next_year": year + 1 if is_december else year,
        "first_day": first_day,
        "last_day": last_day,
    }


def _group_releases_by_day(releases):
    """Group release events by their local day."""
    release_dict = {}
    for release in releases:
        day = timezone.localtime(release.datetime).day
        release_dict.setdefault(day, []).append(release)
    return release_dict


@require_GET
def calendar(request):
    """Display the calendar page."""
    view_type = request.user.update_preference(
        "calendar_layout",
        request.GET.get("view"),
    )
    month, year = _parse_calendar_date(request)
    nav = _calendar_navigation(month, year)
    releases = Event.objects.get_user_events(
        request.user, nav["first_day"], nav["last_day"]
    )

    context = {
        "calendar": cal.monthcalendar(year, month),
        "month": month,
        "month_name": cal.month_name[month],
        "year": year,
        "release_dict": _group_releases_by_day(releases),
        "today": timezone.localdate(),
        "view_type": view_type,
        **{k: nav[k] for k in ("prev_month", "prev_year", "next_month", "next_year")},
    }
    return render(request, "events/calendar.html", context)


@require_POST
def reload_calendar(request):
    """Refresh the calendar with the latest dates."""
    tasks.reload_calendar.delay(request.user)
    messages.info(request, "The task to refresh upcoming releases has been queued.")
    return redirect("calendar")


@login_not_required
@csrf_exempt
@require_http_methods(["GET", "HEAD", "PROPFIND"])
def download_calendar(_, token: str):
    """Download the calendar as a iCalendar file."""
    try:
        user = User.objects.get(token=token)
    except ObjectDoesNotExist:
        logger.warning(
            "Could not process Calendar request: Invalid token: %s",
            token,
        )
        return HttpResponse(status=401)

    now = timezone.now()

    # Define default start and end date (from past 30 days to incoming 90 days)
    start_date = now.date() - timedelta(days=30)
    end_date = now.date() + timedelta(days=90)

    # Retrieve release events
    releases = Event.objects.get_user_events(user, start_date, end_date)

    # Create iCalendar object
    cal = icalendar.Calendar()
    cal.add("prodid", "-//Docket//EN")
    cal.add("version", "2.0")

    for release in releases:
        cal_event = icalendar.Event()
        cal_event.add("uid", release.id)
        cal_event.add("summary", str(release))
        dt_tz_aware = release.datetime.replace(tzinfo=UTC)
        cal_event.add("dtstart", dt_tz_aware)
        cal_event.add("dtend", dt_tz_aware)
        cal_event.add("dtstamp", now)
        cal.add_component(cal_event)

    # Return the iCal file
    response = HttpResponse(cal.to_ical(), content_type="text/calendar")
    response["Content-Disposition"] = 'attachment; filename="calendar.ics"'
    return response
