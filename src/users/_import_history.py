from django_celery_beat.models import PeriodicTask
from django_celery_results.models import TaskResult

from users import helpers

_IMPORT_TASKS = {
    "trakt": "Import from Trakt",
    "simkl": "Import from SIMKL",
    "myanimelist": "Import from MyAnimeList",
    "anilist": "Import from AniList",
    "kitsu": "Import from Kitsu",
    "docket": "Import from Docket",
    "hltb": "Import from HowLongToBeat",
    "steam": "Import from Steam",
    "imdb": "Import from IMDB",
    "goodreads": "Import from GoodReads",
}
_TASK_TO_SOURCE = {v: k for k, v in _IMPORT_TASKS.items()}


def collect_task_results(user):
    """Build the recent-import history list for the given user."""
    task_results = TaskResult.objects.filter(
        task_kwargs__regex=rf"['\"]user_id['\"]\s*:\s*{user.id}\b",
        task_name__in=_IMPORT_TASKS.values(),
    ).order_by("-date_done")

    results = []
    for task in task_results:
        processed_task = helpers.process_task_result(task)
        results.append(
            {
                "task": processed_task,
                "source": _TASK_TO_SOURCE[task.task_name],
                "date": task.date_done,
                "status": task.status,
                "summary": processed_task.summary,
                "errors": processed_task.errors,
            },
        )
    return results


def collect_periodic_tasks(user):
    """Build the active import-schedule list for the given user."""
    periodic_tasks = PeriodicTask.objects.filter(
        task__in=_IMPORT_TASKS.values(),
        kwargs__regex=rf"['\"]user_id['\"]\s*:\s*{user.id}\b",
        enabled=True,
    ).select_related("crontab")

    schedules = []
    for periodic_task in periodic_tasks:
        schedule_info = helpers.get_next_run_info(periodic_task)
        if not schedule_info:
            continue
        username = ""
        if " for " in periodic_task.name:
            username = periodic_task.name.split(" for ")[1].split(" at ")[0]
        schedules.append(
            {
                "task": periodic_task,
                "source": _TASK_TO_SOURCE.get(periodic_task.task, "unknown"),
                "username": username,
                "last_run": periodic_task.last_run_at,
                "next_run": schedule_info["next_run"],
                "schedule": schedule_info["frequency"],
                "mode": schedule_info["mode"],
            },
        )
    return schedules
