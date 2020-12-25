from django.urls import path

from apps.users import views


urlpatterns = [
    path("reset_password", views.reset_password, name="reset_password"),
    path("user_info/<uuid:user_id>/", views.user_info),
    path("user_socials/<uuid:user_id>/", views.user_socials),
]

app_name = "users"
