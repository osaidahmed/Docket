"""Contains views for importing and exporting media data from various sources."""

import json
import logging
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_not_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

import users
from integrations import exports, tasks
from integrations.imports import anilist, helpers, simkl, trakt
from integrations.webhooks import emby, jellyfin, plex

logger = logging.getLogger(__name__)


def _initiate_oauth(request, redirect_name, auth_url, client_id):
    """Build OAuth state, store in session, and redirect to provider."""
    redirect_uri = request.build_absolute_uri(reverse(redirect_name))
    state = {
        "mode": request.POST["mode"],
        "frequency": request.POST["frequency"],
        "time": request.POST["time"],
    }
    state_token = secrets.token_urlsafe(32)
    request.session[state_token] = state
    return redirect(
        f"{auth_url}?client_id={client_id}&redirect_uri={redirect_uri}"
        f"&response_type=code&state={state_token}",
    )


def _handle_oauth_callback(
    request, enc_token, username, source, task_fn, **task_kwargs
):
    """Handle OAuth callback: dispatch once or create schedule."""
    state_token = request.GET["state"]
    frequency = request.session[state_token]["frequency"]
    mode = request.session[state_token]["mode"]
    import_time = request.session[state_token]["time"]

    if frequency == "once":
        task_fn.delay(
            user_id=request.user.id,
            mode=mode,
            token=enc_token,
            username=username,
            **task_kwargs,
        )
        messages.info(
            request, f"The task to import media from {source} has been queued."
        )
    else:
        helpers.create_import_schedule(
            username=username,
            request=request,
            mode=mode,
            frequency=frequency,
            import_time=import_time,
            source=source,
            token=enc_token,
        )
    return redirect("import_data")


def _handle_public_import(request, source, task_fn, error_label=None):
    """Handle public import by username: validate, dispatch or schedule."""
    username = request.POST.get("user")
    label = error_label or f"{source} username"
    if not username:
        messages.error(request, f"{label} is required.")
        return redirect("import_data")

    mode = request.POST["mode"]
    frequency = request.POST["frequency"]

    if frequency == "once":
        task_fn.delay(username=username, user_id=request.user.id, mode=mode)
        messages.info(
            request, f"The task to import media from {source} has been queued."
        )
    else:
        import_time = request.POST["time"]
        helpers.create_import_schedule(
            username, request, mode, frequency, import_time, source
        )
    return redirect("import_data")


def _handle_file_import(request, file_key, source_label, task_fn):
    """Handle file-based import: validate file, dispatch task."""
    file = request.FILES.get(file_key)
    if not file:
        messages.error(request, f"{source_label} file is required.")
        return redirect("import_data")

    mode = request.POST["mode"]
    task_fn.delay(file=request.FILES[file_key], user_id=request.user.id, mode=mode)
    messages.info(
        request, f"The task to import media from {source_label} file has been queued."
    )
    return redirect("import_data")


def _handle_webhook(request, token, service_name, processor_class, payload_key=None):
    """Validate webhook token, parse payload, and process."""
    try:
        user = users.models.User.objects.get(token=token)
    except ObjectDoesNotExist:
        logger.warning(
            "Could not process %s webhook: Invalid token: %s", service_name, token
        )
        return HttpResponse(status=401)

    request.user = user
    data = request.body if payload_key is None else request.POST.get(payload_key)
    if not data:
        logger.warning("Missing payload in %s webhook request", service_name)
        return HttpResponse("Missing payload", status=400)

    payload = json.loads(data)
    processor_class().process_payload(payload, user)
    return HttpResponse(status=200)


@require_POST
def trakt_oauth(request):
    """Initiate Trakt OAuth2 authorization flow."""
    return _initiate_oauth(
        request,
        "import_trakt_private",
        "https://trakt.tv/oauth/authorize",
        settings.TRAKT_API,
    )


@require_GET
def import_trakt_private(request):
    """Handle Trakt OAuth2 callback and schedule private import."""
    oauth = trakt.handle_oauth_callback(request)
    enc_token = helpers.encrypt(oauth["refresh_token"])
    return _handle_oauth_callback(
        request, enc_token, oauth["username"], "Trakt", tasks.import_trakt
    )


