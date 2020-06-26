from django.shortcuts import render

from apps.base.utils import dynamodb_create_or_update_item

DYNAMODB_PROFILES_TABLE_NAME = "profiles"
GITHUB_SUCCESS_TEMPLATE_PATH = "profiles/github_success.html"
GITHUB_FAIL_TEMPLATE_PATH = "profiles/github_fail.html"


def render_github_oauth_success(request, **kwargs):
    """
    Example call:
    ```python
        # From inside a view function
        return render_github_oauth_success(request)
    ```
    """
    return render(request, GITHUB_SUCCESS_TEMPLATE_PATH, kwargs)


def render_github_oauth_fail(request, **kwargs):
    """
    Example call:
    ```python
        # From inside a view function
        return render_github_oauth_fail(
            request, errors=["error1", "error2"],
        )
    ```
    """
    return render(request, GITHUB_FAIL_TEMPLATE_PATH, kwargs)


def dynamodb_create_or_update_profile(profile):
    """Uses DynamoDB PutItem to create/update a profile on DynamoDB"""
    attrs = {
        "user_id": {"S": str(profile.user.id)},
        f"{profile.provider}_access_token": {"S": profile.access_token},
    }
    return dynamodb_create_or_update_item(
        table_name=DYNAMODB_PROFILES_TABLE_NAME, attrs=attrs
    )
