from django.db import models

from apps.base.utils import get_sentinel_user


class TelegramUser(models.Model):
    id = models.CharField(max_length=20, primary_key=True)  # chat id
    first_name = models.CharField(max_length=64)
    last_name = models.CharField(max_length=64, blank=True, null=True)


class MessageFromTelegram(models.Model):
    telegram_message_id = models.IntegerField()  # message id
    receiver = models.ForeignKey(
        "users.User",
        related_name="received_messages_from_tg",
        on_delete=models.SET(get_sentinel_user),
    )
    sender = models.ForeignKey(
        TelegramUser,
        related_name="sent_messages",
        on_delete=models.SET(get_sentinel_user),
    )
    text = models.TextField()
    time = models.DateTimeField(auto_now_add=True)
