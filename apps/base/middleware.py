from django.contrib.auth import authenticate
from django.http import JsonResponse
from django.utils.cache import patch_vary_headers

from graphql_jwt.exceptions import JSONWebTokenError
from graphql_jwt.middleware import _authenticate


# https://github.com/flavors/django-graphql-jwt/blob/v0.2.1/graphql_jwt/middleware.py


def jwt_middleware(get_response):
    def middleware(request):
        # Before calling view
        if _authenticate(request):
            try:
                user = authenticate(request=request)
            except JSONWebTokenError as err:
                return JsonResponse(
                    {"errors": [{"message": str(err)}],}, status=401
                )

            if user is not None:
                request.user = request._cached_user = user

        # Calling view
        response = get_response(request)

        # After calling view
        patch_vary_headers(response, ("Authorization"))
        return response

    return middleware
