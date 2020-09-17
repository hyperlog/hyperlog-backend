from calendar import timegm
from datetime import datetime

from graphql_jwt.settings import jwt_settings
from graphql_jwt.utils import jwt_decode

from django.contrib.auth import get_user_model
from django.utils import timezone


USER_ID_FIELD = "id"


def jwt_payload_handler(user, context=None):
    user_id = getattr(user, USER_ID_FIELD)

    issued_at = timezone.now()

    user.last_login = issued_at
    user.full_clean()
    user.save()

    payload = {
        USER_ID_FIELD: str(user_id),
        "exp": datetime.utcnow() + jwt_settings.JWT_EXPIRATION_DELTA,
        "issued_at": issued_at.timestamp(),
    }

    if jwt_settings.JWT_ALLOW_REFRESH:
        payload["origIat"] = timegm(datetime.utcnow().utctimetuple())

    if jwt_settings.JWT_AUDIENCE is not None:
        payload["aud"] = jwt_settings.JWT_AUDIENCE

    if jwt_settings.JWT_ISSUER is not None:
        payload["iss"] = jwt_settings.JWT_ISSUER

    return payload


def jwt_payload_get_username_handler(payload):
    return payload.get(USER_ID_FIELD)


def jwt_payload_get_user_by_natural_key_handler(username):
    UserModel = get_user_model()
    try:
        return UserModel.objects.get(**{USER_ID_FIELD: username})
    except UserModel.DoesNotExist:
        return None


def jwt_decode_handler(token, context=None):
    payload = jwt_decode(token)
    if context is not None:
        context.jwt_issued_at = payload.get("issued_at")

    return payload
