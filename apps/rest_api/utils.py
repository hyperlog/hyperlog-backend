import base64
import hashlib
import logging
import re
from functools import wraps

from django.conf import settings
from django.http import Http404
from django.contrib.auth import get_user_model


logger = logging.getLogger("django-restapi")

TECH_ANALYSIS_AUTH_HASH = settings.TECH_ANALYSIS_AUTH_HASH
LAMBDA_AUTH_USERNAME = settings.LAMBDA_AUTH_USERNAME
LAMBDA_AUTH_PASSWORD_HASH = settings.LAMBDA_AUTH_PASSWORD_HASH


def get_repo_full_name_pattern():
    return r"^[a-zA-Z0-9_\-\.]+/[a-zA-Z0-9_\-\.]+$"


def validate_tech_analysis_data(data):
    """
    Data format (JSON):

    {
        "repo_full_name": "vuejs/vue",
        "libs": {
            "js.validate": {
                "deletions": 321, "insertions": 579
            },
            "js.vue": {
                "deletions": 52420, "insertions": 19681
            },
            "js.config": {
                "deletions": 11050, "insertions": 22517
            }
        },
        "tech": {
            "javascript-web": {
                "deletions": 52772, "insertions": 20323
            },
            "testing": {
                "deletions": 75, "insertions": 259
            },
            "utils": {
                "deletions": 11073, "insertions": 22585
            }
        },
        "tags": {
            "ui-framework": {
                "deletions": 52422, "insertions": 19699
            },
            "configuration": {
                "deletions": 11050, "insertions": 22517
            }
        }
    }
    """
    assert set(data.keys()) == {"repo_full_name", "libs", "tech", "tags"}
    assert re.match(get_repo_full_name_pattern(), data["repo_full_name"])
    for key in ["libs", "tech", "tags"]:
        # passes for empty dicts too
        for _, val in data[key].items():
            assert set(val.keys()) == {"insertions", "deletions"}


def validate_profile_analysis_data(data):
    """
    Data Format (JSON):

    {
        "user_profile": {
            "avatarUrl": str,
            "bio": str,
            ...
        },
        "repos": {
            "<ownerName>/<repoName>": {
                "description": str,
                "full_name": str,
                ...
            }
        },
        "selectedRepos": [
            "<ownerName>/<repoName>",
            ...
        ]
    }
    """
    repo_full_name_pattern = get_repo_full_name_pattern()

    required_keys = {"user_profile", "repos"}
    for key in required_keys:
        assert key in data, f"Required key {key} absent"

    expected_keys = {"user_profile", "repos", "selectedRepos"}
    for key in data:
        assert key in expected_keys, f"Unexpected key {key}"

    for repo_full_name in data["repos"].keys():
        assert re.match(repo_full_name_pattern, repo_full_name)
    for repo_full_name in data["selectedRepos"]:
        assert re.match(repo_full_name_pattern, repo_full_name)


def validate_repo_analysis_data(data):
    """
    Data Format (JSON):

    {
        "id": int, # example - 45717250 for tensorflow
        "analysis": {
            "full_name": "tensorflow/tensorflow",
            "archived": false,
            ...
        }
    }
    """
    repo_full_name_regex = get_repo_full_name_pattern()

    assert set(data.keys()) == {"id", "analysis"}
    assert "full_name" in data["analysis"]
    assert re.match(repo_full_name_regex, data["analysis"]["full_name"])


def require_techanalysis_auth(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        auth_key = request.META.get("HTTP_AUTHORIZATION")
        if (
            auth_key is not None
            and hashlib.sha256(auth_key.encode()).hexdigest()
            == TECH_ANALYSIS_AUTH_HASH
        ):
            return view_func(request, *args, **kwargs)
        else:
            raise Http404()

    return wrapper


def require_lambda_auth(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        auth_header = request.META.get("HTTP_AUTHORIZATION")
        if not auth_header or not auth_header.lower().startswith("basic "):
            raise Http404()

        auth = auth_header[6:]
        if auth:
            try:
                auth = base64.b64decode(auth).decode()
                username, password = auth.split(":")
            except Exception:
                logger.exception("Error while trying lambda basic auth")
                raise Http404()

        if (
            username == LAMBDA_AUTH_USERNAME
            and hashlib.sha256(password.encode()).hexdigest()
            == LAMBDA_AUTH_PASSWORD_HASH
        ):
            return view_func(request, *args, **kwargs)

        raise Http404()

    return wrapper


def dynamic_cors_middleware(get_response):
    USER_ID_HEADER_KEY = "X-API-KEY"
    HOSTNAME_PATTERN = (
        r"^http://([^\.]*)\.localhost"
        if settings.ENV == "dev"
        else r"^https://([^\.]*)\.hyperlog\.dev"
    )

    @wraps(get_response)
    def middleware(request, *args, **kwargs):
        origin = request.META.get("HTTP_ORIGIN")

        if origin is None:
            raise Http404()

        reg_match = re.match(HOSTNAME_PATTERN, origin)
        if settings.DEBUG is False and not reg_match:
            logger.warn(
                f"Got invalid request from {origin}. "
                f"Hostname pattern wrong. Meta dump: {request.META}"
            )
            # 404 makes it a little bit harder for outsiders to understand the API  # noqa: E501
            raise Http404()

        subdomain_username = reg_match.group(1) if reg_match else None

        UserModel = get_user_model()
        user_id = request.headers.get(USER_ID_HEADER_KEY)

        try:
            portfolio_user = UserModel.objects.get(id=user_id)
            if not settings.DEBUG:
                assert portfolio_user.username == subdomain_username
        except UserModel.DoesNotExist:
            logger.warn(
                f"Got invalid request from {origin}. Wrong Portfolio user id. "
                f"Meta dump: {request.META}"
            )
            raise Http404()
        except AssertionError:
            logger.warn(
                f"Subdomain user ({subdomain_username}) and api-key user "
                f"({portfolio_user.username}) do not match"
            )
            raise Http404()

        request._portfolio_user = portfolio_user
        return get_response(request, *args, **kwargs)

    return middleware
