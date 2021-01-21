from django.urls import path

from . import views


urlpatterns = [
    path("user_info/", views.get_user_info),
    path("user_socials/", views.get_user_socials),
    path("selected_repos/", views.get_selected_repos),
    path("single_repo/<str:repo_full_name_b64>/", views.get_single_repo,),
    path(
        "tech_analysis/<uuid:user_id>/add_repo/", views.add_tech_analysis_repo
    ),
]
