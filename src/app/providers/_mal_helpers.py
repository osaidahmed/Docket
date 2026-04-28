"""Pure helpers for the MAL provider, kept separate to respect the file's fn-budget."""

from datetime import datetime


def parse_jst_start_date(start_date, tz):
    """Parse a MAL start_date in JST, falling back to year-month-only format."""
    try:
        return datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=tz)
    except ValueError:
        return datetime.strptime(start_date, "%Y-%m").replace(tzinfo=tz)
