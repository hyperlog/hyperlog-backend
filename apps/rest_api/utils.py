import hashlib
import re
from functools import wraps

from django.conf import settings
from django.http import Http404

TECH_ANALYSIS_AUTH_HASH = settings.TECH_ANALYSIS_AUTH_HASH


def validate_tech_analysis_data(data):
    """
    Data format (JSON):

    {
        "repo_full_name": "vuejs/vue",
        "libs": {
            "js.validate": {
                "deletions": 321, "insertions": 579
            },
            "js.vue": {
                "deletions": 52420, "insertions": 19681
            },
            "js.config": {
                "deletions": 11050, "insertions": 22517
            }
        },
        "tech": {
            "javascript-web": {
                "deletions": 52772, "insertions": 20323
            },
            "testing": {
                "deletions": 75, "insertions": 259
            },
            "utils": {
                "deletions": 11073, "insertions": 22585
            }
        },
        "tags": {
            "ui-framework": {
                "deletions": 52422, "insertions": 19699
            },
            "configuration": {
                "deletions": 11050, "insertions": 22517
            }
        }
    }
    """
    assert set(data.keys()) == {"repo_full_name", "libs", "tech", "tags"}
    assert re.match(
        r"^[a-zA-Z0-9_\-\.]+/[a-zA-Z0-9_\-\.]+$", data["repo_full_name"]
    )
    for key in ["libs", "tech", "tags"]:
        # passes for empty dicts too
        for _, val in data[key].items():
            assert set(val.keys()) == {"insertions", "deletions"}


def require_techanalysis_auth(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        auth_key = request.META.get("HTTP_AUTHORIZATION")
        if (
            auth_key is not None
            and hashlib.sha256(auth_key.encode()).hexdigest()
            == TECH_ANALYSIS_AUTH_HASH
        ):
            return view_func(request, *args, **kwargs)
        else:
            raise Http404()

    return wrapper
