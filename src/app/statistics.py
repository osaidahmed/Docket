import calendar
import datetime
import heapq
import itertools
import logging
from collections import defaultdict

from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.db import models
from django.db.models import (
    Prefetch,
    Q,
)
from django.utils import timezone

from app import config
from app.models import TV, BasicMedia, Episode, MediaManager, MediaTypes, Season, Status
from app.templatetags import app_tags

logger = logging.getLogger(__name__)


def get_user_media(user, start_date, end_date):
    """Get all media items and their counts for a user within date range."""
    media_models = [
        apps.get_model(app_label="app", model_name=media_type)
        for media_type in user.get_active_media_types()
    ]
    user_media = {}
    media_count = {"total": 0}

    base_episodes = _build_base_episodes(user, media_models, start_date, end_date)

    for model in media_models:
        media_type = model.__name__.lower()
        queryset = _build_model_queryset(
            model,
            user,
            base_episodes,
            start_date,
            end_date,
        ).select_related("item")

        user_media[media_type] = queryset
        count = queryset.count()
        media_count[media_type] = count
        media_count["total"] += count

    logger.info(
        "%s - Retrieved media %s",
        user,
        "for all time" if start_date is None else f"from {start_date} to {end_date}",
    )
    return user_media, media_count


def _build_base_episodes(user, media_models, start_date, end_date):
    if TV not in media_models and Season not in media_models:
        return None
    if start_date is None and end_date is None:
        return Episode.objects.filter(related_season__user=user)
    return Episode.objects.filter(
        related_season__user=user,
        end_date__range=(start_date, end_date),
    )


def _build_model_queryset(model, user, base_episodes, start_date, end_date):
    if model == TV:
        return _build_tv_queryset(base_episodes)
    if model == Season:
        return _build_season_queryset(base_episodes)
    if start_date is None and end_date is None:
        return model.objects.filter(user=user)
    return model.objects.filter(user=user).filter(
        _build_date_range_filter(start_date, end_date),
    )


def _build_tv_queryset(base_episodes):
    tv_ids = base_episodes.values_list(
        "related_season__related_tv",
        flat=True,
    ).distinct()
    return TV.objects.filter(id__in=tv_ids).prefetch_related(
        Prefetch(
            "seasons",
            queryset=Season.objects.select_related("item").prefetch_related(
                Prefetch(
                    "episodes",
                    queryset=base_episodes.filter(
                        related_season__related_tv__in=tv_ids,
                    ),
                ),
            ),
        ),
    )


def _build_season_queryset(base_episodes):
    season_ids = base_episodes.values_list("related_season", flat=True).distinct()
    return Season.objects.filter(id__in=season_ids).prefetch_related(
        Prefetch("episodes", queryset=base_episodes),
    )


def _build_date_range_filter(start_date, end_date):
    return (
        (
            Q(start_date__isnull=False)
            & Q(end_date__isnull=False)
            & ~(Q(end_date__lt=start_date) | Q(start_date__gt=end_date))
        )
        | (
            Q(start_date__isnull=False)
            & Q(end_date__isnull=True)
            & Q(start_date__gte=start_date)
            & Q(start_date__lte=end_date)
        )
        | (
            Q(start_date__isnull=True)
            & Q(end_date__isnull=False)
            & Q(end_date__gte=start_date)
            & Q(end_date__lte=end_date)
        )
    )


def get_media_type_distribution(media_count):
    """Get data formatted for Chart.js pie chart."""
    # Define colors for each media type
    # Format for Chart.js
    chart_data = {
        "labels": [],
        "datasets": [
            {
                "data": [],
                "backgroundColor": [],
            },
        ],
    }

    # Only include media types with counts > 0
    for media_type, count in media_count.items():
        if media_type != "total" and count > 0:
            # Format label with first letter capitalized
            label = app_tags.media_type_readable(media_type)
            chart_data["labels"].append(label)
            chart_data["datasets"][0]["data"].append(count)
            chart_data["datasets"][0]["backgroundColor"].append(
                config.get_stats_color(media_type),
            )
    return chart_data


def get_status_distribution(user_media):
    """Get status distribution for each media type within date range."""
    distribution = {}
    total_completed = 0
    # Define status order to ensure consistent stacking
    status_order = list(Status.values)
    for media_type, media_list in user_media.items():
        status_counts = dict.fromkeys(status_order, 0)
        counts = media_list.values("status").annotate(count=models.Count("id"))
        for count_data in counts:
            status_counts[count_data["status"]] = count_data["count"]
            if count_data["status"] == Status.COMPLETED.value:
                total_completed += count_data["count"]

        distribution[media_type] = status_counts

    # Format the response for charting
    return {
        "labels": [app_tags.media_type_readable(x) for x in distribution],
        "datasets": [
            {
                "label": status,
                "data": [
                    distribution[media_type][status] for media_type in distribution
                ],
                "background_color": get_status_color(status),
                "total": sum(
                    distribution[media_type][status] for media_type in distribution
                ),
            }
            for status in status_order
        ],
        "total_completed": total_completed,
    }


