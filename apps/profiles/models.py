from django.db import models


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
            return super().create(**kwargs)

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
