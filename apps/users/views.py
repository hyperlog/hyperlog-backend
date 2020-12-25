from graphql_jwt.utils import jwt_decode
from jwt.exceptions import InvalidTokenError

from django.contrib.auth import get_user_model
from django.http import HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from apps.base.utils import get_model_object


def render_reset_password_form(request, code, linkType):
    return render(
        request,
        "users/reset_password_form.html",
        {"code": code, "linkType": linkType},
    )


def render_reset_password_fail(request, errors):
    return render(
        request, "users/reset_password_fail.html", {"errors": errors}
    )


def render_reset_password_success(request, linkType="default"):
    return render(
        request, "users/reset_password_success.html", {"linkType": linkType}
    )


@require_http_methods(["GET", "POST"])
def reset_password(request):
    """Resets the password if correct token is provided"""

    if request.method == "GET":
        if "code" in request.GET:
            code = request.GET.get("code")
            linkType = request.GET.get("type")
            try:
                decoded = jwt_decode(code)
            except InvalidTokenError:
                return render_reset_password_fail(
                    request, errors=["Invalid code"]
                )

            _, exp = decoded["username"], decoded["exp"]

            if timezone.now().timestamp() > exp:
                return render_reset_password_fail(
                    request,
                    errors=["Code expired. Please try with a newer code."],
                )

            return render_reset_password_form(request, code, linkType)
        elif "status" in request.GET:
            status = request.GET.get("status")
            if status == "success":
                return render_reset_password_success(
                    request, linkType=request.GET.get("linkType")
                )
            else:
                return render_reset_password_fail(
                    request, errors=["Something went wrong. Please try again"]
                )
        else:
            return HttpResponseBadRequest()

    elif request.method == "POST":
        encoded = request.POST.get("code")
        password = request.POST.get("password1")

        if not encoded or not password:
            return render_reset_password_fail(
                request, errors=["Invalid request"]
            )

        try:
            decoded = jwt_decode(encoded)
        except InvalidTokenError:
            return render_reset_password_fail(request, errors=["Invalid code"])

        username, exp = decoded["username"], decoded["exp"]

        if timezone.now().timestamp() > exp:
            return render_reset_password_fail(
                request, errors=["Code expired. Please try with a newer code."]
            )

        get_user = get_model_object(get_user_model(), username=username)

        if get_user.success:
            user = get_user.object
            user.set_password(password)
            user.save()
            reset_base_url = reverse("users:reset_password")
            linkType = request.POST.get("linkType")
            return redirect(
                f"{reset_base_url}?status=success&linkType={linkType}"
            )
        else:
            return render_reset_password_fail(request, errors=get_user.errors)
