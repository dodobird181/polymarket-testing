"""
Plots BTC price over a Polymarket 5-min window with strategy buy markers.

Usage: python replay.py <logfile.jsonl> <slug>
Example: python replay.py strategy_logs/my_strategy.jsonl btc-updown-5m-1774143000
"""

import json
import sys

import matplotlib.pyplot as plt
import requests

KRAKEN_BASE = "https://api.kraken.com/0/public"
KRAKEN_PAIR = "XBTUSD"
KRAKEN_RESULT_KEY = "XXBTZUSD"
WINDOW_SECS = 300
HISTORY_SECS = 900  # 3 windows of context before the target window
BUCKET_SECS = 5


def fetch_trades_in_window(start_ts: int, end_ts: int) -> list[tuple[float, float]]:
    """Fetch all BTC/USD trades from Kraken in [start_ts, end_ts). Returns (timestamp, price) pairs."""
    trades = []
    since_ns = start_ts * 10**9

    while True:
        resp = requests.get(
            f"{KRAKEN_BASE}/Trades",
            params={"pair": KRAKEN_PAIR, "since": since_ns},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        batch = data["result"][KRAKEN_RESULT_KEY]
        last_ns = int(data["result"]["last"])

        for trade in batch:
            ts = float(trade[2])
            if ts >= end_ts:
                return trades
            trades.append((ts, float(trade[0])))

        if not batch or last_ns / 10**9 >= end_ts:
            break
        since_ns = last_ns

    return trades


def bucket_prices(trades: list[tuple[float, float]], start_ts: int) -> tuple[list[int], list[float]]:
    """Aggregate trades into BUCKET_SECS-wide buckets using last price. Forward-fills gaps.
    x-axis is seconds relative to start_ts (negative = history, 0..300 = target window)."""
    buckets: dict[int, float] = {}
    for ts, price in trades:
        b = int((ts - start_ts) // BUCKET_SECS) * BUCKET_SECS
        buckets[b] = price

    times, prices = [], []
    last_price = None
    for t in range(-HISTORY_SECS, WINDOW_SECS, BUCKET_SECS):
        if t in buckets:
            last_price = buckets[t]
        if last_price is not None:
            times.append(t)
            prices.append(last_price)

    return times, prices


def load_log_entry(logfile: str, slug: str) -> dict | None:
    """Return the last JSONL entry matching the given slug."""
    match = None
    with open(logfile) as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("state", {}).get("slug") == slug:
                match = entry
    return match


def price_at(times: list[int], prices: list[float], t: float) -> float:
    """Return the price closest to time t (seconds into window)."""
    return prices[min(range(len(times)), key=lambda i: abs(times[i] - t))]


def main():
    if len(sys.argv) != 3:
        print("Usage: python replay.py <logfile.jsonl> <slug>")
        sys.exit(1)

    logfile, slug = sys.argv[1], sys.argv[2]
    start_ts = int(slug.split("-")[-1])
    end_ts = start_ts + WINDOW_SECS

    print(f"Fetching Kraken trades for {slug} (including {HISTORY_SECS}s of context)...")
    trades = fetch_trades_in_window(start_ts - HISTORY_SECS, end_ts)
    print(f"  {len(trades)} trades fetched")

    times, prices = bucket_prices(trades, start_ts)

    entry = load_log_entry(logfile, slug)
    if entry is None:
        print(f"No log entry found for slug '{slug}'")
        sys.exit(1)

    buys = [t for t in entry["state"]["trades"] if t["side"] == "buy"]
    buy_times = [t["dt"] - start_ts for t in buys]
    buy_prices = [price_at(times, prices, bt) for bt in buy_times]

    # --- plot ---
    fig, ax = plt.subplots(figsize=(14, 6))
    fig.patch.set_facecolor("#0e1117")
    ax.set_facecolor("#0e1117")

    ax.plot(times, prices, color="#4a9eff", linewidth=1.5, label="BTC/USD (Kraken)")

    # Window boundary lines + per-window delta annotations
    boundaries = list(range(-HISTORY_SECS, WINDOW_SECS + 1, WINDOW_SECS))
    for i, x in enumerate(boundaries):
        is_target = x == 0
        ax.axvline(
            x=x, color="white", linewidth=1,
            linestyle="--" if is_target else ":",
            alpha=0.6 if is_target else 0.35,
        )

    # Annotate each window segment with price delta
    for i in range(len(boundaries) - 1):
        w_start, w_end = boundaries[i], boundaries[i + 1]
        p_open = price_at(times, prices, w_start)
        p_close = price_at(times, prices, w_end - BUCKET_SECS)
        delta = p_close - p_open
        color = "#00cc66" if delta >= 0 else "#ff4455"
        sign = "+" if delta >= 0 else ""
        mid_x = (w_start + w_end) / 2
        ax.text(
            mid_x, 0.97,
            f"{sign}${delta:.0f}",
            color=color, fontsize=9, ha="center", va="top",
            transform=ax.get_xaxis_transform(),
        )

    if buys:
        ax.scatter(buy_times, buy_prices, color="#00ff88", s=120, zorder=5,
                   label=f"Buy ({len(buys)})")
        for bt, bp, b in zip(buy_times, buy_prices, buys):
            ax.annotate(
                f"${b['price']:.3f}",
                xy=(bt, bp),
                xytext=(6, 6),
                textcoords="offset points",
                color="#00ff88",
                fontsize=8,
            )

    outcome = entry.get("outcome", "unknown")
    ax.set_title(f"{slug}  •  outcome: {outcome}", color="white", fontsize=12)
    ax.set_xlabel("Seconds relative to window start", color="white")
    ax.set_ylabel("BTC Price (USD)", color="white")
    ax.tick_params(colors="white")
    ax.legend(facecolor="#1e1e2e", labelcolor="white", edgecolor="#444")
    for spine in ax.spines.values():
        spine.set_edgecolor("#333")

    outfile = f"{slug}.png"
    plt.tight_layout()
    plt.savefig(outfile, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Saved to {outfile}")
    plt.show()


if __name__ == "__main__":
    main()
