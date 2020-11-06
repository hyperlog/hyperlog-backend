from django.contrib import admin

from apps.messaging.models import TelegramUser, TelegramMessage


admin.site.register(TelegramUser)
admin.site.register(TelegramMessage)
