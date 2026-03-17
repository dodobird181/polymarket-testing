"""
Gamma API client — fetches BTC 5-min market metadata and resolution outcomes.

Key discovery from live API inspection:
- Series slug: btc-up-or-down-5m
- Event slug pattern: btc-updown-5m-{unix_ts}  (ts = window end, divisible by 300)
- Fetch by slug: GET /events?slug=btc-updown-5m-{ts}
- outcomePrices["1","0"] → resolved Up; ["0","1"] → resolved Down
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional

import requests

from polymarket.models import Market

GAMMA_BASE = "https://gamma-api.polymarket.com"
SERIES_SLUG = "btc-up-or-down-5m"
WINDOW_SECONDS = 300


def _parse_market(event: dict) -> Optional[Market]:
    """Parse a Gamma event dict into a Market. Returns None if malformed."""
    markets = event.get("markets", [])
    if not markets:
        return None
    m = markets[0]

    token_ids: list[str] = []
    raw_tokens = m.get("clobTokenIds", "[]")
    if isinstance(raw_tokens, str):
        import json
        token_ids = json.loads(raw_tokens)
    else:
        token_ids = raw_tokens

    if len(token_ids) < 2:
        return None

    outcome_prices: list[str] = []
    raw_prices = m.get("outcomePrices", '["0","0"]')
    if isinstance(raw_prices, str):
        import json
        outcome_prices = json.loads(raw_prices)
    else:
        outcome_prices = raw_prices

    up_price = float(outcome_prices[0]) if outcome_prices else 0.0
    down_price = float(outcome_prices[1]) if len(outcome_prices) > 1 else 0.0

    resolved = m.get("umaResolutionStatus") == "resolved" or (
        up_price in (0.0, 1.0) and down_price in (0.0, 1.0) and (up_price + down_price) == 1.0
    )

    outcome: Optional[str] = None
    if resolved:
        outcome = "Up" if up_price == 1.0 else "Down"

    # Parse start_time from eventStartTime (the actual 5-min window start)
    start_time_raw = event.get("startTime") or m.get("startDate") or event.get("startDate")
    end_time_raw = event.get("endDate") or m.get("endDate")

    def _parse_dt(s: Optional[str]) -> datetime:
        if not s:
            return datetime.now(timezone.utc)
        s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s)

    return Market(
        slug=event.get("slug", ""),
        condition_id=m.get("conditionId", ""),
        up_token_id=token_ids[0],
        down_token_id=token_ids[1],
        title=event.get("title", ""),
        start_time=_parse_dt(start_time_raw),
        end_time=_parse_dt(end_time_raw),
        closed=event.get("closed", False),
        resolved=resolved,
        outcome=outcome,
        up_price_at_close=up_price,
        volume=float(m.get("volume") or 0),
    )


def get_market_by_slug(slug: str) -> Optional[Market]:
    """Fetch a single BTC 5-min market by its exact slug."""
    resp = requests.get(f"{GAMMA_BASE}/events", params={"slug": slug}, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if not data:
        return None
    return _parse_market(data[0])


def get_recent_closed_markets(n: int = 50) -> list[Market]:
    """
    Fetch the last n resolved BTC 5-min markets by walking backwards
    from the most recent completed 5-min window.
    """
    now = int(time.time())
    # most recent completed window
    current_window = (now // WINDOW_SECONDS) * WINDOW_SECONDS

    markets: list[Market] = []
    ts = current_window - WINDOW_SECONDS  # start one window back (current may still be open)

    while len(markets) < n:
        slug = f"btc-updown-5m-{ts}"
        market = get_market_by_slug(slug)
        if market is not None and market.resolved:
            markets.append(market)
        ts -= WINDOW_SECONDS

        # safety: don't go back more than ~30 days
        if ts < now - 30 * 24 * 3600:
            break

    return markets
