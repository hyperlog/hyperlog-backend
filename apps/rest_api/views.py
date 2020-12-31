import base64
import json
import logging
from binascii import Error as Base64Error

from django.contrib.auth import get_user_model
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from apps.profiles.models import TechAnalysis
from apps.profiles.utils import (
    dynamodb_get_profile_analysis,
    dynamodb_get_repo_analysis,
)
from apps.rest_api.utils import (
    validate_tech_analysis_data,
    require_techanalysis_auth,
)


logger = logging.getLogger(__name__)


@require_GET
def get_user_info(request, user_id):
    """
    GET /user_info/<uuid:user_id>/

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

    UUID param needs to be properly formatted with lowercase and dashes
    """
    UserModel = get_user_model()

    try:
        user = UserModel.objects.get(id=user_id)
    except UserModel.DoesNotExist:
        raise Http404()

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


@require_GET
def get_user_socials(request, user_id):
    """
    GET /user_socials/<uuid:user_id>/

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
    UserModel = get_user_model()

    try:
        user = UserModel.objects.get(id=user_id)
    except UserModel.DoesNotExist:
        raise Http404()

    return JsonResponse(user.social_links)


@require_GET
def get_selected_repos(request, user_id):
    """
    GET /selected_repos/<uuid:user_id>/

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
    UserModel = get_user_model()

    try:
        user = UserModel.objects.get(id=user_id)
    except UserModel.DoesNotExist:
        raise Http404()

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


@require_GET
def get_single_repo(request, user_id, repo_full_name_b64):
    """
    GET /single_repo/<uuid:user_id>/<str:repo_full_name_b64>/

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
        - commits: map
        - pushed_at: datetime
        - stargazers_count: int
        - contributors: map
        - tech_stack: map ({"tech": {...}, "tags": {...}, "libs": {...}})
    """
    UserModel = get_user_model()

    try:
        user = UserModel.objects.get(id=user_id)
    except UserModel.DoesNotExist:
        raise Http404()

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

        tech_analysis.save()
        return JsonResponse({"success": True})
    else:
        raise Http404()
