"""Generic template-tag utilities (predicates, ranges, pagination) for `app_tags`."""


def is_list(arg1):
    """Return True if the object is a list."""
    return isinstance(arg1, list)


def str_equals(value, arg):
    """Return True if the string value is equal to the argument."""
    return str(value) == str(arg)


def startswith(value, arg):
    """Return True if the string value starts with the argument."""
    return str(value).startswith(str(arg))


def get_range(value):
    """Return a range from 1 to the given value."""
    return range(1, int(value) + 1)


def get_pagination_range(current_page, total_pages, window, total_exact=True):  # noqa: FBT002
    """Return a list of page numbers (and None for ellipses) to display."""
    # Django templates resolve missing dict keys to "" — treat as True
    if total_exact == "":
        total_exact = True

    if not total_exact:
        return _estimate_pagination_range(current_page, window)

    if total_pages <= 5 + window * 2:
        return list(range(1, total_pages + 1))

    second_page = 2
    left_boundary = max(second_page, current_page - window)
    right_boundary = min(total_pages - 1, current_page + window)

    result = [1]
    if left_boundary > second_page:
        result.append(None)
    result.extend(range(left_boundary, right_boundary + 1))
    if right_boundary < total_pages - 1:
        result.append(None)
    if total_pages not in result:
        result.append(total_pages)
    return result


def _estimate_pagination_range(current_page, window):
    """Pagination range when total page count is an estimate (always trailing …)."""
    second_page = 2
    left_boundary = max(second_page, current_page - window)
    right_boundary = current_page + window
    result = [1]
    if left_boundary > second_page:
        result.append(None)
    result.extend(range(left_boundary, right_boundary + 1))
    result.append(None)
    return result


def get_item(dictionary, key):
    """Look up a key in a dictionary."""
    if isinstance(dictionary, dict):
        return dictionary.get(key, "")
    return ""


def csv_contains(csv_string, value):
    """Check if a value is in a comma-separated string."""
    if not csv_string:
        return False
    return str(value) in str(csv_string).split(",")


_TAGS = ("get_pagination_range",)
_FILTERS = (
    "is_list",
    "str_equals",
    "startswith",
    "get_range",
    "get_item",
    "csv_contains",
)
