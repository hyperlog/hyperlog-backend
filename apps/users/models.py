from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def _create_user(
        self, email, username, name, is_staff, is_superuser, **extra_fields
    ):
        """
        Creates and saves a User with the given name, username and email
        """
        user = self.model(
            email=self.normalize_email(email),
            username=username,
            name=name,
            is_active=True,
            is_staff=is_staff,
            is_superuser=is_superuser,
            last_login=timezone.now(),
            registered_at=timezone.now(),
            **extra_fields
        )
        user.save(using=self._db)
        return user

    def create_user(self, email, username, name, **extra_fields):
        is_staff = extra_fields.pop("is_staff", False)
        is_superuser = extra_fields.pop("is_superuser", False)
        return self._create_user(
            email, username, name, is_staff, is_superuser, **extra_fields
        )

    def create_superuser(self, email, username, name, **extra_fields):
        return self._create_user(
            email,
            username,
            name,
            is_staff=True,
            is_superuser=True,
            **extra_fields
        )


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(
        verbose_name="Email", unique=True, max_length=255
    )
    username = models.CharField(verbose_name="Username", max_length=30)
    name = models.CharField(verbose_name="Name", max_length=60)
    # TODO: Finish up the Github model and come back
    # github = models.ForeignKey('')

    # Fields settings
    EMAIL_FIELD = "email"
    USERNAME_FIELD = "username"

    is_admin = models.BooleanField(verbose_name="Admin", default=False)
    is_active = models.BooleanField(verbose_name="Active", default=True)
    is_staff = models.BooleanField(verbose_name="Staff", default=False)
    registered_at = models.DateTimeField(
        verbose_name="Registered at", auto_now_add=timezone.now
    )

    objects = UserManager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
