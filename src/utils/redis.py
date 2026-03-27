from redis import Redis

from src.config import load_config

"""
Provides a singleton redis client (per-thread).
"""

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
