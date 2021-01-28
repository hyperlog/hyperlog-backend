import logging
import uuid

from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import JSONField
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import m2m_changed, pre_save
from django.db.utils import IntegrityError
from django.dispatch import receiver
from django.utils import timezone

from apps.users.models import DeletedUser

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
    # Have to be flexible about ids because github/gitlab's ids are integers
    # but BitBucket uses uuid. CharField can take any type
    provider_uid = models.CharField(max_length=255)
    username = models.CharField(
        max_length=255
    )  # Gitlab allows up to 255 chars
    access_token = models.CharField(max_length=255)
    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="profiles"
    )
    profile_analysis = JSONField(default=dict, blank=True)

    class Meta:
        # There should be only one profile with the same provider and uid pair
        unique_together = [
            ("_provider", "provider_uid"),
            ("user", "_provider"),
        ]

    def unique_error_message(self, model_class, unique_check):
        if unique_check == ("_provider", "provider_uid"):
            return (
                "This %s account is already associated with a user"
                % self._provider
            )
        else:
            return super().unique_error_message(model_class, unique_check)

    @property
    def provider(self):
        return self._provider

    def __str__(self):
        return (
            f"<Profile provider: {self.provider}, username: {self.username}>"
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
    """

    class ProfileManager(models.Manager):
        def create(self, **kwargs):
            """
            Overrides the default create method

            Note: Only use this method in testing or when validation has
            already been done
            """
            if kwargs.get("_provider") and kwargs.get("_provider") != provider:
                raise Exception(
                    "_provider field can only be specified in model definition"
                )
            kwargs["_provider"] = provider
            # Convert non-str types (int, uuid) to str for provider_uid
            kwargs["provider_uid"] = str(kwargs["provider_uid"])
            profile_obj = super().create(**kwargs)

            return profile_obj

    return ProfileManager


class GithubProfile(BaseProfileModel):
    objects = get_profile_manager_by_provider("github")()

    def clean_fields(self, exclude=None):
        if self._provider and self._provider != "github":
            raise ValidationError(
                "The social provider cannot be defined externally"
            )
        self._provider = "github"
        super().clean_fields(exclude=exclude)


class GitlabProfile(BaseProfileModel):
    objects = get_profile_manager_by_provider("gitlab")()


class BitbucketProfile(BaseProfileModel):
    objects = get_profile_manager_by_provider("bitbucket")()


class StackOverflowProfile(models.Model):
    id = models.IntegerField(primary_key=True, editable=False)
    reputation = models.IntegerField()
    badge_counts = JSONField()
    link = models.CharField(max_length=255)
    user = models.OneToOneField(
        "users.User", on_delete=models.CASCADE, related_name="stack_overflow"
    )

    def __str__(self):
        return f"<StackOverflowProfile: {self.id}>"


class Repo(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # ID as per provider (e.g. GitHub)
    provider_repo_id = models.IntegerField(editable=False)
    provider = models.CharField(max_length=20, editable=False)
    full_name = models.CharField(max_length=255)
    repo_analysis = JSONField(default=dict)

    class Meta:
        unique_together = ("provider", "provider_repo_id")

    # For speeding up queries by full_name, put an index on the full_name field


class Project(models.Model):
    slug = models.CharField(max_length=120, primary_key=True, editable=False)
    name = models.CharField(max_length=100)
    user = models.ForeignKey(
        get_user_model(), related_name="projects", on_delete=models.CASCADE
    )
    repos = models.ManyToManyField(Repo, related_name="projects")
    tagline = models.CharField(max_length=200)
    description = models.CharField(max_length=2000, blank=True)
    icon = models.URLField()  # max_length is defaulted at 200


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

    user = models.ForeignKey(
        "users.User", on_delete=models.CASCADE, related_name="notifications"
    )
    priority = models.IntegerField(
        validators=[
            MinValueValidator(
                limit_value=LOW,
                message=f"Value of priority should be at least {LOW}",
            ),
            MaxValueValidator(
                limit_value=HIGH,
                message=f"Value of priority should be at most {HIGH}",
            ),
        ],
        default=MEDIUM,
    )
    read = models.BooleanField(default=False)
    heading = models.CharField(max_length=100)
    sub = models.TextField(blank=True)

    def __str__(self):
        return "<Notification User: %(username)s heading: %(heading)s>" % {
            "username": self.user.username,
            "heading": self.heading,
        }


class ProfileAnalysis(models.Model):
    # null = True so that when the record of analysis stays even if the user is deleted  # noqa
    user = models.ForeignKey(
        get_user_model(),
        null=True,
        on_delete=models.SET_NULL,
        related_name="profile_analyses",
    )
    deleted_user = models.ForeignKey(
        DeletedUser,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="profile_analyses",
    )
    start_timestamp = models.DateTimeField(auto_now_add=timezone.now)

    @property
    def has_valid_user(self):
        return True if self.user or self.deleted_user else False


class OutsiderMessage(models.Model):
    """A message sent from a non-Hyperlog user to a Hyperlog user"""

    sender_name = models.CharField(max_length=40)
    sender_email = models.EmailField()
    text = models.TextField()
    receiver = models.ForeignKey(
        "users.User",
        on_delete=models.CASCADE,
        related_name="outsider_messages",
    )
    time = models.DateTimeField(auto_now_add=True)
    is_archived = models.BooleanField()


class ContactInfo(models.Model):
    """Public contact info for a user"""

    user = models.OneToOneField(
        "users.User", on_delete=models.CASCADE, related_name="contact_info"
    )
    email = models.EmailField(max_length=255, blank=True, default="")
    phone = models.CharField(max_length=25, blank=True, default="")
    address = models.CharField(max_length=255, blank=True, default="")


def default_aggregated_analysis():
    return {"libs": {}, "tech": {}, "tags": {}}


class TechAnalysis(models.Model):
    """Tech analysis for user"""

    user = models.OneToOneField(
        "users.User", on_delete=models.CASCADE, related_name="tech_analysis"
    )
    repos = JSONField(default=dict)
    aggregated_analysis = JSONField(default=default_aggregated_analysis)

    # NOTE: If queries are slow, check out using GIN index for jsonb fields


# Signals


@receiver(pre_save, sender=TechAnalysis)
def add_aggregated_analysis(sender, instance, **kwargs):
    aggregated_analysis = {"libs": {}, "tech": {}, "tags": {}}

    def get_initial_stats_unit():
        return {"insertions": 0, "deletions": 0}

    for repo_name, repo in instance.repos.items():
        for libs_tech_or_tags in {"libs", "tech", "tags"}:
            for (specific_cat, stats) in repo[libs_tech_or_tags].items():
                if specific_cat not in aggregated_analysis[libs_tech_or_tags]:
                    aggregated_analysis[libs_tech_or_tags][
                        specific_cat
                    ] = get_initial_stats_unit()

                aggregated_analysis[libs_tech_or_tags][specific_cat][
                    "insertions"
                ] += stats["insertions"]
                aggregated_analysis[libs_tech_or_tags][specific_cat][
                    "deletions"
                ] += stats["deletions"]

    instance.aggregated_analysis = aggregated_analysis


@receiver(m2m_changed, sender=Project.repos.through)
def verify_repo_user_unique_together(sender, **kwargs):
    project = kwargs.get("instance")
    action = kwargs.get("action")
    repo_ids = kwargs.get("pk_set")

    if action == "pre_add":
        if Project.objects.filter(
            repos__in=repo_ids, user=project.user
        ).exists():
            raise IntegrityError(
                f"One of the keys in {repo_ids} violates unique together constraint for repo and user ({project.user.id})"  # noqa: E501
            )
