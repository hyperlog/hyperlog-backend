import logging

import boto3

from django.conf import settings
from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

AWS_ACCOUNT_ID = settings.AWS_ACCOUNT_ID
AWS_DEFAULT_REGION = settings.AWS_DEFAULT_REGION
AWS_SNS_TOPIC_ARN_TEMPLATE = "arn:aws:sns:%s:%s:{topic}" % (
    AWS_DEFAULT_REGION,
    AWS_ACCOUNT_ID,
)


def create_model_object(model, **kwargs):
    try:
        # Directly using model.objects.create() does not validate the data
        obj = model(**kwargs)
        obj.save()
    except ValidationError:
        error_msg = f"Validation failed for {model.__name__} with {kwargs}"
        logger.exception(error_msg)
        raise Exception(error_msg)

    return obj


def get_model_object(model, **kwargs):
    try:
        obj = model.objects.get(**kwargs)
    except model.DoesNotExist:
        error_msg = f"{model.__name__} with id {id} does not exist"
        logger.exception(error_msg)
        raise Exception(error_msg)
    except model.MultipleObjectsReturned:
        error_msg = (
            f"{model.__name__} with query {kwargs} returned multiple objects"
        )
        logger.exception(error_msg)
        raise Exception(error_msg)

    return obj


# General AWS utils


def get_aws_client(resource, **kwargs):
    """Returns a Boto3 client for the given resource.

    Parameters:
    * resource {str}: The AWS resource to fetch the client for
    (e.g. "sqs", "sns")
    * kwargs {Dict[str, Any]}: Other parameters while connecting the client
    which will overwrite the default configuration (from env variables).

    Returns:
    client {Boto3 low-level client}: A boto3 low-level client to access the
    provided resource
    """
    # Credentials and config details will automatically be taken from
    # environment variables
    try:
        client = boto3.client(resource)
        return client
    except Exception as e:
        logger.error(e, exc_info=True)
        raise


# SNS specific utils


def get_sns_topic_arn_by_name(topic):
    """Gets the ARN (Amazon Resource Name) for the given SNS topic"""
    return AWS_SNS_TOPIC_ARN_TEMPLATE.format(topic=topic)


def get_or_create_sns_topic(client, topic):
    """
    Creates a new SNS topic and returns the resulting topic ARN.
    This is idempotent, topic will only be created if it does not exist.

    Parameters:
    * client {Boto3 SNS client}: The SNS client which will execute the request
    (returned by `get_aws_client("sns")`)
    * topic {str}: The name of the topic

    Returns:
    * topic_arn {str}: The ARN of the topic
    """
    try:
        topic = client.create_topic(Name=topic)
    except Exception as e:
        logger.exception(e)
        raise

    return topic["TopicArn"]


def publish_message_to_sns_topic(client, topic, message, subject=None):
    """
    Publishes a message to SNS. Sends the same message to all subscribers of
    the topic.

    Parameters:
    * client {Boto3 SNS Client}: The SNS client to use (returned by
    `get_aws_client("sns")`)
    * topic {str}: The name of the topic to publish on
    * message {str}: The message to be published. If the payload is of type
    Dict, it should first be converted to JSON before passing here.
    * subject {Optional[str]}: The subject for the message. Will appear as the
    subject of email notifications. Will be accessible via the JSON response
    on other subscriptions.

    Returns:
    * message_id {str}: The `MessageId` as returned by AWS.
    """
    try:
        response = client.publish(
            TopicArn=get_sns_topic_arn_by_name(topic),
            Message=message,
            Subject=subject,
        )
    except Exception as e:
        logger.exception(e)
        raise

    return response["MessageId"]
