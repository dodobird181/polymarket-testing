"""
Forward-test (paper trading) monitor for the BTC 5-min Window strategy.

Watches the live market in real time. When a qualifying trade is detected
(a fill at 90–95¢ in the 2–4 min window), it logs the "entry" and tracks
the resolution — no real money involved.

Run:poetry run python -m live.monitor
    poetry run python -m live.monitor
    poetry run python -m live.monitor --low 0.85 --high 0.95  # wider band

How it works:
    1. Every 5 seconds, fetch the current active BTC 5-min market.
    2. Detect when we're inside the entry window (min 2 – min 4).
    3. Poll the data-api for new trades. If a fill prints at 90–95¢, log it.
    4. Wait for resolution. Compare to the entry direction. Log PnL.

Important caveats vs live trading:
    - Fill assumption: you'd need a resting limit order already in the book.
      Reacting to a trade after seeing it adds 1–5s latency — the fill is gone.
    - Slippage: your order size moves the price. $10 probably fine; $1K+ matters.
    - No redemption fees modelled here (Polymarket charges ~2% on winnings).
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from backtest.engine import WindowEntryStrategy
from polymarket.clob_client import get_trades
from polymarket.gamma_client import get_market_by_slug

LOG_FILE = Path("live/forward_test_log.jsonl")
POLL_INTERVAL = 5  # seconds between trade checks
WINDOW_SECS = 300  # 5-min market window length


def _current_window_end_ts() -> int:
    """Return the end timestamp of the current (or just-started) 5-min window."""
    now = int(time.time())
    # Each window ends at a unix ts divisible by 300
    # Current window: (now // 300) * 300 + 300
    return ((now // WINDOW_SECS) + 1) * WINDOW_SECS


def _elapsed(window_end_ts: int) -> int:
    """Seconds elapsed since the window started."""
    window_start_ts = window_end_ts - WINDOW_SECS
    return int(time.time()) - window_start_ts


def _log(entry: dict) -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"  [LOG] {entry}")


def _print_summary() -> None:
    """Print PnL summary from the log file."""
    if not LOG_FILE.exists():
        print("No forward-test log found.")
        return

    entries = [json.loads(l) for l in LOG_FILE.read_text().splitlines() if l]
    resolved = [e for e in entries if e.get("resolved")]

    if not resolved:
        print(f"  {len(entries)} entries logged, none resolved yet.")
        return

    wins = sum(1 for e in resolved if e["correct"])
    losses = len(resolved) - wins
    stake = resolved[0].get("stake", 10.0)
    pnl = sum((stake / e["entry_price"]) - stake if e["correct"] else -stake for e in resolved)
    print(f"\n  Forward-test summary ({len(resolved)} resolved trades):")
    print(f"    Wins / Losses : {wins} / {losses}  ({wins/len(resolved):.1%} WR)")
    print(f"    Total PnL     : ${pnl:+.2f}")
    print(f"    ROI           : {pnl / (len(resolved) * stake):+.1%}")


def watch(low: float = 0.90, high: float = 0.95, stake: float = 10.0, dry_run: bool = True) -> None:
    print(f"Starting forward-test monitor  [low={low}, high={high}, stake=${stake}]")
    print(f"Log file: {LOG_FILE.resolve()}")
    print(f"Press Ctrl+C to stop.\n")

    seen_trade_ts: set[int] = set()  # avoid double-logging same fill
    active_entry: dict | None = None  # open position waiting for resolution

    while True:
        now = int(time.time())
        end_ts = _current_window_end_ts()
        start_ts = end_ts - WINDOW_SECS
        slug = f"btc-updown-5m-{end_ts}"
        elapsed = _elapsed(end_ts)

        phase = (
            "pre-window"
            if elapsed < 0
            else (
                "window-open"
                if elapsed < 120
                else "entry-window" if elapsed < 240 else "late-window" if elapsed < WINDOW_SECS else "resolving"
            )
        )

        # ── Resolve previous entry if we crossed into a new window ──
        if active_entry and active_entry["end_ts"] != end_ts:
            market = get_market_by_slug(active_entry["slug"])
            if market and market.resolved:
                active_entry["outcome"] = market.outcome
                active_entry["resolved"] = True
                active_entry["correct"] = market.outcome == active_entry["signal"]
                _log(active_entry)
                active_entry = None

        # ── Only look for entries during the entry window ────────────
        latest_up_p = None
        if phase == "entry-window" and active_entry is None:
            trades = get_trades(
                get_market_by_slug(slug).condition_id if (m := get_market_by_slug(slug)) else "",
                start_ts=start_ts + 120,
                end_ts=start_ts + 240,
            )
            for trade in trades:
                if trade.timestamp in seen_trade_ts:
                    continue
                seen_trade_ts.add(trade.timestamp)

                up_p = trade.up_price
                latest_up_p = up_p
                signal = None
                entry_price = None
                if low <= up_p <= high:
                    signal, entry_price = "Up", up_p
                elif low <= (1 - up_p) <= high:
                    signal, entry_price = "Down", 1 - up_p

                if signal:
                    active_entry = {
                        "ts": now,
                        "slug": slug,
                        "end_ts": end_ts,
                        "signal": signal,
                        "entry_price": entry_price,
                        "stake": stake,
                        "resolved": False,
                        "outcome": None,
                        "correct": None,
                        "dry_run": dry_run,
                    }
                    print(f"\n  *** SIGNAL {signal} @ {entry_price:.3f}  ({'DRY RUN' if dry_run else 'LIVE'}) ***")
                    _log({**active_entry, "event": "entry"})
                    break  # one trade per window

        print(
            f"\r  [{datetime.now(timezone.utc).strftime('%H:%M:%S')}]  "
            f"{slug}  elapsed={elapsed}s  phase={phase}  up={latest_up_p}  down={latest_up_p - 100 if latest_up_p is not None else None}",
            end="",
            flush=True,
        )

        time.sleep(POLL_INTERVAL)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--low", type=float, default=0.90)
    parser.add_argument("--high", type=float, default=0.95)
    parser.add_argument("--stake", type=float, default=10.0)
    parser.add_argument("--summary", action="store_true", help="Print log summary and exit")
    args = parser.parse_args()

    if args.summary:
        _print_summary()
        return

    try:
        watch(low=args.low, high=args.high, stake=args.stake, dry_run=True)
    except KeyboardInterrupt:
        print("\n\nStopped. Final summary:")
        _print_summary()


if __name__ == "__main__":
    main()
