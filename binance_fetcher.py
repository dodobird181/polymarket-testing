import json
from time import sleep, time

import redis
import requests

from config import load_config
from log_config import getLogger
from market_info import current_window_start

logger = getLogger(__name__)

BINANCE_BASE = "https://api.binance.com/api/v3"


def fetch_price_at(ts: int) -> float:
    resp = requests.get(
        f"{BINANCE_BASE}/klines",
        params={
            "symbol": "BTCUSDT",
            "interval": "5m",
            "startTime": ts * 1000,  # Binance uses milliseconds
            "limit": 1,
        },
        timeout=5,
    )
    resp.raise_for_status()
    return float(resp.json()[0][1])  # index 1 = open price


def fetch_live_price() -> float:
    resp = requests.get(f"{BINANCE_BASE}/ticker/price", params={"symbol": "BTCUSDT"}, timeout=5)
    resp.raise_for_status()
    return float(resp.json()["price"])


def fetch_history() -> list:
    """
    Fetch 5-min BTC history over the course of 24 hours.
    """
    resp = requests.get(
        f"{BINANCE_BASE}/klines",
        params={"symbol": "BTCUSDT", "interval": "5m", "limit": 288},
        timeout=10,
    )
    resp.raise_for_status()
    # omit the last candle because binance include the current 5-minute period (not closed yet)
    return resp.json()[:-1]


if __name__ == "__main__":
    config = load_config()
    r = redis.Redis.from_url(config.redis_url, socket_connect_timeout=2, socket_timeout=2)

    last_window_ts: int | None = None
    window_start_price: float | None = None

    while True:
        try:
            start_ts = current_window_start()
            if start_ts != last_window_ts:
                last_window_ts = start_ts
                history = fetch_history()
                r.set("binance:history", json.dumps(history))
                window_start_price = fetch_price_at(start_ts)
                logger.info("New window — start price: %.2f", window_start_price)

            live_price = fetch_live_price()
            r.set(
                "binance:live",
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
            logger.error("Binance fetcher error: %s", e)

        sleep(1)
