from redis import Redis

from config import load_config

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        config = load_config()
        _client = Redis.from_url(
            config.redis_url,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _client
