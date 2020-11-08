import uuid

from django.contrib.postgres.fields import JSONField
from django.db import models

from apps.base.utils import get_sentinel_user


class Post(models.Model):
    class Meta:
        unique_together = ["author", "slug"]

    PUBLIC = "PB"
    PRIVATE = "PR"
    UNLISTED = "UL"
    VISIBILITY_CHOICES = [
        (PUBLIC, "public"),
        (PRIVATE, "private"),
        (UNLISTED, "unlisted"),
    ]

    author = models.ForeignKey(
        "users.User",
        on_delete=models.SET(get_sentinel_user),
        related_name="blog_posts",
    )
    slug = models.CharField(max_length=100)
    uuid = models.UUIDField(
        primary_key=True, default=uuid.uuid4, editable=False
    )
    title = models.CharField(max_length=100)
    subtitle = models.CharField(max_length=255)
    content = JSONField()
    feature_image = models.URLField()
    visibility = models.CharField(
        max_length=2, choices=VISIBILITY_CHOICES, default=PRIVATE
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(blank=True, null=True)
    custom_excerpt = models.CharField(max_length=255, blank=True, null=True)
    canonical_url = models.URLField(max_length=255, blank=True, null=True)
    url = models.URLField()
    excerpt = models.CharField(max_length=255, blank=True, null=True)
    reading_time = models.IntegerField()  # in minutes
    og_image = models.URLField(blank=True, null=True)
    og_title = models.CharField(max_length=100, blank=True, null=True)
    og_description = models.CharField(max_length=255, blank=True, null=True)
    twitter_image = models.URLField(blank=True, null=True)
    twitter_title = models.CharField(max_length=255, blank=True, null=True)
    twitter_description = models.CharField(
        max_length=512, blank=True, null=True
    )
    meta_title = models.CharField(max_length=100, blank=True, null=True)
    meta_description = models.CharField(max_length=255, blank=True, null=True)
    tags = models.ManyToManyField("blogs.Tag")

    def __str__(self):
        return f"{self.title} - author: {self.author.full_name}"

    def is_public(self):
        return self.visibility == self.PUBLIC


class Tag(models.Model):
    name = models.CharField(max_length=35, unique=True)

    def __str__(self):
        return self.name
