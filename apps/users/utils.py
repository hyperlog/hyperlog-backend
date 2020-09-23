import logging
from datetime import timedelta
from itertools import chain

import botocore
from coolname import generate as generate_readable
from graphql_jwt.utils import jwt_encode

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from apps.base.utils import (
    CreateModelResult,
    get_error_messages,
    get_aws_client,
    get_or_create_sns_topic_by_topic_name,
)
from apps.users.models import DeletedUser, User


DDB_PROFILES_TABLE = settings.AWS_DDB_PROFILES_TABLE
SNS_USER_DELETE_TOPIC = settings.AWS_SNS_USER_DELETE_TOPIC
RESET_PASSWORD_EMAIL = settings.AWS_SES_RESET_PASSWORD_EMAIL
REPLYTO_EMAIL = settings.AWS_SES_REPLYTO_EMAIL

logger = logging.getLogger(__name__)


def to_dict(instance):
    # https://stackoverflow.com/a/29088221
    opts = instance._meta
    data = {}
    for f in chain(opts.concrete_fields, opts.private_fields):
        data[f.name] = f.value_from_object(instance)
    for f in opts.many_to_many:
        data[f.name] = [i.id for i in f.value_from_object(instance)]
    return data


def create_user(username, email, password, **kwargs) -> CreateModelResult:
    """Util to create a user

    Does the following:
    1. Create a model with given kwargs as field-value pairs (username, email
    and password are required)
    2. Validate the model
    3. Return the result as a `CreateModelResult` instance

    See: `apps.base.utils.create_model_object`
    """
    # Force lowercase on username an email by default
    user = get_user_model()(
        username=username.lower(), email=email.lower(), **kwargs
    )
    if password is None:
        user.set_unusable_password()
    else:
        user.set_password(password)

    try:
        # Run all validations
        user.full_clean()
    except ValidationError as e:
        return CreateModelResult(success=False, errors=get_error_messages(e))

    try:
        dynamodb_create_profile(user)
    except botocore.exceptions.ClientError:
        logger.error("DynamoDB error encountered", exc_info=True)

    user.save()
    return CreateModelResult(success=True, object=user)


def delete_user(user: User) -> DeletedUser:
    """Delete a user

    Does the following:
    1. Copy the user's fields into the DeletedUser table (with is_active=False)
    2. Delete the user from the main Users table

    Notes:
    The objects with this model as foreign key will be deleted (e.g. the
    GithubProfile)
    """
    user_id = user.id

    # Get the dict representation of user and rename the ID field
    user_dict = to_dict(user)
    user_dict["old_user_id"] = user_dict.pop("id")

    kwargs = {}
    for field in DeletedUser._meta.get_fields():
        if field.name in user_dict:
            kwargs[field.name] = user_dict.pop(field.name)

    deleted_user = DeletedUser(**kwargs)
    deleted_user.save()
    user.delete()

    try:
        sns_publish_user_delete_event(user_id)
    except botocore.exceptions.ClientError:
        logger.exception("Couldn't publish user_delete SNS event")

    return deleted_user


def generate_random_username():
    """Generates a totally random readable username"""
    while True:
        username = "".join(map(lambda x: x.capitalize(), generate_readable(2)))
        if len(username) <= 15:
            return username


def dynamodb_create_profile(user):
    """Uses DynamoDB PutItem to create/update a profile on DynamoDB"""
    client = get_aws_client("dynamodb")

    # fmt: off
    return client.put_item(
        TableName=DDB_PROFILES_TABLE,
        Item={
            "user_id": {
                "S": str(user.id)
            },
            "status": {
                "S": "idle"
            },
            "turn": {
                "N": "0"
            },
        },
    )
    # fmt: on


def get_reset_password_link(user, linkType):
    # Encode with expiry of 10 minutes
    code = jwt_encode(
        {
            "username": user.username,
            "exp": timezone.now() + timedelta(seconds=600),
        }
    )
    base_url = (
        "https://gateway.hyperlog.io"
        if settings.DEBUG is False
        else "http://localhost:8000"
    )
    return f"{base_url}/reset_password?code={code}&type={linkType}"


def send_reset_password_email(user):
    """
    Sends an email to the user with a link to reset the password
    """
    url = get_reset_password_link(user, "default")

    from_email = RESET_PASSWORD_EMAIL
    to = user.email
    subject = "Reset your password"
    reply_to = REPLYTO_EMAIL

    text_content = """
Hey %(username)s,
We just received a request to reset your Hyperlog.io password. To do that, \
just follow this link: %(reset_link)s.

May the force be with you.

Regards,
Hyperlog Team
""" % {
        "username": user.username,
        "reset_link": url,
    }

    html_content = """<img src="" alt="Hyperlog Logo">
<p>Hey %(username)s,<br>
We just received a request to reset your Hyperlog.io password. Feel free \
ignore the email if it wasn't you.</p>

<a href="%(reset_link)s"><button style="">Reset password here</button></a>

<p>Regards,<br>
The Hyperlog Team</p>
""" % {
        "username": user.username,
        "reset_link": url,
    }

    msg = EmailMultiAlternatives(
        subject, text_content, from_email, [to], reply_to=[reply_to]
    )
    msg.attach_alternative(html_content, "text/html")

    try:
        msg.send()
    except botocore.exceptions.ClientError:
        if settings.DEBUG:  # Dev mode
            print(text_content)

        logger.exception("Reset Password: Unable to send email")
        return


def sns_publish_user_delete_event(user_id):
    """
    Publishes the user.delete event to the SNS topic
    (AWS_SNS_USER_DELETE_TOPIC in env vars)
    """
    topic = get_or_create_sns_topic_by_topic_name(SNS_USER_DELETE_TOPIC)
    return topic.publish(
        Message=str(timezone.now().timestamp()),
        MessageAttributes={
            "user_id": {"DataType": "String", "StringValue": str(user_id)}
        },
    )
