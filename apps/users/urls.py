from django.urls import path

from apps.users import views


urlpatterns = [
    path("reset_password", views.reset_password, name="reset_password"),
]

app_name = "users"
