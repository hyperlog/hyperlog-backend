from django.urls import path

from apps.profiles import views


urlpatterns = [
    path("connect_github", views.connect_github),
    path("auth/github", views.oauth_github, name="oauth_github"),
    path(
        "auth/github/callback",
        views.oauth_github_callback,
        name="oauth_github_callback",
    ),
    # debugging stuff: remove later
    path("test_github_success", views.test_template_success),
    path("test_github_fail", views.test_template_fail),
    # debugging stuff
]

app_name = "profiles"
