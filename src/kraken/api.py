from requests import get as GET

KRAKEN_BASE = "https://api.kraken.com/0/public"
KRAKEN_PAIR = "XBTUSD"
KRAKEN_RESULT_KEY = "XXBTZUSD"


def fetch_live_price() -> float:
    resp = GET(f"{KRAKEN_BASE}/Ticker", params={"pair": KRAKEN_PAIR}, timeout=5)
    resp.raise_for_status()
    return float(resp.json()["result"][KRAKEN_RESULT_KEY]["c"][0])


def fetch_price_at(ts: int) -> float:
    """Returns the open price of the 5-min candle starting at ts (seconds)."""
    resp = GET(
        f"{KRAKEN_BASE}/OHLC",
        params={"pair": KRAKEN_PAIR, "interval": 5, "since": ts - 1},
        timeout=5,
    )
    resp.raise_for_status()
    candles = resp.json()["result"][KRAKEN_RESULT_KEY]
    return float(candles[0][1])  # open price of first candle


def fetch_history() -> list:
    """Fetch 5-min BTC history over the course of 24 hours (288 completed candles)."""
    resp = GET(
        f"{KRAKEN_BASE}/OHLC",
        params={"pair": KRAKEN_PAIR, "interval": 5},
        timeout=10,
    )
    resp.raise_for_status()
    candles = resp.json()["result"][KRAKEN_RESULT_KEY]
    # Kraken includes the current forming candle as the last entry — exclude it
    return candles[-289:-1]
