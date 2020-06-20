from django.core.exceptions import ValidationError


def validate_price_type(value):
    if value not in ["recurring", "one_time"]:
        raise ValidationError(
            "Price.type must be either 'recurring' or 'one_time'"
        )
