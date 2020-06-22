import json

from django.db import models
from django.contrib.auth import get_user_model
from django.core.validators import MinLengthValidator

from apps.base.utils import validate_lowercase
from apps.membership.utils import validate_price_type


class StripeProduct(models.Model):
    """Ref: https://stripe.com/docs/api/products"""

    # For docs on ID length see:
    # https://stripe.com/docs/upgrades#what-changes-does-stripe-consider-to-be-backwards-compatible  # noqa
    id = models.CharField(max_length=255)
    active = models.BooleanField()
    # For docs on max length of name and description, see:
    # https://stripe.com/docs/upgrades#2018-10-31
    name = models.CharField(max_length=250)
    description = models.CharField(max_length=350)
    _metadata_json = models.TextField(
        default=json.dumps({})
    )  # JSON-encoded key-value pairs

    def metadata():
        doc = "The metadata attribute of Product object. key-value pairs."

        def fget(self):
            return json.loads(self._metadata_json)

        def fset(self, value):
            self._metadata_json = json.dumps(value)

        def fdel(self):
            self._metadata_json = json.dumps({})

        return locals()

    metadata = property(**metadata())  # fmt: off


class StripePrice(models.Model):
    """Ref: https://stripe.com/docs/api/prices"""

    # For docs on ID length see:
    # https://stripe.com/docs/upgrades#what-changes-does-stripe-consider-to-be-backwards-compatible  # noqa
    id = models.CharField(max_length=255)
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

    def metadata():
        doc = "The metadata attribute of Price object. key-value pairs."

        def fget(self):
            return json.loads(self._metadata_json)

        def fset(self, value):
            self._metadata_json = json.dumps(value)

        def fdel(self):
            self._metadata_json = json.dumps({})

        return locals()

    metadata = property(**metadata())

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
    id = models.CharField(max_length=255)
    description = models.TextField(blank=True)
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

    def metadata():
        doc = "The metadata attribute of Customer object. key-value pairs."

        def fget(self):
            return json.loads(self._metadata_json)

        def fset(self, value):
            self._metadata_json = json.dumps(value)

        def fdel(self):
            self._metadata_json = json.dumps({})

        return locals()

    metadata = property(**metadata())


class StripeSubscription(models.Model):
    """Ref: https://stripe.com/docs/billing/subscriptions/fixed-price#create-subscription"""  # noqa

    # For docs on ID length see:
    # https://stripe.com/docs/upgrades#what-changes-does-stripe-consider-to-be-backwards-compatible  # noqa
    id = models.CharField(max_length=255)
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    customer = models.ForeignKey(
        StripeCustomer, on_delete=models.CASCADE, related_name="subscriptions"
    )
    # Disallows deleting price if a subscription using that price exists
    price = models.ForeignKey(
        StripePrice, on_delete=models.PROTECT, related_name="subscriptions"
    )
