from src.config import getLogger, load_config
from src.utils.market_info import Btc5MinMarketOutcome
from src.utils.redis.client import get_redis

"""
Caches resolved Polymarket BTC 5-min market outcomes in Redis.
"""

logger = getLogger(__name__)
config = load_config()


def _key(slug: str) -> str:
    return f"{config.redis.key_prefix}_outcome:{slug}"


def get_cached_outcome(slug: str) -> Btc5MinMarketOutcome | None:
    """
    Return the cached market outcome for the given slug, or None if not cached.
    """
    raw = get_redis().get(_key(slug))
    if raw is None:
        return None
    return Btc5MinMarketOutcome(raw.decode())


def cache_outcome(slug: str, outcome: Btc5MinMarketOutcome) -> None:
    """
    Cache a resolved market outcome. Resolved outcomes never change, so no expiry is set.
    """
    get_redis().set(_key(slug), outcome.value)