def get_status_pie_chart_data(status_distribution):
    """Get status distribution as a pie chart."""
    # Format for Chart.js pie chart
    chart_data = {
        "labels": [],
        "datasets": [
            {
                "data": [],
                "backgroundColor": [],
            },
        ],
    }

    # Process each status dataset
    for dataset in status_distribution["datasets"]:
        status_label = dataset["label"]
        status_count = dataset["total"]
        status_color = dataset["background_color"]

        # Only include statuses with counts > 0
        if status_count > 0:
            chart_data["labels"].append(status_label)
            chart_data["datasets"][0]["data"].append(status_count)
            chart_data["datasets"][0]["backgroundColor"].append(status_color)

    return chart_data


def get_score_distribution(user_media):
    """Get score distribution for each media type within date range."""
    distribution = {}
    total_scored = 0
    total_score_sum = 0
    all_scored_media = []
    score_range = range(11)

    for media_type, media_list in user_media.items():
        score_counts = dict.fromkeys(score_range, 0)
        scored_media = media_list.exclude(score__isnull=True).select_related("item")

        for media in scored_media:
            all_scored_media.append(media)
            score_counts[int(media.score)] += 1
            total_scored += 1
            total_score_sum += media.score

        distribution[media_type] = score_counts

    average_score = (
        round(total_score_sum / total_scored, 2) if total_scored > 0 else None
    )

    top_rated_media = _select_top_rated(all_scored_media, 14)
    top_rated_media = _annotate_top_rated_media(top_rated_media)

    return {
        "labels": [str(score) for score in score_range],
        "datasets": [
            {
                "label": app_tags.media_type_readable(media_type),
                "data": [distribution[media_type][score] for score in score_range],
                "background_color": config.get_stats_color(media_type),
            }
            for media_type in distribution
        ],
        "average_score": average_score,
        "total_scored": total_scored,
    }, top_rated_media


def _select_top_rated(all_scored_media, count):
    counter = itertools.count()
    heap = []
    for media in all_scored_media:
        entry = (float(media.score), next(counter), media)
        if len(heap) < count:
            heapq.heappush(heap, entry)
        else:
            heapq.heappushpop(heap, entry)
    return [m for _, _, m in sorted(heap, key=lambda x: (-x[0], x[1]))]


def _annotate_top_rated_media(top_rated_media):
    """Apply prefetch_related and annotate max_progress for top rated media."""
    if not top_rated_media:
        return top_rated_media

    media_by_type = defaultdict(list)
    for media in top_rated_media:
        media_by_type[media.item.media_type].append(media)

    prefetched = {}
    media_manager = MediaManager()
    for media_type, media_list in media_by_type.items():
        model = apps.get_model(app_label="app", model_name=media_type)
        media_ids = [m.id for m in media_list]
        queryset = model.objects.filter(id__in=media_ids)
        queryset = media_manager._apply_prefetch_related(queryset, media_type)
        media_manager.annotate_max_progress(queryset, media_type)
        prefetched.update({(media_type, m.id): m for m in queryset})

    return [prefetched.get((m.item.media_type, m.id), m) for m in top_rated_media]


def get_status_color(status):
    """Get the color for the status of the media."""
    try:
        return config.get_status_stats_color(status)
    except KeyError:
        return "rgba(201, 203, 207)"


def get_timeline(user_media):
    """Build a timeline of media consumption organized by month-year."""
    timeline = defaultdict(list)

    querysets = (qs for mt, qs in user_media.items() if mt != MediaTypes.TV.value)
    for media in itertools.chain.from_iterable(querysets):
        for year, month in _get_media_months(media):
            timeline[(year, month)].append(media)

    sorted_keys = sorted(timeline, reverse=True)
    return {
        f"{calendar.month_name[month]} {year}": sorted(
            timeline[(year, month)],
            key=time_line_sort_key,
            reverse=True,
        )
        for year, month in sorted_keys
    }


def _get_media_months(media):
    if media.start_date and media.end_date:
        start = timezone.localdate(media.start_date)
        end = timezone.localdate(media.end_date)
        current = start
        while current <= end:
            yield current.year, current.month
            current = (current + relativedelta(months=1)).replace(day=1)
    elif media.start_date:
        d = timezone.localdate(media.start_date)
        yield d.year, d.month
    elif media.end_date:
        d = timezone.localdate(media.end_date)
        yield d.year, d.month


def time_line_sort_key(media):
    """Sort media items in the timeline."""
    if media.end_date is not None:
        return timezone.localdate(media.end_date)
    return timezone.localdate(media.start_date)