@require_POST
def import_trakt_public(request):
    """Import Trakt data using public username."""
    return _handle_public_import(request, "Trakt", tasks.import_trakt)


@require_POST
def simkl_oauth(request):
    """Initiate SIMKL OAuth2 authorization flow."""
    return _initiate_oauth(
        request,
        "import_simkl_private",
        "https://simkl.com/oauth/authorize",
        settings.SIMKL_ID,
    )


@require_GET
def import_simkl_private(request):
    """Handle SIMKL OAuth2 callback."""
    oauth = simkl.get_token(request)
    enc_token = helpers.encrypt(oauth["access_token"])
    return _handle_oauth_callback(
        request, enc_token, oauth["username"], "SIMKL", tasks.import_simkl
    )


@require_POST
def import_mal(request):
    """Import anime and manga data from MyAnimeList."""
    return _handle_public_import(request, "MyAnimeList", tasks.import_mal)


@require_POST
def anilist_oauth(request):
    """Initiate AniList OAuth flow."""
    return _initiate_oauth(
        request,
        "import_anilist_private",
        "https://anilist.co/api/v2/oauth/authorize",
        settings.ANILIST_ID,
    )


@require_GET
def import_anilist_private(request):
    """Handle AniList OAuth2 callback."""
    oauth = anilist.get_token(request)
    enc_token = helpers.encrypt(oauth["access_token"])
    username = oauth["username"]

    if not username:
        messages.error(request, "AniList username is required.")
        return redirect("import_data")

    return _handle_oauth_callback(
        request, enc_token, username, "AniList", tasks.import_anilist
    )


@require_POST
def import_anilist_public(request):
    """Import anime and manga data from AniList."""
    return _handle_public_import(request, "AniList", tasks.import_anilist)


@require_POST
def import_kitsu(request):
    """Import anime and manga data from Kitsu by user ID."""
    return _handle_public_import(
        request, "Kitsu", tasks.import_kitsu, error_label="Kitsu user ID"
    )


@require_POST
def import_yamtrack(request):
    """Import media from Yamtrack CSV."""
    return _handle_file_import(
        request, "yamtrack_csv", "Yamtrack CSV", tasks.import_yamtrack
    )


@require_POST
def import_hltb(request):
    """Import game data from HowLongToBeat."""
    return _handle_file_import(
        request, "hltb_csv", "HowLongToBeat CSV", tasks.import_hltb
    )


@require_POST
def import_steam(request):
    """Import game data from Steam."""
    return _handle_public_import(
        request, "Steam", tasks.import_steam, error_label="Steam ID"
    )


def import_imdb(request):
    """Import data from IMDb."""
    return _handle_file_import(request, "imdb_csv", "IMDb CSV", tasks.import_imdb)


@require_POST
def import_goodreads(request):
    """Import books data from Goodreads CSV."""
    return _handle_file_import(
        request, "goodreads_csv", "Goodreads CSV", tasks.import_goodreads
    )


@require_GET
def export_csv(request):
    """Export all media data to a CSV file."""
    now = timezone.localtime()
    response = StreamingHttpResponse(
        streaming_content=exports.generate_rows(request.user),
        content_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="yamtrack_{now}.csv"'},
    )
    logger.info("User %s started CSV export", request.user.username)
    return response


@login_not_required
@csrf_exempt
@require_POST
def jellyfin_webhook(request, token):
    """Handle Jellyfin webhook notifications."""
    return _handle_webhook(
        request, token, "Jellyfin", jellyfin.JellyfinWebhookProcessor
    )


@login_not_required
@csrf_exempt
@require_POST
def plex_webhook(request, token):
    """Handle Plex webhook notifications."""
    return _handle_webhook(request, token, "Plex", plex.PlexWebhookProcessor, "payload")


@login_not_required
@csrf_exempt
@require_POST
def emby_webhook(request, token):
    """Handle Emby webhook notifications."""
    return _handle_webhook(request, token, "Emby", emby.EmbyWebhookProcessor, "data")
