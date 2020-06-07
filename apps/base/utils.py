import logging

from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)


def create_model_object(model, **kwargs):
    try:
        # Directly using model.objects.create() does not validate the data
        obj = model(**kwargs)
        obj.save()
    except ValidationError:
        error_msg = f"Validation failed for {model.__name__} with {kwargs}"
        logger.exception(error_msg)
        raise Exception(error_msg)

    return obj


def get_model_object(model, **kwargs):
    try:
        obj = model.objects.get(**kwargs)
    except model.DoesNotExist:
        error_msg = f"{model.__name__} with id {id} does not exist"
        logger.exception(error_msg)
        raise Exception(error_msg)
    except model.MultipleObjectsReturned:
        error_msg = (
            f"{model.__name__} with query {kwargs} returned multiple objects"
        )
        logger.exception(error_msg)
        raise Exception(error_msg)

    return obj


def get_error_message(error: Exception) -> str:
    """Obtains the error message for an Exception.

    Procedure:
    1. See if exception has a 'message' attribute. If yes, return that.
    2. Otherwise simply return `str(error)`
    """
    return getattr(error, "message", str(error))
