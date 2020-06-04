from redis import Redis

from django.conf import settings

PROFILES_QUEUE = "queue:profiles"
NOTIFICATIONS_QUEUE = "queue:notifications:{}"


class RedisInterface:
    def __init__(self, **kwargs):
        # this would create a new connection everytime a new interface is
        # created
        # TODO: Make connection an object globally accessible like
        # django.db.connection
        self._conn = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            password=settings.REDIS_PASSWORD,
            **kwargs,
        )

    def push_to_profiles_queue(self, payload):
        """Expects payload to be a JSON-encoded object"""
        self._conn.rpush(PROFILES_QUEUE, payload)
        # TODO: Add log info of payload being pushed

    def push_notification_id(self, user_id, notification_id):
        """Pushes a notification id belonging to the user with provided userid.
        Pushed to a queue named like 'queue:notifications:$user_id' (RPUSH)

        Payload should be the ID of the notification as per the database
        """
        self._conn.rpush(NOTIFICATIONS_QUEUE.format(user_id), notification_id)

    def pop_notification_id(self, user_id):
        """Pops notification id from user's queue (LPOP). None if the list is
        empty
        """
        self._conn.lpop(NOTIFICATIONS_QUEUE.format(user_id))
