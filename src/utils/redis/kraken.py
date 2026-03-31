from json import dumps, loads

from src.config import getLogger, load_config
from src.kraken import KrakenData
from src.utils.redis.client import get_redis

"""
Describes getting and setting price information from the kraken API.
"""

logger = getLogger(__name__)
config = load_config()


def get_kraken_data() -> KrakenData | None:
    try:
        redis = get_redis()
        raw = redis.get(config.redis.kraken.kraken_data_key)
        if raw is None:
            logger.warning("Expected redis key '%s' to contain data.", config.redis.kraken.kraken_data_key)
            return None
        return KrakenData.from_dict(loads(raw))  # type: ignore[arg-type]
    except Exception as e:
        logger.error("Failed to load kraken data.", exc_info=e)
        return None


def set_kraken_data(kraken_data: KrakenData) -> None:
    redis = get_redis()
    redis.set(config.redis.kraken.kraken_data_key, dumps(kraken_data.to_dict()))


if __name__ == "__main__":
    from time import sleep

    while True:
        data = get_kraken_data()
        logger.info("live price: %s", str(data.live_price) if data else "NO DATA")
        sleep(0.5)
