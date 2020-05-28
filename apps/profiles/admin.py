from django.contrib import admin

from apps.profiles.models import (
    BaseProfileModel,
    BitbucketProfile,
    EmailAddress,
    GithubProfile,
    GitlabProfile,
    Notification,
)

admin.site.register(BaseProfileModel)
admin.site.register(BitbucketProfile)
admin.site.register(EmailAddress)
admin.site.register(GithubProfile)
admin.site.register(GitlabProfile)
admin.site.register(Notification)
