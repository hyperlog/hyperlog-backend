from django.core.exceptions import ValidationError


def validate_price_type(value):
    if value not in ["recurring", "one_time"]:
        raise ValidationError(
            "Price.type must be either 'recurring' or 'one_time'"
        )


def get_choices_validator(choices, message):
    global validate_choices

    def validate_choices(value):
        if value not in [choice[0] for choice in choices]:
            raise ValidationError(message % {"value": value})

    return validate_choices
