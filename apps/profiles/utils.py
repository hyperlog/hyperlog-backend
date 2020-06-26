from django.shortcuts import render

from apps.base.utils import get_aws_client

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
    client = get_aws_client("dynamodb")

    key = {"user_id": {"S": str(profile.user.id)}}
    expression_attribute_names = {"#AT": "%s_access_token" % profile.provider}
    expression_attribute_values = {":t": {"S": profile.access_token}}
    update_expression = "SET #AT = :t"

    return client.update_item(
        TableName=DYNAMODB_PROFILES_TABLE_NAME,
        Key=key,
        UpdateExpression=update_expression,
        ExpressionAttributeNames=expression_attribute_names,
        ExpressionAttributeValues=expression_attribute_values,
    )
