from django.conf import settings
from django.shortcuts import render
from django.utils import timezone

from apps.base.utils import get_aws_client, get_sqs_queue_by_name

DYNAMODB_PROFILES_TABLE_NAME = settings.AWS_DYNAMODB_PROFILES_TABLE
PROFILE_ANALYSIS_QUEUE_NAME = settings.AWS_PROFILE_ANALYSIS_QUEUE
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


def dynamodb_get_analysis_status_by_user_id(user_id):
    """
    Uses the DynamoDB GetItem API to get the analysis status and then checks
    if the status is in progress
    """
    client = get_aws_client("dynamodb")

    key = {"user_id": {"S": str(user_id)}}
    response = client.get_item(TableName=DYNAMODB_PROFILES_TABLE_NAME, Key=key)
    return response["Item"]["status"]["S"]


def push_profile_analysis_to_sqs_queue(user_id, github_token):
    """
    Push a task for profile analysis onto the SQS profile analysis queue
    """
    queue = get_sqs_queue_by_name(PROFILE_ANALYSIS_QUEUE_NAME)

    # The MessageBody argument is required. Use it for timestamp
    return queue.send_message(
        MessageBody=str(timezone.now().timestamp()),
        MessageAttributes={
            "user_id": {"DataType": "String", "StringValue": str(user_id)},
            "github_token": {
                "DataType": "String",
                "StringValue": github_token,
            },
        },
    )
