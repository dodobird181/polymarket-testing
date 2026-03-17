"""
Loader: fetches N resolved BTC 5-min markets and enriches each with
intra-window price history from the CLOB API.

Returns a pandas DataFrame with one row per market, ready for backtesting.

Columns:
  slug            str   btc-updown-5m-{ts}
  title           str   human-readable window label
  start_time      datetime (UTC)
  end_time        datetime (UTC)
  outcome         str   "Up" or "Down"
  volume          float total USDC traded
  open_price      float AMM mid-price at window open (~0.505, use for baseline strategies)
  trade_open      float first actual order-book fill price in the window
  close_price     float price at last sample in window
  max_price       float highest price in window
  min_price       float lowest price in window
  n_trades        int   number of on-chain fills
  trades          list  raw fills: [{"t", "p" (up-price), "size", "side", "outcome"}]
  up_token_id     str   for further CLOB queries
  condition_id    str   market condition ID
"""
from __future__ import annotations

import time
from typing import Optional

import pandas as pd

from polymarket.gamma_client import get_recent_closed_markets
from polymarket.clob_client import get_trades, get_price_history


def load_markets(n: int = 50, verbose: bool = True) -> pd.DataFrame:
    """
    Fetch n resolved BTC 5-min markets and their price histories.

    Note: each market requires 2 HTTP calls (Gamma + CLOB), so n=50 → ~100 requests.
    A small sleep is added to be polite to the API.
    """
    if verbose:
        print(f"Fetching {n} resolved BTC 5-min markets from Gamma API...")

    markets = get_recent_closed_markets(n)

    if verbose:
        print(f"  Got {len(markets)} markets. Fetching trades + AMM prices (3 calls/market)...")

    rows = []
    for i, market in enumerate(markets):
        # Derive 5-min window boundaries from slug: btc-updown-5m-{start_ts}
        # The slug timestamp IS the window start (confirmed via docs + API test)
        try:
            window_start = int(market.slug.rsplit("-", 1)[-1])
        except (ValueError, IndexError):
            window_start = int(market.start_time.timestamp())
        window_end = window_start + 300  # 5-min window

        # Fetch all trades for the market; filter to the 5-min window
        trades = get_trades(market.condition_id, start_ts=window_start, end_ts=window_end)

        # AMM mid-price at 1-min resolution within the window (5 points)
        # This is the fair-value quote the market maker holds (~0.505 until BTC moves)
        amm = get_price_history(market.up_token_id, start_ts=window_start, end_ts=window_end, fidelity=1)
        amm_open = amm[0].p if amm else None

        # Trade-based price summary (actual fills, not AMM mid)
        up_prices = [t.up_price for t in trades]
        trade_open  = up_prices[0]  if up_prices else None
        close_price = up_prices[-1] if up_prices else None
        max_price   = max(up_prices) if up_prices else None
        min_price   = min(up_prices) if up_prices else None

        rows.append({
            "slug": market.slug,
            "title": market.title,
            "start_time": market.start_time,
            "end_time": market.end_time,
            "outcome": market.outcome,
            "resolved_up": market.outcome == "Up",
            "volume": market.volume,
            "open_price": amm_open,      # AMM mid at window open (~0.505, no lookahead)
            "trade_open": trade_open,    # First actual fill in window (may already be 90¢+)
            "close_price": close_price,
            "max_price": max_price,
            "min_price": min_price,
            "n_trades": len(trades),
            "trades": [
                {"t": t.timestamp, "p": t.up_price, "size": t.size, "side": t.side, "outcome": t.outcome}
                for t in trades
            ],
            "up_token_id": market.up_token_id,
            "condition_id": market.condition_id,
        })

        if verbose and (i + 1) % 10 == 0:
            print(f"  {i + 1}/{len(markets)} done...")

        time.sleep(0.1)  # gentle rate limiting

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("end_time").reset_index(drop=True)
    return df
