import logging
import sys

from github import Github
from requests_oauthlib import OAuth2Session

from django.conf import settings
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods

from apps.base.utils import create_model_object
from apps.profiles.models import GithubProfile, EmailAddress

logger = logging.getLogger(__name__)

try:
    GITHUB_CLIENT_ID = settings.GITHUB_CLIENT_ID
    GITHUB_CLIENT_SECRET = settings.GITHUB_CLIENT_SECRET
    GITHUB_REDIRECT_URI = settings.GITHUB_REDIRECT_URI
    GITHUB_OAUTH_SCOPES = settings.GITHUB_OAUTH_SCOPES
except AttributeError:
    tb = sys.exc_info()[2]
    raise Exception(
        "One of GitHub's OAuth settings was missing. "
        "Check traceback for more info."
    ).with_traceback(tb)

GITHUB_AUTHORIZATION_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"


@require_http_methods(["GET"])
def connect_github(request):
    token = request.GET.get("token") or ""
    response = HttpResponseRedirect('/auth/github')
    response['Authorization'] = f"JWT {token}"
    return response

@require_http_methods(["GET"])
def oauth_github(request):
    if request.user.is_authenticated:
        github = OAuth2Session(
            client_id=GITHUB_CLIENT_ID,
            redirect_uri=GITHUB_REDIRECT_URI,
            scope=GITHUB_OAUTH_SCOPES,
        )
        authorization_url, state = github.authorization_url(
            GITHUB_AUTHORIZATION_URL
        )
        request.session["oauth_github_state"] = state
        return redirect(authorization_url)
    else:
        return JsonResponse(
            {"success": False, "errors": ["User not authenticated"]}
        )


@require_http_methods(["GET"])
def oauth_github_callback(request):
    if request.user.is_anonymous:
        return JsonResponse(
            {"success": False, "errors": ["User not authenticated"]}
        )

    if not request.GET.get("code"):
        if request.GET.get("error"):
            # See: https://developer.github.com/apps/managing-oauth-apps/troubleshooting-oauth-app-access-token-request-errors/  # noqa
            error = {
                "error": request.GET.get("error"),
                "error_description": request.GET.get("error_description"),
                "error_uri": request.GET.get("error_uri"),
            }
            logger.error(f"Github OAuth error\n{error}")
            return JsonResponse({"success": False, "errors": [error]})
        return JsonResponse(
            {"success": False, "errors": ["No code found in parameters"]}
        )

    try:
        code = request.GET.get("code")
        oauth = OAuth2Session(
            client_id=GITHUB_CLIENT_ID,
            state=request.session.get("oauth_github_state"),
        )
        access_token = oauth.fetch_token(
            GITHUB_TOKEN_URL, client_secret=GITHUB_CLIENT_SECRET, code=code
        ).get("access_token")

        # Load interface to v3 API to grab uid, username and email
        g = Github(access_token)
        github_details = g.get_user()

        # TODO: Add UID to model creation kwargs
        profile = create_model_object(
            GithubProfile,
            access_token=access_token,
            username=github_details.login,
            user=request.user,
        )

        for email_dict in github_details.get_emails():
            # TODO: Add primary and verified parameters
            create_model_object(
                EmailAddress, email=email_dict.get("email"), profile=profile
            )

    except Exception:
        logger.error("Error while processing Github OAuth", exc_info=True)
        return JsonResponse({"success": False})

    return JsonResponse({"success": True})
