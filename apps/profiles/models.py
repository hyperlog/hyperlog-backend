import json
import logging

from django.db import models

from apps.profiles.utils import RedisInterface

logger = logging.getLogger(__name__)


class EmailAddress(models.Model):
    email = models.EmailField()
    profile = models.ForeignKey(
        "BaseProfileModel", on_delete=models.CASCADE, related_name="emails"
    )

    def __str__(self):
        return self.email


class BaseProfileModel(models.Model):
    _provider = models.CharField(max_length=20)
    username = models.CharField(
        max_length=255
    )  # Gitlab allows up to 255 chars
    access_token = models.CharField(max_length=255)
    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="profiles"
    )

    class Meta:
        # There should be only one profile with a provider and username pair
        unique_together = ["_provider", "username"]

    def __str__(self):
        return (
            f"Profile <provider: {self._provider}, username: {self.username}>"
        )

    def _get_payload(self):
        """Creates a JSON-encoded payload to send to Redis

        Payload format:
        {
          "provider": "github",
          "access_token": "the access token",
          "user_id": 1
        }
        """
        return json.dumps(
            {
                "provider": self._provider,
                "access_token": self.access_token,
                "user_id": self.user.id,
            }
        )

    def push_to_queue(self):
        """Pushes the payload obtained from _get_redis_payload to Redis"""
        r = RedisInterface()
        payload = self._get_payload()

        try:
            r.push_to_profiles_queue(payload)
        except Exception:
            # Log the error so that payload can be pushed later
            logger.error(
                f"Error while pushing payload '{payload}' to Redis queue",
                exc_info=True,
            )


def get_profile_manager_by_provider(provider: str) -> models.Manager:
    """
    Gets a specific manager for proxy profile models according to the profile
    provider - e.g. GitHub, GitLab, BitBucket
    The provider arg should be the lowercase representation of the name, i.e.
    GitHub -> 'github', GitLab -> 'gitlab'

    Usage:
    class GithubProfile(BaseProfileModel):
        objects = get_profile_manager_by_provider('github')()

        class Meta:
            proxy = True
    """

    class ProfileManager(models.Manager):
        def get_queryset(self):
            """
            Overrides the models.Manager's get_queryset method to only give
            results for the given provider
            """
            return super().get_queryset().filter(_provider=provider)

        def create(self, **kwargs):
            """
            Overrides the default create method
            """
            if kwargs.get("_provider"):
                raise Exception(
                    "_provider field can only be specified in model definition"
                )
            kwargs["_provider"] = provider
            profile_obj = super().create(**kwargs)
            profile_obj.push_to_queue()
            return profile_obj

    return ProfileManager


class GithubProfile(BaseProfileModel):
    objects = get_profile_manager_by_provider("github")()

    class Meta:
        proxy = True


class GitlabProfile(BaseProfileModel):
    objects = get_profile_manager_by_provider("gitlab")()

    class Meta:
        proxy = True


class BitbucketProfile(BaseProfileModel):
    objects = get_profile_manager_by_provider("bitbucket")()

    class Meta:
        proxy = True


class Notification(models.Model):
    """
    Note:
    Priority Field:
    Notification.priority is an IntegerField and can take values:

    0 - low
    1 - medium
    2 - high

    Can be accessed by Notification.LOW, Notification.MEDIUM, Notification.HIGH
    Default value is 1 - Medium
    """

    LOW = 0
    MEDIUM = 1
    HIGH = 2
    priority_choices = ((LOW, "Low"), (MEDIUM, "Medium"), (HIGH, "High"))

    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="notifications"
    )
    priority = models.IntegerField(choices=priority_choices, default_value=MEDIUM)
    read = models.BooleanField(default=False)
    heading = models.CharField(max_length=100)
    sub = models.TextField(blank=True)

    def __str__(self):
        return f"Notification <UserID: {self.user.id}, heading: {self.heading}"
