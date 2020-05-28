import logging

from redis import Redis

from django.conf import settings
from django.core.exceptions import ValidationError

PROFILES_QUEUE = "queue:profiles"

logger = logging.getLogger(__name__)


class RedisInterface:
    def __init__(self, **kwargs):
        self._conn = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            **kwargs,
        )

    def push_to_profiles_queue(self, payload):
        """Expects payload to be a JSON-encoded object"""
        self._conn.rpush(PROFILES_QUEUE, payload)


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
