import json

from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinLengthValidator

from apps.base.utils import validate_lowercase
from apps.membership.utils import get_choices_validator, validate_price_type


class StripeProduct(models.Model):
    """Ref: https://stripe.com/docs/api/products"""

    # For docs on ID length see:
    # https://stripe.com/docs/upgrades#what-changes-does-stripe-consider-to-be-backwards-compatible  # noqa
    id = models.CharField(max_length=255, primary_key=True)
    active = models.BooleanField()
    # For docs on max length of name and description, see:
    # https://stripe.com/docs/upgrades#2018-10-31
    name = models.CharField(max_length=250)
    description = models.CharField(max_length=350, blank=True)
    _metadata_json = models.TextField(
        default=json.dumps({})
    )  # JSON-encoded key-value pairs

    # fmt: off
    def metadata():
        doc = "The metadata attribute of Product object. key-value pairs."
        def fget(self):  # noqa: E306
            return json.loads(self._metadata_json)
        def fset(self, value):  # noqa: E306
            self._metadata_json = json.dumps(value)
        def fdel(self):  # noqa: E306
            self._metadata_json = json.dumps({})
        return locals()
    metadata = property(**metadata())
    # fmt: on


class StripePrice(models.Model):
    """Ref: https://stripe.com/docs/api/prices"""

    # For docs on ID length see:
    # https://stripe.com/docs/upgrades#what-changes-does-stripe-consider-to-be-backwards-compatible  # noqa
    id = models.CharField(max_length=255, primary_key=True)
    active = models.BooleanField(default=True)
    # Should be exactly 3 characters, all lowercase and supported by stripe
    currency = models.CharField(
        default="inr",
        max_length=3,
        validators=[MinLengthValidator(3), validate_lowercase],
    )
    _metadata_json = models.TextField(
        default=json.dumps({})
    )  # JSON-encoded key-value pairs
    nickname = models.CharField(max_length=255, blank=True)
    product = models.ForeignKey(
        StripeProduct, on_delete=models.CASCADE, related_name="prices"
    )
    _recurring = models.TextField(
        default=json.dumps({})
    )  # JSON-encoded key-value pairs
    type = models.CharField(
        max_length=9, validators=[validate_price_type]
    )  # Either "one_time" or "recurring"
    unit_amount = models.IntegerField()  # Price in paise

    # fmt: off
    def metadata():
        doc = "The metadata attribute of Price object. key-value pairs."
        def fget(self):  # noqa: E306
            return json.loads(self._metadata_json)
        def fset(self, value):  # noqa: E306
            self._metadata_json = json.dumps(value)
        def fdel(self):  # noqa: E306
            self._metadata_json = json.dumps({})
        return locals()
    metadata = property(**metadata())
    # fmt: on

    def recurring():
        doc = "The recurring property."

        def fget(self):
            return json.loads(self._recurring)

        def fset(self, value):
            # Setting defaults
            recurring_dict = {
                "aggregate_usage": None,
                "interval": None,
                "interval_count": None,
                "usage_type": None,
            }
            if value.get("usage_type") == "metered":
                recurring_dict["aggregate_usage"] = "sum"
            if value.get("interval"):
                recurring_dict["interval_count"] = 1
            recurring_dict.update(**value)
            self._recurring = json.dumps(recurring_dict)

        def fdel(self):
            self._recurring = json.dumps({})

        return locals()

    recurring = property(**recurring())


class StripeCustomer(models.Model):
    """Ref: https://stripe.com/docs/api/customers"""

    # For docs on ID length see:
    # https://stripe.com/docs/upgrades#what-changes-does-stripe-consider-to-be-backwards-compatible  # noqa
    id = models.CharField(max_length=255, primary_key=True)
    description = models.CharField(max_length=350, blank=True)
    # The email here will be the one used by Stripe to notify the customer
    email = models.EmailField(max_length=255)
    _metadata_json = models.TextField(
        default=json.dumps({})
    )  # JSON-encoded key-value pairs
    user = models.OneToOneField(
        get_user_model(),
        on_delete=models.CASCADE,
        related_name="stripe_customer",
    )

    # fmt: off
    def metadata():
        doc = "The metadata attribute of Customer object. key-value pairs."
        def fget(self):  # noqa: E306
            return json.loads(self._metadata_json)
        def fset(self, value):  # noqa: E306
            self._metadata_json = json.dumps(value)
        def fdel(self):  # noqa: E306
            self._metadata_json = json.dumps({})
        return locals()
    metadata = property(**metadata())
    # fmt: on


class StripeSubscription(models.Model):
    """Ref: https://stripe.com/docs/billing/subscriptions/fixed-price#create-subscription"""  # noqa

    STATUS_INCOMPLETE = "incomplete"
    STATUS_INCOMPLETE_EXPIRED = "incomplete_expired"
    STATUS_TRIALING = "trialing"
    STATUS_ACTIVE = "active"
    STATUS_PAST_DUE = "past_due"
    STATUS_CANCELED = "canceled"
    STATUS_UNPAID = "unpaid"
    STATUS_CHOICES = [
        ("INC", STATUS_INCOMPLETE),
        ("INC_EX", STATUS_INCOMPLETE_EXPIRED),
        ("TRIAL", STATUS_TRIALING),
        ("ACTIVE", STATUS_ACTIVE),
        ("DUE", STATUS_PAST_DUE),
        ("CANCEL", STATUS_CANCELED),
        ("UNPAID", STATUS_UNPAID),
    ]

    # For docs on ID length see:
    # https://stripe.com/docs/upgrades#what-changes-does-stripe-consider-to-be-backwards-compatible  # noqa
    id = models.CharField(max_length=255, primary_key=True)
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    # OneToOne because one customer can only have one subscription at a time
    customer = models.OneToOneField(
        StripeCustomer, on_delete=models.CASCADE, related_name="subscription"
    )
    # Disallows deleting price if a subscription using that price exists
    price = models.ForeignKey(
        StripePrice, on_delete=models.PROTECT, related_name="subscriptions"
    )
    _status = models.CharField(
        max_length=6,
        choices=STATUS_CHOICES,
        validators=[
            get_choices_validator(
                STATUS_CHOICES, "Invalid subscription status %(value)s"
            )
        ],
    )

    # fmt: off
    def status():
        doc = "The status property."
        def fget(self):  # noqa: E306
            return self.get__status_display()
        def fset(self, value):  # noqa: E306
            self._status = value
        return locals()
    status = property(**status())
    # fmt: on
