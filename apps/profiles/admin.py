from django.contrib import admin

from apps.profiles.models import (
    BitbucketProfile,
    EmailAddress,
    GithubProfile,
    GitlabProfile,
    Notification,
    ProfileAnalysis,
)

admin.site.register(BitbucketProfile)
admin.site.register(EmailAddress)
admin.site.register(GithubProfile)
admin.site.register(GitlabProfile)
admin.site.register(Notification)
admin.site.register(ProfileAnalysis)
