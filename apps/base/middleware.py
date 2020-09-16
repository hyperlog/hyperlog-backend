from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.utils.cache import patch_vary_headers

from graphql import GraphQLError
from graphql_jwt.shortcuts import get_user_by_token


JWT_COOKIE_MAX_AGE = settings.JWT_CUSTOM_COOKIE_MIDDLEWARE_MAX_AGE


def custom_jwt_cookie_middleware(get_response):
    def middleware(request):
        if "JWT" in request.COOKIES:
            # When JWT exists and is used to get the user
            token = request.COOKIES.get("JWT")
            user = get_user_by_token(token)

            if user is not None:
                request.user = request._cached_user = user

        response = get_response(request)

        if "JWT" not in request.COOKIES and hasattr(request, "jwt_token"):
            # When a JWT needs to be set
            token = request.jwt_token
            response.set_cookie("JWT", token, max_age=JWT_COOKIE_MAX_AGE)

        patch_vary_headers(response, ["Authorization"])
        return response

    return middleware


def validate_request_for_jwt_newest_token(request):
    if (
        request.user.is_authenticated
        and getattr(request, "jwt_issued_at", None) is not None
        and request.user.last_login.timestamp() != request.jwt_issued_at
    ):
        request.user = AnonymousUser()
        raise GraphQLError(
            "Your login session has expired because a newer login was detected."  # noqa: E501
        )


def jwt_verify_newest_token(get_response):
    def middleware(request):
        validate_request_for_jwt_newest_token(request)
        return get_response(request)

    return middleware


class JWTVerifyNewestTokenMiddleware(object):
    """
    JWT Newest Token Middleware for Graphene.
    Django middlewares are executed before Graphene-specific middlewares.
    Since we want to override the GraphQL-JWT's authentication middleware
    behaviour, we need a middleware which will be run after that.
    """

    def resolve(self, next, root, info, **kwargs):
        if info.context.user.is_authenticated:
            context = info.context
            validate_request_for_jwt_newest_token(context)

        return next(root, info, **kwargs)
