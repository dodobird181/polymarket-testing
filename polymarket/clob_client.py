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
    limit: int = 10_000,
) -> list[Trade]:
    """
    Fetch on-chain trades for a market from the public data API.

    IMPORTANT: the data-api has a freshness lag at large limits.
      - limit ≤ ~20 : hits a hot cache, returns the very latest trades.
      - limit ≥ 500 : hits a slower store; trades from the last ~30s are absent.
    For live monitoring use limit=50. For closed-market backtests use limit=10_000.

    The data-api does not support timestamp filtering — filtering is done client-side.
    Returns trades sorted by timestamp ascending.
    """
    resp = requests.get(
        f"{DATA_API_BASE}/trades",
        params={"market": condition_id, "limit": limit},
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
