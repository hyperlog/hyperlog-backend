from django.urls import path

from apps.profiles import views


urlpatterns = [
    path("auth/github", views.oauth_github, name="oauth_github"),
    path(
        "auth/github/callback",
        views.oauth_github_callback,
        name="oauth_github_callback",
    ),
]

app_name = "profiles"
