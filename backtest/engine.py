"""
Backtesting engine for Polymarket BTC 5-min up/down markets.

Usage:
    from backtest.engine import run_backtest, AlwaysUpStrategy, FadeStrategy

    results = run_backtest(df, AlwaysUpStrategy(), stake=10.0)
    print(results)

Strategy interface:
    Implement signal(row) → "Up", "Down", or "SKIP"
    row is a pandas Series with columns from loader.load_markets()

PnL model (binary prediction market):
    - You bet `stake` USDC on your chosen outcome at the open_price.
    - If correct: payout = stake / open_price  →  profit = payout - stake
    - If wrong:   loss   = -stake
    - SKIP:       no position, no PnL
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

import pandas as pd

Signal = Literal["Up", "Down", "SKIP"]


class Strategy(ABC):
    """Base class — implement signal() to define a strategy."""

    @abstractmethod
    def signal(self, row: pd.Series) -> Signal:
        """
        Given a market row (as returned by loader.load_markets()),
        return "Up", "Down", or "SKIP".

        Available fields at signal time (no lookahead):
          open_price   – first quoted price in the 5-min window
          trades       – list of {"t": unix_ts, "p": up_price, "size": usdc, "side": str, "outcome": str}
          volume       – total USDC traded in the market
          start_time   – window open datetime
          end_time     – window close datetime
          slug         – btc-updown-5m-{end_unix_ts}
          title        – human label
        """
        ...

    def get_entry_price(self, row: pd.Series) -> float:
        """
        Price at which this strategy enters its position.
        Override if your strategy enters mid-window at a non-open price.
        Default: use the first price sample (open).
        """
        return row.get("open_price") or 0.5


class AlwaysUpStrategy(Strategy):
    """Baseline: always bet Up. Useful as a reference to check market bias."""

    def signal(self, row: pd.Series) -> Signal:
        return "Up"


class AlwaysDownStrategy(Strategy):
    """Baseline: always bet Down."""

    def signal(self, row: pd.Series) -> Signal:
        return "Down"


class FadeStrategy(Strategy):
    """
    Fade the market: if Up is priced above 0.5 (market leans Up), bet Down.
    If Up is priced below 0.5 (market leans Down), bet Up.
    Skip markets trading exactly at 0.5 (no edge).
    """

    def __init__(self, threshold: float = 0.02):
        self.threshold = threshold

    def signal(self, row: pd.Series) -> Signal:
        p = row.get("open_price")
        if p is None:
            return "SKIP"
        if p > 0.5 + self.threshold:
            return "Down"
        if p < 0.5 - self.threshold:
            return "Up"
        return "SKIP"


class MomentumStrategy(Strategy):
    """
    Follow the market: if Up is priced above 0.5, bet Up (momentum).
    """

    def __init__(self, threshold: float = 0.02):
        self.threshold = threshold

    def signal(self, row: pd.Series) -> Signal:
        p = row.get("open_price")
        if p is None:
            return "SKIP"
        if p > 0.5 + self.threshold:
            return "Up"
        if p < 0.5 - self.threshold:
            return "Down"
        return "SKIP"


class WindowEntryStrategy(Strategy):
    """
    Enter between minute 2 and minute 4 of the 5-min window using real trades.

    Scans actual on-chain fills (from data-api.polymarket.com/trades) for the
    first trade where either the Up or Down token printed between `low` and `high`.

    - Up-token price in [low, high]  → bet "Up"
    - Down-token price in [low, high] (= Up price in [1-high, 1-low]) → bet "Down"
    - No qualifying trade found       → SKIP

    The actual fill price at entry is used for PnL (not the AMM open_price).
    """

    def __init__(self, low: float = 0.90, high: float = 0.95):
        self.low = low
        self.high = high
        self._entry_price: float = 0.5

    def signal(self, row: pd.Series) -> Signal:
        trades = row.get("trades") or []
        slug = row.get("slug", "")

        # Slug timestamp = window start: btc-updown-5m-{start_ts}
        try:
            window_start = int(slug.rsplit("-", 1)[-1])
        except (ValueError, IndexError):
            return "SKIP"

        entry_start = window_start + 120  # 2 min into window
        entry_end = window_start + 240  # 4 min into window

        for trade in trades:
            t, p = trade["t"], trade["p"]  # p is already normalised to Up-token price
            if not (entry_start <= t <= entry_end):
                continue
            if self.low <= p <= self.high:
                self._entry_price = p
                return "Up"
            if self.low <= (1 - p) <= self.high:
                self._entry_price = 1 - p
                return "Down"

        return "SKIP"

    def get_entry_price(self, row: pd.Series) -> float:
        return self._entry_price


def run_backtest(
    df: pd.DataFrame,
    strategy: Strategy,
    stake: float = 10.0,
) -> dict:
    """
    Simulate trading strategy on a DataFrame of resolved markets.

    Args:
        df:       DataFrame from backtest.loader.load_markets()
        strategy: A Strategy instance
        stake:    USDC risked per trade

    Returns:
        dict with keys:
          num_markets   total markets in df
          num_trades    markets where signal != SKIP
          num_wins      correct predictions
          num_losses    incorrect predictions
          win_rate      num_wins / num_trades
          total_pnl     cumulative profit/loss in USDC
          roi           total_pnl / (num_trades * stake)
          avg_pnl       total_pnl / num_trades
          trades        list of per-trade dicts
    """
    trades = []

    for _, row in df.iterrows():
        sig = strategy.signal(row)
        if sig == "SKIP":
            continue
        if row["outcome"] is None:
            continue

        correct = sig == row["outcome"]
        entry_price = strategy.get_entry_price(row)

        if correct:
            pnl = (stake / entry_price) - stake
        else:
            pnl = -stake

        trades.append(
            {
                "slug": row["slug"],
                "title": row["title"],
                "end_time": row["end_time"],
                "signal": sig,
                "outcome": row["outcome"],
                "entry_price": entry_price,
                "correct": correct,
                "pnl": pnl,
            }
        )

    num_trades = len(trades)
    num_wins = sum(1 for t in trades if t["correct"])
    total_pnl = sum(t["pnl"] for t in trades)

    return {
        "num_markets": len(df),
        "num_trades": num_trades,
        "num_wins": num_wins,
        "num_losses": num_trades - num_wins,
        "win_rate": num_wins / num_trades if num_trades else 0.0,
        "total_pnl": total_pnl,
        "roi": total_pnl / (num_trades * stake) if num_trades else 0.0,
        "avg_pnl": total_pnl / num_trades if num_trades else 0.0,
        "trades": trades,
    }


def print_results(name: str, results: dict) -> None:
    print(f"\n{'─' * 50}")
    print(f"  Strategy: {name}")
    print(f"{'─' * 50}")
    print(f"  Markets:   {results['num_markets']}")
    print(f"  Trades:    {results['num_trades']}")
    print(f"  Wins:      {results['num_wins']}  |  Losses: {results['num_losses']}")
    print(f"  Win rate:  {results['win_rate']:.1%}")
    print(f"  Total PnL: ${results['total_pnl']:+.2f}")
    print(f"  ROI:       {results['roi']:+.1%}")
    print(f"  Avg PnL:   ${results['avg_pnl']:+.2f} per trade")
    print(f"{'─' * 50}")


def stress_test(results: dict, extra_losses: list[int], stake: float = 10.0) -> None:
    """
    Flip the N best-paying wins into losses and recompute PnL.

    This answers: "how fragile is this strategy?" — if real-world slippage,
    spread, or market microstructure costs us N additional losses vs backtest,
    do we still profit?

    We flip the highest-payout wins first (worst-case scenario) because those
    are the trades where our fill assumption is most aggressive (e.g. entering
    at exactly 90¢ on a fast-moving market may not be realistic).

    Args:
        results:      Output of run_backtest().
        extra_losses: List of N values to stress-test (e.g. [3, 5, 10]).
        stake:        Must match the stake used in run_backtest().
    """
    trades = results["trades"]
    num_trades = results["num_trades"]
    if num_trades == 0:
        print("  No trades to stress-test.")
        return

    # Base metrics
    base_wins  = results["num_wins"]
    base_pnl   = results["total_pnl"]
    base_wr    = results["win_rate"]

    # Wins sorted by payout descending (flip the most optimistic ones first)
    winning_trades = sorted(
        [t for t in trades if t["correct"]],
        key=lambda t: (stake / t["entry_price"]) - stake,
        reverse=True,
    )

    print(f"\n{'─' * 50}")
    print(f"  Stress Test  (base: {base_wins}W / {num_trades - base_wins}L, "
          f"WR={base_wr:.1%}, PnL=${base_pnl:+.2f})")
    print(f"{'─' * 50}")
    print(f"  {'Extra losses':>14}  {'Wins':>5}  {'Win rate':>9}  {'Total PnL':>10}  {'ROI':>7}  {'Status':>8}")
    print(f"  {'─'*14}  {'─'*5}  {'─'*9}  {'─'*10}  {'─'*7}  {'─'*8}")

    # Print baseline row
    roi = base_pnl / (num_trades * stake)
    status = "PROFIT" if base_pnl > 0 else "LOSS"
    print(f"  {'0 (baseline)':>14}  {base_wins:>5}  {base_wr:>9.1%}  ${base_pnl:>+9.2f}  {roi:>+7.1%}  {status:>8}")

    for n in extra_losses:
        to_flip = winning_trades[:n]
        # Each flipped win: remove its profit, add a full loss
        lost_profit = sum((stake / t["entry_price"]) - stake for t in to_flip)
        extra_loss  = stake * len(to_flip)
        adj_pnl  = base_pnl - lost_profit - extra_loss
        adj_wins = base_wins - len(to_flip)
        adj_wr   = adj_wins / num_trades
        adj_roi  = adj_pnl / (num_trades * stake)
        status   = "PROFIT" if adj_pnl > 0 else "LOSS"
        note     = f"  ← only {len(to_flip)} flipped" if len(to_flip) < n else ""
        print(f"  {n:>14}  {adj_wins:>5}  {adj_wr:>9.1%}  ${adj_pnl:>+9.2f}  {adj_roi:>+7.1%}  {status:>8}{note}")

    print(f"{'─' * 50}")
