from django.db import models

from apps.base.utils import get_sentinel_user


class TelegramUser(models.Model):
    id = models.CharField(max_length=20, primary_key=True)  # chat id
    first_name = models.CharField(max_length=64)
    last_name = models.CharField(max_length=64, blank=True, null=True)


class TelegramMessage(models.Model):
    tg_message_id = models.IntegerField()  # message id
    hl_user = models.ForeignKey(
        "users.User",
        related_name="tg_messages",
        on_delete=models.SET(get_sentinel_user),
    )
    tg_user = models.ForeignKey(
        "messaging.TelegramUser",
        related_name="tg_messages",
        on_delete=models.SET(get_sentinel_user),
    )
    # Whether message is being sent or received
    is_outgoing = models.BooleanField(default=False)
    text = models.TextField()
    time = models.DateTimeField(auto_now_add=True)
