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


_OAUTH_CONFIGS = {
    "trakt": {
        "auth_url": "https://trakt.tv/oauth/authorize",
        "client_id_setting": "TRAKT_API",
        "callback_url_name": "import_trakt_private",
        "token_module": trakt,
        "token_attr": "handle_oauth_callback",
        "task_module_attr": "import_trakt",
        "token_field": "refresh_token",
        "source_label": "Trakt",
        "requires_username": False,
    },
    "simkl": {
        "auth_url": "https://simkl.com/oauth/authorize",
        "client_id_setting": "SIMKL_ID",
        "callback_url_name": "import_simkl_private",
        "token_module": simkl,
        "token_attr": "get_token",
        "task_module_attr": "import_simkl",
        "token_field": "access_token",
        "source_label": "SIMKL",
        "requires_username": False,
    },
    "anilist": {
        "auth_url": "https://anilist.co/api/v2/oauth/authorize",
        "client_id_setting": "ANILIST_ID",
        "callback_url_name": "import_anilist_private",
        "token_module": anilist,
        "token_attr": "get_token",
        "task_module_attr": "import_anilist",
        "token_field": "access_token",
        "source_label": "AniList",
        "requires_username": True,
    },
}


def _make_oauth_view(provider_key):
    """Build an OAuth-initiate view bound to the given provider config."""
    cfg = _OAUTH_CONFIGS[provider_key]

    @require_POST
    def oauth_view(request):
        return _initiate_oauth(
            request,
            cfg["callback_url_name"],
            cfg["auth_url"],
            getattr(settings, cfg["client_id_setting"]),
        )

    oauth_view.__name__ = f"{provider_key}_oauth"
    oauth_view.__doc__ = f"Initiate {cfg['source_label']} OAuth2 authorization flow."
    return oauth_view


def _make_import_private_view(provider_key):
    """Build an OAuth-callback view bound to the given provider config."""
    cfg = _OAUTH_CONFIGS[provider_key]

    @require_GET
    def import_view(request):
        # Resolve token_fn and task_fn at call time so unittest.mock.patch
        # against the imported module attributes is honoured.
        token_fn = getattr(cfg["token_module"], cfg["token_attr"])
        task_fn = getattr(tasks, cfg["task_module_attr"])
        oauth = token_fn(request)
        enc_token = helpers.encrypt(oauth[cfg["token_field"]])
        username = oauth.get("username")
        if cfg["requires_username"] and not username:
            messages.error(request, f"{cfg['source_label']} username is required.")
            return redirect("import_data")
        return _handle_oauth_callback(
            request,
            enc_token,
            username,
            cfg["source_label"],
            task_fn,
        )

    import_view.__name__ = f"import_{provider_key}_private"
    import_view.__doc__ = f"Handle {cfg['source_label']} OAuth2 callback."
    return import_view


trakt_oauth = _make_oauth_view("trakt")
import_trakt_private = _make_import_private_view("trakt")


@require_POST
def import_trakt_public(request):
    """Import Trakt data using public username."""
    return _handle_public_import(request, "Trakt", tasks.import_trakt)


simkl_oauth = _make_oauth_view("simkl")
import_simkl_private = _make_import_private_view("simkl")


@require_POST
def import_mal(request):
    """Import anime and manga data from MyAnimeList."""
    return _handle_public_import(request, "MyAnimeList", tasks.import_mal)


anilist_oauth = _make_oauth_view("anilist")
import_anilist_private = _make_import_private_view("anilist")


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
def import_docket(request):
    """Import media from Docket CSV."""
    return _handle_file_import(request, "docket_csv", "Docket CSV", tasks.import_docket)


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
        headers={"Content-Disposition": f'attachment; filename="docket_{now}.csv"'},
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
