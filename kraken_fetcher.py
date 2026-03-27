import json
from time import sleep, time

import redis
import requests

from market_info import current_window_start
from src.config import getLogger, load_config

logger = getLogger(__name__)

KRAKEN_BASE = "https://api.kraken.com/0/public"
KRAKEN_PAIR = "XBTUSD"
KRAKEN_RESULT_KEY = "XXBTZUSD"


def fetch_live_price() -> float:
    resp = requests.get(f"{KRAKEN_BASE}/Ticker", params={"pair": KRAKEN_PAIR}, timeout=5)
    resp.raise_for_status()
    return float(resp.json()["result"][KRAKEN_RESULT_KEY]["c"][0])


def fetch_price_at(ts: int) -> float:
    """Returns the open price of the 5-min candle starting at ts (seconds)."""
    resp = requests.get(
        f"{KRAKEN_BASE}/OHLC",
        params={"pair": KRAKEN_PAIR, "interval": 5, "since": ts - 1},
        timeout=5,
    )
    resp.raise_for_status()
    candles = resp.json()["result"][KRAKEN_RESULT_KEY]
    return float(candles[0][1])  # open price of first candle


def fetch_history() -> list:
    """Fetch 5-min BTC history over the course of 24 hours (288 completed candles)."""
    resp = requests.get(
        f"{KRAKEN_BASE}/OHLC",
        params={"pair": KRAKEN_PAIR, "interval": 5},
        timeout=10,
    )
    resp.raise_for_status()
    candles = resp.json()["result"][KRAKEN_RESULT_KEY]
    # Kraken includes the current forming candle as the last entry — exclude it
    return candles[-289:-1]


if __name__ == "__main__":
    config = load_config()
    r = redis.Redis.from_url(config.redis_url, socket_connect_timeout=2, socket_timeout=2)

    last_window_ts: int | None = None
    window_start_price: float | None = None

    while True:
        try:
            start_ts = current_window_start()
            if start_ts != last_window_ts:
                history = fetch_history()
                r.set("kraken:history", json.dumps(history))
                window_start_price = fetch_price_at(start_ts)
                last_window_ts = start_ts  # only update after success
                logger.info("New window — start price: %.2f", window_start_price)

            live_price = fetch_live_price()
            r.set(
                "kraken:live",
                json.dumps(
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
