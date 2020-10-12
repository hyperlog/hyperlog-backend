from django.contrib import admin

from apps.profiles import models


class StackOverflowProfileAdmin(admin.ModelAdmin):
    readonly_fields = ("id",)


admin.site.register(models.BitbucketProfile)
admin.site.register(models.EmailAddress)
admin.site.register(models.GithubProfile)
admin.site.register(models.GitlabProfile)
admin.site.register(models.Notification)
admin.site.register(models.ProfileAnalysis)
admin.site.register(models.StackOverflowProfile, StackOverflowProfileAdmin)
admin.site.register(models.OutsiderMessage)
