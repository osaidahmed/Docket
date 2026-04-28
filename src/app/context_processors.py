# https://docs.djangoproject.com/en/stable/ref/templates/api/#writing-your-own-context-processors

from django.conf import settings

from app.models import MediaTypes, Sources, Status


def template_constants(request):  # noqa: ARG001
    """Export project-wide constants and media enums to all templates."""
    return {
        "REGISTRATION": settings.REGISTRATION,
        "REDIRECT_LOGIN_TO_SSO": settings.REDIRECT_LOGIN_TO_SSO,
        "IMG_NONE": settings.IMG_NONE,
        "TRACK_TIME": settings.TRACK_TIME,
        "MediaTypes": MediaTypes,
        "Sources": Sources,
        "Status": Status,
    }
