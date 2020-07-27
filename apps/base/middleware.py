from django.conf import settings
from django.utils.cache import patch_vary_headers

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
