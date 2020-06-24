from django.urls import path

from apps.membership import views


urlpatterns = [path("webhook/", views.webhook, name="webhook")]

app_name = "membership"
