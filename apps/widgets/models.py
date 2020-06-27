from django.contrib.auth import get_user_model
from django.db import models


class Widget(models.Model):
    user = models.OneToOneField(
        get_user_model(), on_delete=models.CASCADE, related_name="widget"
    )
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)

    def __str__(self):
        return (
            f"<Widget clicks: {self.clicks} impressions: {self.impressions}>"
        )
