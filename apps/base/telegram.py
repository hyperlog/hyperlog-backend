import hashlib
import logging
from functools import wraps

from graphql import GraphQLError
from graphql.execution import ResolveInfo

from django.conf import settings

logger = logging.getLogger(__name__)

TG_BOT_SOURCE = settings.TG_BOT_SOURCE
TG_TOKEN_HASH = settings.TG_TOKEN_HASH


def context(f):
    def decorator(func):
        def wrapper(*args, **kwargs):
            info = next(arg for arg in args if isinstance(arg, ResolveInfo))
            return func(info.context, *args, **kwargs)

        return wrapper

    return decorator


def telegram_bot_required(f):
    @wraps(f)
    @context(f)
    def wrapper(context, *args, **kwargs):
        source = get_source_ip_addr(context)
        if source != TG_BOT_SOURCE:
            logger.error(
                f"Expected Telegram bot to connect from '{TG_BOT_SOURCE}'. "
                f"Instead received connection from '{source}'"
            )
            raise GraphQLError("Permission denied!")

        auth_token = get_telegram_token_header(context)
        if (
            auth_token
            and hashlib.sha256(auth_token.encode()).hexdigest()
            == TG_TOKEN_HASH
        ):
            return f(*args, **kwargs)
        else:
            logger.error("Telegram token mismatch")
            raise GraphQLError("Permission denied!")

    return wrapper


def get_source_ip_addr(request):
    x_forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    return (
        x_forwarded.split(",")[0]
        if x_forwarded
        else request.META.get("REMOTE_ADDR")
    )


def get_telegram_token_header(request):
    """ The Auth header should be of the form - 'TG <..token_here..>' """
    auth_val = request.META.get("HTTP_AUTHORIZATION")
    if auth_val:
        auth_val_split = auth_val.split(" ")
        if len(auth_val_split) == 2 and auth_val_split[0].upper() == "TG":
            return auth_val_split[1]
