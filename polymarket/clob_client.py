"""
CLOB / Data API clients.

prices-history  — AMM mid-price sampled every ~10 min (useless for 5-min windows)
trades          — individual on-chain fills from data-api.polymarket.com (useful!)

Trade schema (data-api):
  conditionId   str
  outcome       "Up" | "Down"
  price         float  price of *that* outcome token (0-1)
  size          float  USDC filled
  side          "BUY" | "SELL"
  timestamp     int    unix seconds
"""
from __future__ import annotations

from dataclasses import dataclass

import requests

from polymarket.models import PricePoint

CLOB_BASE     = "https://clob.polymarket.com"
DATA_API_BASE = "https://data-api.polymarket.com"


@dataclass
class Trade:
    timestamp: int
    outcome: str    # "Up" or "Down"
    price: float    # price of that outcome (0-1)
    size: float     # USDC
    side: str       # "BUY" or "SELL"

    @property
    def up_price(self) -> float:
        """Normalise to Up-token price regardless of which outcome was traded."""
        return self.price if self.outcome == "Up" else 1 - self.price


def get_price_history(
    up_token_id: str,
    start_ts: int | None = None,
    end_ts: int | None = None,
    fidelity: int = 1,
) -> list[PricePoint]:
    """
    AMM mid-price at `fidelity`-minute intervals.

    For 5-min markets pass start_ts/end_ts (the window boundaries) and
    fidelity=1 to get one sample per minute = 5 data points per window.

    Note: the AMM holds price at 0.505 until Chainlink resolves, so these
    points are useful for confirming flat/no-movement within the window.
    Real order-book fills (which can hit 90-95¢) come from get_trades().

    Args:
        up_token_id: clobTokenIds[0] from the Gamma API.
        start_ts:    Unix timestamp — prices at or after this time.
        end_ts:      Unix timestamp — prices at or before this time.
        fidelity:    Granularity in minutes (1 = finest available).
    """
    params: dict = {"market": up_token_id, "fidelity": fidelity}
    if start_ts is not None and end_ts is not None:
        params["startTs"] = start_ts
        params["endTs"] = end_ts
    else:
        params["interval"] = "all"
    resp = requests.get(f"{CLOB_BASE}/prices-history", params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return [PricePoint(t=pt["t"], p=pt["p"]) for pt in data.get("history", [])]


def get_trades(
    condition_id: str,
    start_ts: int | None = None,
    end_ts: int | None = None,
) -> list[Trade]:
    """
    Fetch all on-chain trades for a market from the public data API.

    The data-api does not support timestamp filtering — we fetch up to 10,000
    trades (the API maximum) and filter client-side by start_ts/end_ts.

    Returns trades sorted by timestamp ascending.

    Args:
        condition_id: The 0x-prefixed conditionId from the Gamma API.
        start_ts:     Keep only trades at or after this unix timestamp.
        end_ts:       Keep only trades at or before this unix timestamp.
    """
    resp = requests.get(
        f"{DATA_API_BASE}/trades",
        params={"market": condition_id, "limit": 10_000},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        return []
    trades = []
    for t in data:
        try:
            ts = int(t["timestamp"])
            if start_ts is not None and ts < start_ts:
                continue
            if end_ts is not None and ts > end_ts:
                continue
            trades.append(Trade(
                timestamp=ts,
                outcome=t["outcome"],
                price=float(t["price"]),
                size=float(t["size"]),
                side=t["side"],
            ))
        except (KeyError, ValueError):
            continue
    trades.sort(key=lambda x: x.timestamp)
    return trades


def get_current_price(up_token_id: str) -> float | None:
    """Get the current midpoint price for the Up token."""
    resp = requests.get(f"{CLOB_BASE}/midpoint", params={"token_id": up_token_id}, timeout=10)
    if resp.status_code != 200:
        return None
    data = resp.json()
    mid = data.get("mid")
    return float(mid) if mid is not None else None
