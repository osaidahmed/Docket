import json
import logging

import requests
from django.conf import settings
from django.urls import reverse
from django_celery_beat.models import PeriodicTask

import app.providers.services
from app.providers import services
from integrations.imports import helpers
from integrations.imports.helpers import MediaImportError

logger = logging.getLogger(__name__)

TRAKT_API_BASE_URL = "https://api.trakt.tv"


def handle_oauth_callback(request):
    """View for getting the Trakt OAuth2 token."""
    code = request.GET["code"]

    url = f"{TRAKT_API_BASE_URL}/oauth/token"

    params = {
        "client_id": settings.TRAKT_API,
        "client_secret": settings.TRAKT_API_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": request.build_absolute_uri(reverse("import_trakt_private")),
    }

    try:
        token_response = app.providers.services.api_request(
            "TRAKT",
            "POST",
            url,
            params=params,
        )
    except services.ProviderAPIError as error:
        if error.status_code == requests.codes.unauthorized:
            msg = "Invalid Trakt secret key."
            raise MediaImportError(msg) from error
        raise

    return {
        "refresh_token": token_response["refresh_token"],
        "username": get_username_from_oauth(token_response["access_token"]),
    }


def get_username_from_oauth(access_token):
    """View for getting the Trakt OAuth2 username."""
    url = f"{TRAKT_API_BASE_URL}/users/me"

    headers = {
        "Content-Type": "application/json",
        "trakt-api-version": "2",
        "trakt-api-key": settings.TRAKT_API,
        "Authorization": f"Bearer {access_token}",
    }

    try:
        request = app.providers.services.api_request(
            "TRAKT",
            "GET",
            url,
            headers=headers,
        )
    except services.ProviderAPIError as error:
        if error.status_code == requests.codes.unauthorized:
            msg = "Invalid Trakt secret key."
            raise MediaImportError(msg) from error
        raise

    return request["username"]


def get_access_token(encrypted_refresh_token):
    """Get access token from encrypted refresh token."""
    url = f"{TRAKT_API_BASE_URL}/oauth/token"

    decrypted_token = helpers.decrypt(encrypted_refresh_token)

    params = {
        "client_id": settings.TRAKT_API,
        "client_secret": settings.TRAKT_API_SECRET,
        "refresh_token": decrypted_token,
        "grant_type": "refresh_token",
        "redirect_uri": f"{settings.BASE_URL}/import/trakt/private",
    }

    try:
        request = app.providers.services.api_request(
            "TRAKT",
            "POST",
            url,
            params=params,
        )
    except services.ProviderAPIError as error:
        if error.status_code == requests.codes.unauthorized:
            msg = "Invalid Trakt secret key."
            raise MediaImportError(msg) from error
        raise

    # refresh tokens are one time use only
    update_refresh_token(encrypted_refresh_token, request["refresh_token"])
    return request["access_token"]


def update_refresh_token(old_token, new_token):
    """Update the refresh token in periodic tasks."""
    periodic_task = PeriodicTask.objects.filter(
        task="Import from Trakt",
        kwargs__contains=f'"token": "{old_token}"',
    ).first()

    if periodic_task:
        task_kwargs = json.loads(periodic_task.kwargs)
        task_kwargs["token"] = helpers.encrypt(new_token)
        periodic_task.kwargs = json.dumps(task_kwargs)
        periodic_task.save()
