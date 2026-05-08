import contextvars

_disable_triggers: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "yamtrack_disable_calendar_triggers",
    default=False,
)


class CalendarTriggerMixin:
    """Mixin exposing a context-aware flag suppressing calendar refresh side-effects."""

    @property
    def _disable_calendar_triggers(self):
        return _disable_triggers.get()


def disable_fetch_releases():
    """Return a context manager that suppresses Item calendar triggers."""
    return _DisableCalendarTriggers()


class _DisableCalendarTriggers:
    """Context manager toggling the calendar-trigger flag for the current context."""

    def __enter__(self):
        self.token = _disable_triggers.set(True)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        _disable_triggers.reset(self.token)
