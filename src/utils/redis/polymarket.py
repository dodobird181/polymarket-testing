from json import dumps, loads

from src.config import getLogger, load_config
from src.kraken import KrakenData
from src.utils.redis.client import get_redis

"""
Describes getting and setting price information from the kraken API.
"""

logger = getLogger(__name__)
config = load_config()


class NoKrakenData(Exception):
    """
    No kraken price data could be found in the redis cache. This should be a fatal errror
    for trading strategies.
    """

    def __init__(self):
        super().__init__("Expected redis key '%s' to contain data.", config.redis.kraken.kraken_data_key)


def get_kraken_data() -> KrakenData:
    redis = get_redis()
    raw = redis.get(config.redis.kraken.kraken_data_key)
    if raw is None:
        raise NoKrakenData()
    return KrakenData.from_dict(loads(raw))  # type: ignore[arg-type]


def set_kraken_data(kraken_data: KrakenData) -> None:
    redis = get_redis()
    redis.set(
        config.redis.kraken.kraken_data_key,
        dumps(kraken_data.to_dict()),
        # expire in 5 seconds. this way, strategies should recieve a fatal-error after 5 seconds
        # if the kraken data-fetcher stops working.
        ex=5,
    )


if __name__ == "__main__":
    # for testing...
    from time import sleep

    while True:
        data = get_kraken_data()
        logger.info("live price: %s", str(data.live_price) if data else "NO DATA")
        sleep(0.5)
