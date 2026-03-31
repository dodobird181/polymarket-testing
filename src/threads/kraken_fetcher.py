from json import dumps
from pathlib import Path
from sys import path as systempath
from time import sleep, time

from requests import get as GET

systempath.insert(0, str(Path(__file__).parents[2]))
from src.config import getLogger, load_config
from src.utils import get_redis
from src.utils.market_info import current_window_start

logger = getLogger(__name__)


if __name__ == "__main__":
    config = load_config()
    redis = get_redis()

    last_window_ts: int | None = None
    window_start_price: float | None = None

    while True:
        try:
            start_ts = current_window_start()
            if start_ts != last_window_ts:
                history = fetch_history()
                redis.set("kraken:history", dumps(history))
                redis.incr("kraken:history:count")
                window_start_price = fetch_price_at(start_ts)
                last_window_ts = start_ts  # only update after success
                logger.info("New window — start price: %.2f", window_start_price)

            live_price = fetch_live_price()
            redis.set(
                "kraken:live",
                dumps(
                    {
                        "live_price": live_price,
                        "window_start_price": window_start_price,
                        "ts": time(),
                    }
                ),
            )
            logger.debug("BTC live price: %.2f", live_price)

        except Exception as e:
            logger.error("Kraken fetcher error: %s", e)

        sleep(1)
