from django.urls import path

from apps.widgets import consumers

websocket_urlpatterns = [
    path("ws/widgets/<user_id>", consumers.WidgetConsumer, name="ws_widgets")
]
