import logging

import requests

from django.conf import settings

from apps.messaging.models import TelegramMessage


logger = logging.getLogger(__name__)

TG_AUTH_SECRET = settings.TG_AUTH_SECRET
TG_BOT_ENDPOINT = settings.TG_BOT_ENDPOINT


def send_tg_message(hl_user, tg_user, text):
    chat_id = tg_user.id
    from_username = hl_user.username
    from_name = hl_user.get_full_name()

    previous_message = (
        TelegramMessage.objects.filter(hl_user=hl_user, tg_user=tg_user)
        .order_by("-time")
        .first()
    )

    r = requests.post(
        TG_BOT_ENDPOINT,
        headers={"Authorization": f"SECRET {TG_AUTH_SECRET}"},
        data={
            "action": "sendMessage",
            "chat_id": chat_id,
            "from_name": from_name,
            "from_username": from_username,
            "message_text": text,
            "previous_in_thread": previous_message.tg_message_id
            if previous_message
            else None,
        },
    )
    if r.status_code != requests.codes.OK:
        logger.error(
            f"Error while sending TG message: Code {r.status_code} - {r.content}"  # noqa: E501
        )
        raise Exception("An unexpected error occurred")
    else:
        message_id = r.json()["message_id"]

    tg_msg = TelegramMessage(
        tg_message_id=message_id,
        hl_user=hl_user,
        tg_user=tg_user,
        is_outgoing=True,
        text=text,
    )
    tg_msg.full_clean()
    tg_msg.save()

    return tg_msg
