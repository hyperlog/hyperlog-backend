import json
import logging

from channels.generic.websocket import WebsocketConsumer
from django.contrib.auth import get_user_model

from apps.base.utils import get_model_object

logger = logging.getLogger(__name__)

CLICK_EVENT = "click"
IMPRESSION_EVENT = "impression"


class WidgetConsumer(WebsocketConsumer):
    def connect(self):
        self.user_id = self.scope["url_route"]["kwargs"].get("user_id")
        if not self.user_id:
            logger.error(
                "No user_id found in URL route. Rejecting WS connection"
            )
            self.close()
            return

        get_user = get_model_object(get_user_model(), id=self.user_id)
        if get_user.success:
            user = get_user.object
        else:
            logger.error("No matching user id. Closing websocket connection")
            self.close()
            return

        self.widget = user.widget
        self.accept()

    def disconnect(self, close_code):
        logger.debug(
            "A connection from %(source)s was closed"
            % {"source": self.scope.get("client")[0]}
        )

    def receive(self, text_data=None, bytes_data=None):
        if bytes_data or not text_data:
            raise NotImplementedError

        data = json.loads(text_data)
        event = data["event"]

        if event == CLICK_EVENT:
            self.increment_clicks()
        elif event == IMPRESSION_EVENT:
            self.increment_impressions()
        else:
            logger.critical(
                f"Unknown event {event} received. Closing connection"
            )
            self.close()

    # helpers

    def increment_clicks(self):
        self.widget.refresh_from_db()
        self.widget.clicks += 1
        self.widget.full_clean()
        self.widget.save()

    def increment_impressions(self):
        self.widget.refresh_from_db()
        self.widget.impressions += 1
        self.widget.full_clean()
        self.widget.save()
