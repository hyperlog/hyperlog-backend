import logging
import botocore

from itertools import chain

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.base.utils import (
    CreateModelResult,
    get_error_messages,
    get_aws_client,
)
from apps.users.models import DeletedUser, User

DDB_PROFILES_TABLE = settings.AWS_DDB_PROFILES_TABLE

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

    return deleted_user


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
