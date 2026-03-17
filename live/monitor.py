"""
Forward-test (paper trading) monitor for the BTC 5-min Window strategy.

Run:
    poetry run python -m live.monitor
    poetry run python -m live.monitor --low 0.85 --high 0.95
    poetry run python -m live.monitor --summary

Slug format confirmed: btc-updown-5m-{window_START_ts}
  window_start = (now // 300) * 300
  window_end   = window_start + 300
  entry window = [window_start + 120, window_start + 240]  (min 2 → min 4)
"""

from __future__ import annotations

import argparse
import json
import time
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

from polymarket.clob_client import Trade, get_trades
from polymarket.gamma_client import get_market_by_slug
from polymarket.models import Market

LOG_FILE = Path("live/forward_test_log.jsonl")
POLL_INTERVAL = 5  # seconds between polls
WINDOW_SECS = 300  # 5-min window


# ── helpers ──────────────────────────────────────────────────────────────────


def current_window_start() -> int:
    """Unix timestamp of the current 5-min window's start (divisible by 300)."""
    return (int(time.time()) // WINDOW_SECS) * WINDOW_SECS


def elapsed(window_start: int) -> int:
    return int(time.time()) - window_start


def window_phase(window_start: int) -> str:
    s = elapsed(window_start)
    if s < 0:
        return "pre"
    if s < 120:
        return "open"  # min 0–2
    if s < 240:
        return "entry"  # min 2–4  ← strategy fires here
    if s < WINDOW_SECS:
        return "late"  # min 4–5
    return "resolving"


def new_trades(
    condition_id: str,
    seen: set[int],
    start_ts: int,
    end_ts: int,
    limit: int = 50,
) -> Iterator[Trade]:
    """Yield trades in [start_ts, end_ts] that haven't been seen before.

    Uses a small limit by default — the data-api has a freshness lag at large
    limits and won't return trades from the last ~30s when limit >= 500.
    """
    for trade in get_trades(condition_id, start_ts=start_ts, end_ts=end_ts, limit=limit):
        if trade.timestamp not in seen:
            seen.add(trade.timestamp)
            yield trade


def _log(entry: dict) -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)
    with LOG_FILE.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"\n  [LOG] {entry}")


def _print_summary() -> None:
    if not LOG_FILE.exists():
        print("No forward-test log found.")
        return
    entries = [json.loads(l) for l in LOG_FILE.read_text().splitlines() if l]
    resolved = [e for e in entries if e.get("resolved")]
    if not resolved:
        print(f"  {len(entries)} entries logged, none resolved yet.")
        return
    stake = resolved[0].get("stake", 10.0)
    wins = sum(1 for e in resolved if e["correct"])
    losses = len(resolved) - wins
    pnl = sum((stake / e["entry_price"]) - stake if e["correct"] else -stake for e in resolved)
    print(f"\n  Forward-test summary ({len(resolved)} resolved trades):")
    print(f"    Wins / Losses : {wins} / {losses}  ({wins/len(resolved):.1%} WR)")
    print(f"    Total PnL     : ${pnl:+.2f}")
    print(f"    ROI           : {pnl / (len(resolved) * stake):+.1%}")


def watch(low: float = 0.90, high: float = 0.95, stake: float = 10.0) -> None:
    print(f"Starting forward-test monitor  [band={low}–{high}, stake=${stake}]")
    print(f"Log: {LOG_FILE.resolve()}\nCtrl+C to stop.\n")

    seen: set[int] = set()  # trade timestamps seen this window
    active_entry: dict | None = None  # open simulated position
    cached_market: Market | None = None  # fetched once per window
    last_win: int = -1
    latest_up_p: float | None = None  # most recent Up price seen

    while True:
        ws = current_window_start()
        slug = f"btc-updown-5m-{ws}"
        phase = window_phase(ws)

        # ── New window: reset per-window state ───────────────────────
        if ws != last_win:
            seen.clear()
            cached_market = None
            latest_up_p = None
            last_win = ws

        # ── Lazy-load market metadata once per window ─────────────────
        if cached_market is None:
            cached_market = get_market_by_slug(slug)

        # ── Resolve previous entry once we're in a new window ─────────
        if active_entry and active_entry["ws"] != ws:
            prev_market = get_market_by_slug(active_entry["slug"])
            if prev_market and prev_market.resolved:
                active_entry.update(
                    {
                        "outcome": prev_market.outcome,
                        "resolved": True,
                        "correct": prev_market.outcome == active_entry["signal"],
                    }
                )
                _log(active_entry)
                active_entry = None

        # ── Scan ALL new trades this window (for live price + signals) ─
        if cached_market:
            for trade in new_trades(
                cached_market.condition_id,
                seen,
                start_ts=ws,
                end_ts=ws + WINDOW_SECS,
            ):
                up_p = trade.up_price
                latest_up_p = up_p
                trade_ts = datetime.fromtimestamp(trade.timestamp, tz=timezone.utc).strftime("%H:%M:%S")
                print(
                    f"\n  [TRADE] {trade_ts}  {trade.outcome} @ {trade.price:.3f}  "
                    f"up={up_p:.3f}  dn={1 - up_p:.3f}  ${trade.size:.0f}  {trade.side}"
                )

                # only signal during the entry window, one position per window
                if phase == "entry" and active_entry is None:
                    if low <= up_p <= high:
                        signal, entry_price = "Up", up_p
                    elif low <= (1 - up_p) <= high:
                        signal, entry_price = "Down", 1 - up_p
                    else:
                        continue

                    active_entry = {
                        "ws": ws,
                        "slug": slug,
                        "signal": signal,
                        "entry_price": entry_price,
                        "stake": stake,
                        "resolved": False,
                        "outcome": None,
                        "correct": None,
                    }
                    print(f"  *** SIGNAL {signal} @ {entry_price:.3f} ***")
                    _log({**active_entry, "event": "entry"})

        # ── Status line ───────────────────────────────────────────────
        price_str = f"  up={latest_up_p:.3f}  dn={1 - latest_up_p:.3f}" if latest_up_p is not None else ""
        pos_str = f"  pos={active_entry['signal']}@{active_entry['entry_price']:.3f}" if active_entry else ""
        print(
            f"\r  [{datetime.now(timezone.utc).strftime('%H:%M:%S')}]  "
            f"{slug}  +{elapsed(ws)}s  [{phase}]{price_str}{pos_str}   "
        )

        time.sleep(POLL_INTERVAL)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--low", type=float, default=0.90)
    parser.add_argument("--high", type=float, default=0.95)
    parser.add_argument("--stake", type=float, default=10.0)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    if args.summary:
        _print_summary()
        return

    try:
        watch(low=args.low, high=args.high, stake=args.stake)
    except KeyboardInterrupt:
        print("\n\nStopped.")
        _print_summary()


if __name__ == "__main__":
    main()
