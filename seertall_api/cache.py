import redis


class CacheClient:
    DEFAULT_EXPIRE_SEC = 60

    def __init__(self, redis_client: redis.Redis | None = None):
        self._redis_client: redis.Redis = redis_client or redis.Redis(
            host="redis", port=6379, db=0, decode_responses=True
        )

    @property
    def _redis(self) -> redis.Redis:
        return self._redis_client

    def get(self, key):
        return self._redis.get(key)

    def set(self, key, value):
        self._redis.setex(name=key, value=value, time=self.DEFAULT_EXPIRE_SEC)
