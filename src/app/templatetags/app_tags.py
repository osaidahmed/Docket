"""Project template tags & filters.

Implementation lives in `_app_tags_format`, `_app_tags_media`, and
`_app_tags_utility`. This module imports each and registers their public
functions with a single `template.Library()` so templates can keep
`{% load app_tags %}` unchanged. The tag/filter functions are also
re-exported at module level so existing test code that calls them as
`app_tags.media_url(...)` keeps working.
"""

from django import template

from app.templatetags import (
    _app_tags_format,
    _app_tags_media,
    _app_tags_utility,
)
from app.templatetags._app_tags_format import (  # noqa: F401
    date_format,
    datetime_format,
    get_static_file_mtime,
    iso_date_format,
    natural_day,
    no_underscore,
    slug,
    time_format,
    timestamp_to_time,
)
from app.templatetags._app_tags_media import (  # noqa: F401
    component_id,
    default_source,
    get_search_media_types,
    get_sidebar_media_types,
    has_caught_up,
    has_repeat,
    icon,
    long_unit,
    media_color,
    media_past_verb,
    media_status_readable,
    media_type_readable,
    media_type_readable_plural,
    media_url,
    media_verb_ing,
    media_view_url,
    repeat_label,
    short_unit,
    show_media_score,
    source_readable,
    sources,
    status_background_color,
    status_color,
    unicode_icon,
)
from app.templatetags._app_tags_utility import (  # noqa: F401
    csv_contains,
    get_item,
    get_pagination_range,
    get_range,
    is_list,
    startswith,
    str_equals,
)

register = template.Library()


for _module in (_app_tags_format, _app_tags_media, _app_tags_utility):
    for _name in _module._TAGS:
        register.simple_tag(getattr(_module, _name), name=_name)
    for _name in _module._FILTERS:
        register.filter(_name, getattr(_module, _name))
