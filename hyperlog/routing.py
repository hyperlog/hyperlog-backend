from channels.routing import ProtocolTypeRouter, URLRouter

import apps.widgets.routing

application = ProtocolTypeRouter(
    {"websocket": URLRouter(apps.widgets.routing.websocket_urlpatterns)}
)
