from django.contrib.auth.signals import user_logged_out
from django.dispatch import receiver
from django.utils import timezone


@receiver(user_logged_out)
def logout_callback(sender, **kwargs):
    user = kwargs.get("user")
    if user is not None:
        # Set last_login to logout time so that all tokens are invalidated
        user.last_login = timezone.now()
        user.full_clean()
        user.save()
