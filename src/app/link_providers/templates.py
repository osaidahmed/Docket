from urllib.parse import quote


def fill_template(template, item):
    """Substitute {title}, {english_title}, {year} in a URL template.

    All values are URL-encoded. Missing fields substitute empty strings.
    Returns an empty string if the template is falsy.
    """
    if not template:
        return ""
    title = quote(getattr(item, "title", "") or "", safe="")
    english_title = quote(getattr(item, "english_title", "") or "", safe="")
    year = _extract_year(item)
    return (
        template.replace("{title}", title)
        .replace("{english_title}", english_title)
        .replace("{year}", year)
    )


def _extract_year(item):
    for attr in ("release_date", "start_date", "premiered"):
        value = getattr(item, attr, None)
        if value and hasattr(value, "year"):
            return str(value.year)
    return ""
