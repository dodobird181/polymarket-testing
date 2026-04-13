"""
Bucket wins and losses from a trading log file by time-of-day (30-min EST)
and day of week.

Usage:
    poetry run python analyze_logs.py data/logs/trading.moving_average_grab.jsonl
"""

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from sys import path as systempath
from zoneinfo import ZoneInfo

_root = str(Path(__file__).resolve().parent)
if _root not in systempath:
    systempath.insert(0, _root)

from math import erfc, sqrt

import requests

from src.utils.market_info import Btc5MinMarketOutcome, get_market_outcome_from_slug
from src.utils.redis.polymarket import cache_outcome, get_cached_outcome

_KRAKEN_OHLC = "https://api.kraken.com/0/public/OHLC"
_KRAKEN_PAIR = "XBTUSD"
_KRAKEN_KEY = "XXBTZUSD"
_CANDLE_SECS = 300  # 5-minute candles


def _fetch_candles(timestamps: list[int]) -> dict[int, tuple]:
    """
    Returns {ts: (open, high, low, close)} for each 5-min candle timestamp.
    Batches requests by 60-hour windows (720 candles per Kraken call).
    """
    if not timestamps:
        return {}

    candles: dict[int, tuple] = {}
    window = 720 * _CANDLE_SECS  # 60 hours per call

    sorted_ts = sorted(set((t // _CANDLE_SECS) * _CANDLE_SECS for t in timestamps))
    batch_start = sorted_ts[0]

    while batch_start <= sorted_ts[-1]:
        try:
            resp = requests.get(
                _KRAKEN_OHLC,
                params={"pair": _KRAKEN_PAIR, "interval": 5, "since": batch_start - 1},
                timeout=10,
            )
            resp.raise_for_status()
            for c in resp.json()["result"][_KRAKEN_KEY]:
                ts = int(c[0])
                candles[ts] = (float(c[1]), float(c[2]), float(c[3]), float(c[4]))
        except Exception:
            pass
        batch_start += window

    return candles


EST = ZoneInfo("America/New_York")
_DAYS_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _fetch_outcome(slug: str, cache: dict) -> str | None:
    if slug in cache:
        return cache[slug]
    try:
        cached = get_cached_outcome(slug)
        if cached is not None and cached != Btc5MinMarketOutcome.UNRESOLVED:
            cache[slug] = cached.value
            return cached.value
    except Exception:
        pass
    try:
        outcome = get_market_outcome_from_slug(slug)
        if outcome != Btc5MinMarketOutcome.UNRESOLVED:
            cache[slug] = outcome.value
            try:
                cache_outcome(slug, outcome)
            except Exception:
                pass
            return outcome.value
    except Exception:
        pass
    return None


def _normalize(records: list) -> list:
    """Return a flat list of {is_win, hour, minute, day} dicts."""
    outcome_cache: dict[str, str] = {}
    rows = []

    def _get_trades(state):
        trade = state.get("trade") or state.get("trades")
        if not trade:
            return []
        return [trade] if isinstance(trade, dict) else trade

    for r in records:
        if "id" in r and "strategy_name" in r:
            slug = r["state"]["slug"]
            market_outcome = _fetch_outcome(slug, outcome_cache)
            if market_outcome is None:
                continue
            is_buy = r["side"] == "buy"
            outcome_matches = r["outcome"] == market_outcome
            is_win = outcome_matches if is_buy else not outcome_matches
            dt = datetime.fromtimestamp(r["state"]["start_ts"], tz=EST)
            rows.append({"is_win": is_win, "dt": dt, "direction": r["outcome"]})
        else:
            for trade in _get_trades(r["state"]):
                is_buy = trade.get("side", "buy") == "buy"
                outcome_matches = trade["outcome"] == r["outcome"]
                is_win = outcome_matches if is_buy else not outcome_matches
                dt = datetime.fromtimestamp(r["state"]["start_ts"], tz=EST)
                rows.append({"is_win": is_win, "dt": dt, "direction": trade["outcome"]})

    return rows


def _pvalue(wins: int, total: int, baseline: float) -> str:
    """Two-sided binomial z-test p-value against baseline win rate."""
    if total == 0:
        return "-"
    p_hat = wins / total
    se = sqrt(baseline * (1 - baseline) / total)
    if se == 0:
        return "-"
    z = (p_hat - baseline) / se
    p = erfc(abs(z) / sqrt(2))  # two-sided
    return f"{p:.3f}"


def _table(buckets: dict, ordered_keys: list, label_col: str, baseline: float) -> None:
    print(
        f"\n{label_col:<13} {'Wins':>6} {'Losses':>8} {'Total':>7} {'Win %':>7} {'p-value':>9}  (baseline {baseline*100:.1f}%)"
    )
    print("-" * 57)
    grand_w = grand_l = 0
    for key in ordered_keys:
        if key not in buckets:
            continue
        w = buckets[key]["wins"]
        l = buckets[key]["losses"]
        t = w + l
        pct = f"{w / t * 100:.1f}%" if t else "-"
        pv = _pvalue(w, t, baseline)
        sig = " *" if pv != "-" and float(pv) < 0.05 else ""
        print(f"{key:<13} {w:>6} {l:>8} {t:>7} {pct:>7} {pv:>9}{sig}")
        grand_w += w
        grand_l += l
    grand_t = grand_w + grand_l
    grand_pct = f"{grand_w / grand_t * 100:.1f}%" if grand_t else "-"
    print("-" * 57)
    print(f"{'TOTAL':<13} {grand_w:>6} {grand_l:>8} {grand_t:>7} {grand_pct:>7}")
    print("  * p < 0.05 (uncorrected). Bonferroni threshold for time buckets: p < 0.001")


def analyze(logfile: str) -> None:
    with open(logfile) as f:
        records = [json.loads(l) for l in f if l.strip()]

    if not records:
        print("No records found.")
        return

    print(f"Loaded {len(records)} records from {logfile}")
    print("Fetching market outcomes (may take a moment)...")

    rows = _normalize(records)
    if not rows:
        print("No resolved markets found.")
        return

    # Attach tail signal from Kraken OHLC
    print("Fetching candle data from Kraken...")
    raw_ts = [int(row["dt"].timestamp()) for row in rows]
    candle_map = _fetch_candles(raw_ts)
    for row in rows:
        ts_key = (int(row["dt"].timestamp()) // _CANDLE_SECS) * _CANDLE_SECS
        if ts_key in candle_map:
            o, h, l, c = candle_map[ts_key]
            body_top = max(o, c)
            body_bottom = min(o, c)
            upper = h - body_top
            lower = body_bottom - l
            rng = h - l
            row["tail_signal"] = (upper - lower) / rng if rng > 0 else 0.0
        else:
            row["tail_signal"] = None

    by_time: dict[tuple, dict] = defaultdict(lambda: {"wins": 0, "losses": 0})
    by_day: dict[str, dict] = defaultdict(lambda: {"wins": 0, "losses": 0})
    by_direction: dict[str, dict] = defaultdict(lambda: {"wins": 0, "losses": 0})
    by_tail: dict[str, dict] = defaultdict(lambda: {"wins": 0, "losses": 0})

    for row in rows:
        dt = row["dt"]
        bucket_minute = (dt.minute // 30) * 30
        time_key = (dt.hour, bucket_minute)
        day_key = dt.strftime("%A")
        slot = "wins" if row["is_win"] else "losses"
        by_time[time_key][slot] += 1
        by_day[day_key][slot] += 1
        by_direction[row["direction"].upper()][slot] += 1
        if row["tail_signal"] is not None:
            sig = row["tail_signal"]
            direction = row["direction"]  # "up" or "down"
            if abs(sig) <= 0.1:
                tail_key = "Balanced"
            elif (sig < -0.1 and direction == "up") or (sig > 0.1 and direction == "down"):
                tail_key = "Aligned"  # tail signal agrees with bet
            else:
                tail_key = "Misaligned"  # tail signal opposes bet
            by_tail[tail_key][slot] += 1

    # Build sorted 30-min labels: (0,0) → "12:00 AM", (0,30) → "12:30 AM", ...
    def _label(h, m):
        return datetime(2000, 1, 1, h, m).strftime("%I:%M %p").lstrip("0") or "12:00 AM"

    all_slots = [(h, m) for h in range(24) for m in (0, 30)]
    time_labels = {k: _label(*k) for k in all_slots}
    labelled_time = {time_labels[k]: v for k, v in by_time.items()}
    ordered_time = [time_labels[k] for k in all_slots if k in by_time]

    total_wins = sum(v["wins"] for v in by_time.values())
    total_trades = total_wins + sum(v["losses"] for v in by_time.values())
    baseline = total_wins / total_trades if total_trades else 0

    print("\n=== BY TIME OF DAY (EST, 30-min buckets) ===")
    _table(labelled_time, ordered_time, "Time (EST)", baseline)

    print("\n=== BY DAY OF WEEK ===")
    _table(by_day, _DAYS_ORDER, "Day", baseline)

    print("\n=== BY BET DIRECTION ===")
    _table(by_direction, ["UP", "DOWN"], "Direction", baseline)

    print("\n=== BY TAIL ALIGNMENT WITH BET ===")
    print("  Aligned    = lower tail + bet UP, or upper tail + bet DOWN")
    print("  Misaligned = lower tail + bet DOWN, or upper tail + bet UP")
    print("  Balanced   = tail signal too small to classify (|signal| <= 0.1)")
    _table(by_tail, ["Aligned", "Misaligned", "Balanced"], "Alignment", baseline)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bucket wins/losses by time of day (30-min EST) and day of week.")
    parser.add_argument("logfile", help="Path to the JSONL trading log file.")
    args = parser.parse_args()
    analyze(args.logfile)
