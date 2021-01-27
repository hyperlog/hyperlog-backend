import base64
import json
import logging
from binascii import Error as Base64Error

from django.contrib.auth import get_user_model
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from apps.profiles.models import BaseProfileModel, Repo, TechAnalysis
from apps.profiles.utils import (
    dynamodb_get_profile_analysis,
    dynamodb_get_repo_analysis,
)
from apps.rest_api.utils import (
    validate_tech_analysis_data,
    validate_profile_analysis_data,
    validate_repo_analysis_data,
    require_techanalysis_auth,
    require_lambda_auth,
    dynamic_cors_middleware,
)


logger = logging.getLogger(__name__)


@dynamic_cors_middleware
@require_GET
def get_user_info(request):
    """
    GET /user_info/

    Return user info as a JSON object.
    Fields:
        - first_name
        - last_name
        - tagline
        - username
        - contact_info {
            - email
            - phone
            - address
        }
    """
    user = request._portfolio_user
    contact_info = getattr(user, "contact_info", None)

    return JsonResponse(
        {
            "first_name": user.first_name,
            "last_name": user.last_name,
            "tagline": user.tagline,
            "username": user.username,
            "contact_info": {
                "email": contact_info.email,
                "phone": contact_info.phone,
                "address": contact_info.address,
            }
            if contact_info is not None
            else None,
        }
    )


@dynamic_cors_middleware
@require_GET
def get_user_socials(request):
    """
    GET /user_socials/

    Return user's social links as a JSON object ({ provider -> username })
    Supported connections:
        - twitter
        - facebook
        - github
        - stackoverflow
        - dribble
        - devto
        - linkedin

    See `apps -> users -> models.py -> User Model -> SUPPORTED_SOCIAL_LINKS`
    for an authoritative list of supported connections.
    """
    user = request._portfolio_user

    return JsonResponse(user.social_links)


@dynamic_cors_middleware
@require_GET
def get_selected_repos(request):
    """
    GET /selected_repos/

    on_each_page = 100

    Gets all the repos to which the user has contributed. Returns dict with
    two params - `count` (integer) and `repos` (array of objects)
    Repo fields with example:
        - repo_name: "react"
        - description: "This is sample repo description"
        - repo_full_name: "facebook/react"
        - external_url: "https://github.com/facebook/react"
        - primary_language: "JavaScript"
        - visibility: "public"
    """
    user = request._portfolio_user
    prof_an = dynamodb_get_profile_analysis(
        user.id, AttributesToGet=["repos", "selectedRepos"]
    )
    result = []
    for repo_full_name in prof_an.get("selectedRepos", []):
        repo = prof_an["repos"].pop(repo_full_name)
        result.append(
            {
                "repo_name": repo_full_name.split("/", maxsplit=1)[1],
                "repo_full_name": repo_full_name,
                "description": repo["description"],
                "external_url": f"https://github.com/{repo_full_name}",
                "primary_language": repo["primaryLanguage"],
                "visibility": "private"
                if repo.get("isPrivate") is True
                else "public",
            }
        )

    return JsonResponse({"count": len(result), "repos": result})


@dynamic_cors_middleware
@require_GET
def get_single_repo(request, repo_full_name_b64):
    """
    GET /single_repo/<str:repo_full_name_b64>/

    Repo full name (`owner/repo`) must be base64 encoded

    Returns information about a single repository
    Fields:
        - private: bool
        - size: int
        - created_at: datetime
        - owner_avatar: url string
        - full_name: string
        - html_url: url string
        - name: string
        - license: map
        - languages: list[map]
        - archived: bool
        - default_branch: string
        - homepage: string
        - owner: string
        - description: string
        - pushed_at: datetime
        - stargazers_count: int
        - contributors: map
        - tech_stack: map ({"tech": {...}, "tags": {...}, "libs": {...}})
    """
    user = request._portfolio_user

    try:
        repo_full_name = base64.urlsafe_b64decode(repo_full_name_b64).decode()
    except Base64Error:
        logger.exception(
            f"Error while decoding base64 repo name {repo_full_name_b64}"
        )
        return HttpResponseBadRequest()

    attributes_to_get = [
        "archived",
        "commits",
        "contributors",
        "created_at",
        "default_branch",
        "description",
        "full_name",
        "homepage",
        "html_url",
        "languages",
        "license",
        "name",
        "owner",
        "owner_avatar",
        "private",
        "pushed_at",
        "size",
        "stargazers_count",
    ]

    repo = dynamodb_get_repo_analysis(
        repo_full_name, AttributesToGet=attributes_to_get
    )
    if repo is None:
        logger.exception(f"Repo not found {repo_full_name}")
        raise Http404()

    tech = getattr(user, "tech_analysis", None)
    if tech and repo_full_name in tech.repos:
        repo["tech_stack"] = tech.repos[repo_full_name]
    else:
        repo["tech_stack"] = None

    return JsonResponse(repo)


