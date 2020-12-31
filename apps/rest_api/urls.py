from django.urls import path

from . import views


urlpatterns = [
    path("user_info/<uuid:user_id>/", views.get_user_info),
    path("user_socials/<uuid:user_id>/", views.get_user_socials),
    path("selected_repos/<uuid:user_id>/", views.get_selected_repos),
    path(
        "single_repo/<uuid:user_id>/<str:repo_full_name_b64>/",
        views.get_single_repo,
    ),
    path(
        "tech_analysis/<uuid:user_id>/add_repo/", views.add_tech_analysis_repo
    ),
]
