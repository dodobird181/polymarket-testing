from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from json import loads
from time import time
from zoneinfo import ZoneInfo

from requests import get as GET
from requests.exceptions import HTTPError


@dataclass
class Btc5MinClobs:
    up: str
    down: str


class Btc5MinMarketOutcome(Enum):
    UNRESOLVED = "unresolved"
    UP = "up"
    DOWN = "down"


class MarketNotFound(Exception): ...


WINDOW_SECS = 300  # 5-min window


def current_window_start() -> int:
    """
    Unix timestamp of the current 5-min window's start.
    """
    return (int(time()) // WINDOW_SECS) * WINDOW_SECS


def to_EST(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(ZoneInfo("America/New_York"))
    return dt.strftime("%Y-%m-%d %I:%M:%S %p EST")


def current_window_slug(window_start_ts) -> str:
    """
    Current 5-min window slug.
    """
    return f"btc-updown-5m-{window_start_ts}"


def elapsed(window_start_ts: int) -> int:
    return int(time()) - window_start_ts


def get_market_by_slug(slug: str) -> dict:
    """
    Fetch a single BTC 5-min market by its exact slug.
    """

    response = GET(f"https://gamma-api.polymarket.com/events", params={"slug": slug}, timeout=10)
    try:
        response.raise_for_status()
        data = response.json()
        if data is None or not isinstance(data, list) or len(data) < 1:
            raise MarketNotFound(f"No market data found for slug: {slug}.")
        if len(data[0]["markets"]) != 1:
            raise AssertionError("Expected BTC Up/Down market response to contain exactly 1 market!")
        return data[0]
    except HTTPError as e:
        raise MarketNotFound from e


def get_current_market_clobs() -> Btc5MinClobs:
    """
    Get current BTC 5-min market clob token ids for the Up and Down directions.
    """

    ts = current_window_start()
    slug = current_window_slug(ts)
    market = get_market_by_slug(slug)
    outcomes = loads(market["markets"][0]["outcomes"])
    if len(outcomes) != 2:
        raise AssertionError("Expected BTC Up/Down market response to contain exactly 2 outcomes!")
    tids = loads(market["markets"][0]["clobTokenIds"])
    market_clobs = dict(zip([x.lower() for x in outcomes], tids))
    return Btc5MinClobs(up=market_clobs["up"], down=market_clobs["down"])


def get_market_outcome_from_slug(slug: str) -> Btc5MinMarketOutcome:
    market = get_market_by_slug(slug)
    outcomes = loads(market["markets"][0]["outcomes"])
    if len(outcomes) != 2:
        raise AssertionError("Expected BTC Up/Down market response to contain exactly 2 outcomes!")
    probabilities = loads(market["markets"][0]["outcomePrices"])
    if market["closed"] == True:
        market_probs = dict(zip([x.lower() for x in outcomes], probabilities))
        if float(market_probs["up"]) == 1:
            return Btc5MinMarketOutcome.UP
        elif float(market_probs["down"]) == 1:
            return Btc5MinMarketOutcome.DOWN
        else:
            raise AssertionError("Expected a market to have one outcome with price == 1 after close.")
    return Btc5MinMarketOutcome.UNRESOLVED
