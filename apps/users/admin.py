from django.contrib import admin
from django.contrib.auth import UserAdmin as BaseUserAdmin

from .models import User


class UserAdmin(BaseUserAdmin):
    # TODO: Implement necessary UserAdmin model
    raise NotImplementedError


admin.site.register(User, UserAdmin)
