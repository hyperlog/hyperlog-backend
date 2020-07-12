import logging
import sys

from github import Github
from requests_oauthlib import OAuth2Session

from django.conf import settings
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from graphql_jwt.decorators import jwt_cookie
from graphql_jwt.exceptions import JSONWebTokenError, JSONWebTokenExpired
from graphql_jwt.utils import get_payload as jwt_get_payload

from apps.base.utils import create_model_object
from apps.profiles.models import GithubProfile, EmailAddress
from apps.profiles.utils import (
    create_profile_object,
    render_github_oauth_fail,
    render_github_oauth_success,
)

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
    if request.GET.get("token"):
        token = request.GET.get("token")
        # Validate token and return appropriate error message
        try:
            jwt_get_payload(token)
        except JSONWebTokenExpired:
            return render_github_oauth_fail(request, errors=["Expired token"])
        except JSONWebTokenError:
            return render_github_oauth_fail(request, errors=["Invalid token"])
    else:
        # If token parameter was not present
        return render_github_oauth_fail(request, errors=["Missing token"])

    response = HttpResponseRedirect(reverse("profiles:oauth_github"))
    response.set_cookie("JWT", token, max_age=30)
    return response


@require_http_methods(["GET"])
@jwt_cookie
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
        return render_github_oauth_fail(
            request, errors=["User not authenticated"]
        )


@require_http_methods(["GET"])
def oauth_github_callback(request):
    if request.user.is_anonymous:
        return render_github_oauth_fail(
            request, errors=["User not authenticated"]
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
            return render_github_oauth_fail(
                errors=[error["error_description"]]
            )
        return render_github_oauth_fail(
            request, errors=["No code found in parameters"]
        )

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

    profile_creation = create_profile_object(
        GithubProfile,
        access_token=access_token,
        username=github_details.login,
        provider_uid=github_details.id,
        user=request.user,
    )

    if profile_creation.success:
        profile = profile_creation.object
        for email_dict in github_details.get_emails():
            # TODO: Add primary and verified parameters
            create_model_object(
                EmailAddress, email=email_dict.get("email"), profile=profile,
            )
    else:
        return render_github_oauth_fail(
            request, errors=profile_creation.errors
        )

    return render_github_oauth_success(request)
