from app.models import Sources


def extract_status_code(error):
    """Return status code from an int or HTTPError."""
    if isinstance(error, int):
        return error
    return error.response.status_code


def extract_log_text(error, details):
    """Return text suitable for logger output."""
    if isinstance(error, int):
        return details or ""
    return error.response.text


def format_provider_label(provider):
    """Map a Sources value to its display label; fallback to titlecase."""
    try:
        return Sources(provider).label
    except ValueError:
        return provider.title()
