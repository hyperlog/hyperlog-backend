import sys

from github import Github
from requests_oauthlib import OAuth2Session

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.base.utils import create_model_object
from apps.profiles.models import GithubProfile

try:
    GITHUB_CLIENT_ID = settings.GITHUB_CLIENT_ID
    GITHUB_CLIENT_SECRET = settings.GITHUB_CLIENT_SECRET
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
def oauth_github(request):
    if request.user.is_authenticated:
        redirect_uri = reverse("profiles:oauth_github_callback")
        github = OAuth2Session(
            client_id=GITHUB_CLIENT_ID,
            redirect_uri=redirect_uri,
            scope=GITHUB_OAUTH_SCOPES,
        )
        authorization_url, state = github.authorization_url(
            GITHUB_AUTHORIZATION_URL
        )
        request.session["oauth_github_state"] = state
        return redirect(authorization_url)
    else:
        return redirect("/")
        # return JsonResponse({"Authorization": request.headers.get("Authorization"), "HTTP_AUTHORIZATION": request.headers.get("HTTP_AUTHORIZATION")})


@require_http_methods(["GET"])
def oauth_github_callback(request):
    if request.user.is_authenticated and request.GET.get("code"):
        code = request.GET.get("code")
        github = OAuth2Session(
            client_id=GITHUB_CLIENT_ID,
            state=request.session.get("oauth_github_state"),
        )
        access_token = github.fetch_token(
            GITHUB_TOKEN_URL, client_secret=GITHUB_CLIENT_SECRET, code=code
        )

        # Load interface to v3 API to grab uid, username and email
        g = Github(access_token.get('access_token'))
        g_user = g.get_user()
        # TODO: Add UID to model creation kwargs
        create_model_object(
            GithubProfile,
            access_token=access_token,
            username=g_user.login,
            emails=[each['email'] for each in g_user.get_emails()],
            user=request.user,
        )
        return redirect("/")
        # redirect to a page and indicate successful authentication
    else:
        return redirect("/")
