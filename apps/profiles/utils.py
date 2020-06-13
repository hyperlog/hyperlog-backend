from redis import Redis

from django.conf import settings
from django.shortcuts import render

PROFILES_QUEUE = "queue:profiles"
GITHUB_SUCCESS_TEMPLATE_PATH = "profiles/github_success.html"
GITHUB_FAIL_TEMPLATE_PATH = "profiles/github_fail.html"


class RedisInterface:
    def __init__(self, **kwargs):
        self._conn = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            **kwargs,
        )

    def push_to_profiles_queue(self, payload):
        """Expects payload to be a JSON-encoded object"""
        self._conn.rpush(PROFILES_QUEUE, payload)
        # TODO: Add log info of payload being pushed


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