@require_techanalysis_auth
@csrf_exempt
def add_tech_analysis_repo(request, user_id):
    """
    POST /tech_analysis/<uuid:user_id>/add_repo/

    Data format (JSON):

    {
        "repo_full_name": "<ownerName>/<repoName>",
        "libs": {
            "js.lib_x": {
                "deletions": 100, "insertions": 123
            },
            "py.lib_y": {
                "deletions": 120, "insertions": 130
            }
        },
        "tech": {
            "tech_x": {
                "deletions": 10, "insertions": 20
            }
        },
        "tags": {
            "tag_x": {
                "deletions": 5, insertions: 2
            }
        }
    }
    """
    if request.method == "POST":
        UserModel = get_user_model()
        try:
            user = UserModel.objects.get(id=user_id)
        except UserModel.DoesNotExist:
            raise Http404()

        # Not hiding the endpoint (with 404) after this point
        data = json.loads(request.body.decode("utf-8"))
        try:
            validate_tech_analysis_data(data)
        except AssertionError:
            logger.exception(f"Couldn't validate tech analysis data: {data}")
            return HttpResponseBadRequest()

        if hasattr(user, "tech_analysis"):
            tech_analysis = user.tech_analysis
        else:
            tech_analysis = TechAnalysis(user=user)

        repo_name = data["repo_full_name"]
        tech_analysis.repos[repo_name] = {
            "libs": data["libs"],
            "tech": data["tech"],
            "tags": data["tags"],
        }

        tech_analysis.full_clean()
        tech_analysis.save()
        return JsonResponse({"success": True})
    else:
        raise Http404()


@require_lambda_auth
@csrf_exempt
def add_github_profile_analysis(request, user_id):
    """
    POST /profile_analysis/github/<uuid:user_id>/

    Data format (JSON):

    {
        user_profile: {
            ...
        },
        repos: {
            ...
        },
        selectedRepos: {
            ...
        }
    }
    """
    if request.method == "POST":
        UserModel = get_user_model()
        try:
            user = UserModel.objects.get(id=user_id)
        except UserModel.DoesNotExist:
            raise Http404()

        try:
            profile = user.profiles.get(_provider="github")
        except BaseProfileModel.DoesNotExist:
            raise Http404("GitHub profile isn't connected")

        # Not hiding the endpoint (with 404) after this point
        data = json.loads(request.body.decode("utf-8"))
        try:
            validate_profile_analysis_data(data)
        except AssertionError:
            logger.exception(
                f"Couldn't validate profile analysis data: {data}"
            )
            return HttpResponseBadRequest()

        profile.profile_analysis = data
        profile.full_clean()
        profile.save()

        return JsonResponse({"success": True})
    else:
        raise Http404()


@require_lambda_auth
@csrf_exempt
def add_github_repo_analysis(request, user_id):
    """
    POST /repo_analysis/github/<uuid:user_id>/

    Data format (JSON):

    {
        id: ...,  (as per GitHub)
        analysis: {
            full_name:
            archived:
            contributors:
            ...
        }
    }
    """
    provider = "github"

    if request.method == "POST":
        UserModel = get_user_model()
        try:
            # Just validate if user id is real
            UserModel.objects.get(id=user_id)
        except UserModel.DoesNotExist:
            raise Http404()

        # Not hiding the endpoint (with 404) after this point
        data = json.loads(request.body.decode("utf-8"))
        try:
            validate_repo_analysis_data(data)
        except AssertionError:
            logger.exception(f"Couldn't validate repo analysis data: {data}")
            return HttpResponseBadRequest()

        repo_id = data["id"]
        repo_full_name = data["analysis"]["full_name"]
        try:
            repo = Repo.objects.get(
                provider=provider, provider_repo_id=repo_id
            )
            repo.full_name = repo_full_name
            repo.repo_analysis = data["analysis"]
        except Repo.DoesNotExist:
            repo = Repo(
                provider=provider,
                provider_repo_id=repo_id,
                full_name=repo_full_name,
                repo_analysis=data["analysis"],
            )

        repo.full_clean()
        repo.save()
        return JsonResponse({"success": True})
    else:
        raise Http404()
