from django.contrib import admin

from apps.messaging.models import TelegramUser, MessageFromTelegram


admin.site.register(TelegramUser)
admin.site.register(MessageFromTelegram)
