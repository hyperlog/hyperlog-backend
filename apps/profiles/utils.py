from redis import Redis

from django.conf import settings

PROFILES_QUEUE = "queue:profiles"


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


def get_model_object(model, **kwargs):
    try:
        obj = model.objects.get(**kwargs)
    except model.DoesNotExist:
        raise Exception(f"{model.__name__} with id {id} does not exist")
    except model.MultipleObjectsReturned:
        raise Exception(
            f"{model.__name__} with queries {kwargs} returned multiple objects"
        )

    return obj