def get_activity_data(user, start_date, end_date):
    """Get daily activity counts for the last year."""
    if end_date is None:
        end_date = timezone.localtime()

    start_date_aligned = get_aligned_monday(start_date)
    combined_data = get_filtered_historical_data(start_date_aligned, end_date, user)

    if start_date is None:
        dates = [item["date"] for item in combined_data]
        start_date = datetime.datetime.combine(
            min(dates) if dates else timezone.localdate(),
            datetime.time.min,
        )
        start_date_aligned = get_aligned_monday(start_date)

    date_counts = {}
    for item in combined_data:
        date = item["date"]
        date_counts[date] = date_counts.get(date, 0) + item["count"]

    date_range = [
        start_date_aligned.date() + datetime.timedelta(days=x)
        for x in range((end_date.date() - start_date_aligned.date()).days + 1)
    ]

    most_active_day, day_percentage = calculate_day_of_week_stats(
        date_counts,
        start_date.date(),
    )
    current_streak, longest_streak = calculate_streaks(
        date_counts,
        end_date.date(),
    )

    activity_data = [
        {
            "date": current_date.strftime("%Y-%m-%d"),
            "count": date_counts.get(current_date, 0),
            "level": get_level(date_counts.get(current_date, 0)),
        }
        for current_date in date_range
    ]

    calendar_weeks = [activity_data[i : i + 7] for i in range(0, len(activity_data), 7)]

    return {
        "calendar_weeks": calendar_weeks,
        "months": _generate_month_labels(date_range),
        "stats": {
            "most_active_day": most_active_day,
            "most_active_day_percentage": day_percentage,
            "current_streak": current_streak,
            "longest_streak": longest_streak,
        },
    }


def _generate_month_labels(date_range):
    mondays = [d for d in date_range if d.weekday() == 0]
    if not mondays:
        return []

    result = []
    for label, group in itertools.groupby(mondays, key=lambda d: d.strftime("%b")):
        count = sum(1 for _ in group)
        result.append((label if count > 1 else "", count))

    if result and result[-1][1] <= 1:
        result.pop()
    return result


def get_aligned_monday(datetime_obj):
    """Get the Monday of the week containing the given date."""
    if datetime_obj is None:
        return None

    days_to_subtract = datetime_obj.weekday()  # 0=Monday, 6=Sunday
    return datetime_obj - datetime.timedelta(days=days_to_subtract)


def get_level(count):
    """Calculate intensity level (0-4) based on count."""
    thresholds = [0, 3, 6, 9]
    for i, threshold in enumerate(thresholds):
        if count <= threshold:
            return i
    return 4


def get_filtered_historical_data(start_date, end_date, user):
    """Return [{"date": datetime.date, "count": int}]."""
    historical_models = BasicMedia.objects.get_historical_models()
    local_tz = timezone.get_current_timezone()

    day_buckets = defaultdict(int)

    for model_name in historical_models:
        model = apps.get_model("app", model_name)

        qs = model.objects.filter(history_user_id=user)

        if start_date:
            qs = qs.filter(history_date__gte=start_date)
        if end_date:
            qs = qs.filter(history_date__lte=end_date)

        # We only need the timestamp, stream results to keep memory usage flat
        for ts in qs.values_list("history_date", flat=True).iterator(chunk_size=2_000):
            aware_ts = timezone.localtime(ts, local_tz)

            day_buckets[aware_ts.date()] += 1

    combined_data = [
        {"date": day, "count": count} for day, count in day_buckets.items()
    ]

    logger.info("%s - built historical data (%s rows)", user, len(combined_data))
    return combined_data


def calculate_day_of_week_stats(date_counts, start_date):
    """Calculate the most active day of the week based on activity frequency.

    Returns the day name and its percentage of total activity.
    """
    # Initialize counters for each day of the week
    day_counts = defaultdict(int)
    total_active_days = 0

    # Count occurrences of each day of the week where activity happened
    for date in date_counts:
        if date < start_date:
            continue
        if date_counts[date] > 0:
            day_name = date.strftime("%A")  # Get full day name
            day_counts[day_name] += 1
            total_active_days += 1

    if not total_active_days:
        return None, 0

    # Find the most active day
    most_active_day = max(day_counts.items(), key=lambda x: x[1])
    percentage = (most_active_day[1] / total_active_days) * 100

    return most_active_day[0], round(percentage)


def calculate_streaks(date_counts, end_date):
    """Calculate current and longest activity streaks."""
    active_dates = sorted(
        [date for date, count in date_counts.items() if count > 0],
        reverse=True,
    )

    if not active_dates:
        return 0, 0

    streaks = []
    streak_count = 1

    for i in range(1, len(active_dates)):
        if (active_dates[i - 1] - active_dates[i]).days == 1:
            streak_count += 1
        else:
            streaks.append(streak_count)
            streak_count = 1
    streaks.append(streak_count)

    longest_streak = max(streaks)
    current_streak = streaks[0] if active_dates[0] == end_date else 0
    return current_streak, longest_streak
