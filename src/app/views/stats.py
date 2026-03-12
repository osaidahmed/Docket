from pathlib import Path

from django.conf import settings
from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.timezone import datetime
from django.views.decorators.http import require_GET

from app import statistics as stats


@require_GET
def statistics(request):
    """Return the statistics page."""
    timeformat = "%Y-%m-%d"
    today = timezone.localdate()
    one_year_ago = today.replace(year=today.year - 1)

    start_date_str = request.GET.get("start-date") or one_year_ago.strftime(timeformat)
    end_date_str = request.GET.get("end-date") or today.strftime(timeformat)

    if start_date_str == "all" and end_date_str == "all":
        start_date = None
        end_date = None
    else:
        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)

        if start_date and end_date:
            start_date = timezone.make_aware(
                datetime.combine(start_date, datetime.min.time()),
            )

            end_date = timezone.make_aware(
                datetime.combine(end_date, datetime.max.time()),
            )

    user_media, media_count = stats.get_user_media(
        request.user,
        start_date,
        end_date,
    )

    media_type_distribution = stats.get_media_type_distribution(
        media_count,
    )
    score_distribution, top_rated = stats.get_score_distribution(user_media)
    status_distribution = stats.get_status_distribution(user_media)
    status_pie_chart_data = stats.get_status_pie_chart_data(
        status_distribution,
    )
    timeline = stats.get_timeline(user_media)

    activity_data = stats.get_activity_data(request.user, start_date, end_date)

    context = {
        "start_date": start_date,
        "end_date": end_date,
        "media_count": media_count,
        "activity_data": activity_data,
        "media_type_distribution": media_type_distribution,
        "score_distribution": score_distribution,
        "top_rated": top_rated,
        "status_distribution": status_distribution,
        "status_pie_chart_data": status_pie_chart_data,
        "timeline": timeline,
    }

    return render(request, "app/statistics.html", context)


@require_GET
def service_worker(_request):
    """Serve the service worker file."""
    sw_path = Path(settings.STATICFILES_DIRS[0]) / "js" / "serviceworker.js"
    with sw_path.open() as f:
        response = HttpResponse(f.read(), content_type="application/javascript")
        response["Service-Worker-Allowed"] = "/"
        return response
