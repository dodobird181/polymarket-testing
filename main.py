"""
Polymarket BTC 5-min Up/Down — backtesting demo.

Run:
    poetry run python main.py
    poetry run python main.py --n 100   # fetch more markets
"""

import argparse

import pandas as pd

from backtest.engine import (
    AlwaysDownStrategy,
    AlwaysUpStrategy,
    FadeStrategy,
    MomentumStrategy,
    WindowEntryStrategy,
    print_results,
    run_backtest,
    stress_test,
)
from backtest.loader import load_markets


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50, help="Number of markets to fetch")
    parser.add_argument("--stake", type=float, default=10.0, help="USDC staked per trade")
    args = parser.parse_args()

    df = load_markets(n=args.n)

    if df.empty:
        print("No resolved markets found. Try again later.")
        return

    # ── Summary of fetched data ──────────────────────────────────────
    resolved = df[df["outcome"].notna()]
    print(f"\n{'═' * 50}")
    print(f"  BTC 5-min Market Data Summary")
    print(f"{'═' * 50}")
    print(f"  Total markets fetched : {len(df)}")
    print(f"  Resolved              : {len(resolved)}")
    if not resolved.empty:
        up_count = (resolved["outcome"] == "Up").sum()
        dn_count = (resolved["outcome"] == "Down").sum()
        print(f"  Resolved Up           : {up_count} ({up_count/len(resolved):.1%})")
        print(f"  Resolved Down         : {dn_count} ({dn_count/len(resolved):.1%})")
        print(
            f"  Date range            : {resolved['end_time'].min().date()} → {resolved['end_time'].max().date()}"
        )
        print(f"  Avg volume / market   : ${resolved['volume'].mean():.2f}")
        has_price = resolved["open_price"].notna()
        if has_price.any():
            print(f"  Avg open price (Up)   : {resolved.loc[has_price, 'open_price'].mean():.3f}")

    # ── Run strategies ───────────────────────────────────────────────
    strategies = [
        ("Always Up",           AlwaysUpStrategy()),
        ("Always Down",         AlwaysDownStrategy()),
        ("Fade (±2%)",          FadeStrategy(threshold=0.02)),
        ("Momentum (±2%)",      MomentumStrategy(threshold=0.02)),
        ("Window 90-95¢",       WindowEntryStrategy(low=0.90, high=0.95)),
    ]

    print(f"\n{'═' * 50}")
    print(f"  Backtest Results  (stake=${args.stake:.0f} per trade)")
    print(f"{'═' * 50}")

    for name, strat in strategies:
        results = run_backtest(resolved, strat, stake=args.stake)
        print_results(name, results)

    # ── Stress test: Window strategy ─────────────────────────────────
    window_results = run_backtest(resolved, WindowEntryStrategy(), stake=args.stake)
    trades_df = pd.DataFrame(window_results["trades"]).tail(10)
    if not trades_df.empty:
        print(f"\n  Last 10 Window Entry trades:")
        print(trades_df[["title", "signal", "outcome", "entry_price", "pnl"]].to_string(index=False))
    stress_test(window_results, extra_losses=[3, 5, 10], stake=args.stake)

    # ── Stress test: Momentum strategy ───────────────────────────────
    momentum_results = run_backtest(resolved, MomentumStrategy(), stake=args.stake)
    stress_test(momentum_results, extra_losses=[3, 5, 10], stake=args.stake)

    # ── Debug: show trades in the entry window for a sample market ───
    print(f"\n{'═' * 50}")
    print(f"  Trade Debug (first 3 markets, 2–4 min window)")
    print(f"{'═' * 50}")
    for _, row in resolved.head(3).iterrows():
        slug = row["slug"]
        try:
            window_start = int(slug.rsplit("-", 1)[-1])
        except (ValueError, IndexError):
            window_start = 0
        entry_start = window_start + 120
        entry_end   = window_start + 240
        trades = row.get("trades") or []
        in_window = [t for t in trades if entry_start <= t["t"] <= entry_end]
        extreme = [t for t in in_window if t["p"] >= 0.90 or t["p"] <= 0.10]
        print(f"\n  {row['title']}")
        print(f"  outcome={row['outcome']}  n_trades={len(trades)}  in_window={len(in_window)}  extreme={len(extreme)}")
        if in_window:
            print(f"  window prices (Up): {[round(t['p'], 3) for t in in_window]}")


if __name__ == "__main__":
    main()
