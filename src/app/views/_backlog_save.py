"""Backlog-save side-effect helpers."""

import logging

from app.services import backlog

logger = logging.getLogger(__name__)


def commit_backlog_form(request, media, media_type, form, pre_save):
    """Save the backlog form and apply pin/archive/rewatch side effects."""
    from app.views.actions import (  # noqa: PLC0415
        _check_rewatch_cancelled,
        _update_pin_order,
    )

    old_status, old_is_rewatch, old_is_pinned = pre_save
    form.save()
    if media.status != old_status:
        backlog.invalidate_archive_count(request.user)
    is_pinned_submitted = "is_pinned" in request.POST
    _update_pin_order(request.user, media, old_is_pinned, is_pinned_submitted)
    logger.info("%s updated from backlog.", form.instance)
    rewatch_cancelled = _check_rewatch_cancelled(
        request.user,
        media,
        media_type,
        old_is_rewatch,
    )
    if rewatch_cancelled:
        media.delete()
    state_changed = (
        media.status != old_status
        or media.is_rewatch != old_is_rewatch
        or is_pinned_submitted != old_is_pinned
    )
    return rewatch_cancelled, state_changed
