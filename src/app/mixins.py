from django.apps import apps


class CalendarTriggerMixin:
    """Mixin that exposes a class flag suppressing calendar refresh side-effects."""

    _disable_calendar_triggers = False


def disable_fetch_releases():
    """Return a context manager that suppresses Item calendar triggers."""
    return _DisableCalendarTriggers()


class _DisableCalendarTriggers:
    """Context manager toggling Item._disable_calendar_triggers."""

    def __enter__(self):
        item_cls = apps.get_model("app", "Item")
        self.original_value = item_cls._disable_calendar_triggers
        item_cls._disable_calendar_triggers = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        item_cls = apps.get_model("app", "Item")
        item_cls._disable_calendar_triggers = self.original_value
