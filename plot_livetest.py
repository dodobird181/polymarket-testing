import json
from datetime import datetime

import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt

JSONL_FILE = "stoploss_strat_35.jsonl"

records = []
with open(JSONL_FILE) as f:
    for line in f:
        line = line.strip()
        if line:
            records.append(json.loads(line))


def get_trades(state: dict) -> list:
    trade = state.get("trade") or state.get("trades")
    if not trade:
        return []
    if isinstance(trade, dict):
        return [trade]
    return trade


traded = [r for r in records if get_trades(r["state"])]

wins, losses = [], []
for r in traded:
    for trade in get_trades(r["state"]):
        outcome_matches = trade["outcome"] == r["outcome"]
        is_buy = trade.get("side", "buy") == "buy"
        # BUY: win if outcome matches (you hold winning shares)
        # SELL: win if outcome does NOT match (you sold away losing shares)
        is_win = outcome_matches if is_buy else not outcome_matches
        if is_buy:
            pnl = trade["amount"] * (1 - trade["price"]) if is_win else -trade["amount"] * trade["price"]
        else:
            # SELL: you received amount*price upfront; win = shares expired worthless, loss = shares paid out $1
            pnl = trade["amount"] * trade["price"] if is_win else -trade["amount"] * (1 - trade["price"])
        entry = {
            "dt": datetime.fromtimestamp(r["state"]["start_ts"]),
            "amount": trade["amount"],
            "price": trade["price"],
            "pnl": pnl,
            "slug": r["state"]["slug"],
        }
        (wins if is_win else losses).append(entry)

num_wins = len(wins)
num_losses = len(losses)
num_trades = num_wins + num_losses
win_rate = (num_wins / num_trades * 100) if num_trades > 0 else 0
total_markets = len({r["state"]["slug"] for r in records})
avg_price = sum(t["price"] for r in traded for t in get_trades(r["state"])) / num_trades if num_trades > 0 else 0

total_pnl = sum(e["amount"] * (1 - e["price"]) for e in wins) + sum(-e["amount"] * e["price"] for e in losses)
total_invested = sum(e["amount"] * e["price"] for e in wins + losses)
pct_return = (total_pnl / total_invested * 100) if total_invested > 0 else 0

fig = plt.figure(figsize=(12, 8))
fig.patch.set_facecolor("#1a1a2e")
gs = gridspec.GridSpec(2, 1, height_ratios=[1, 4], hspace=0.4)

# --- Stats row ---
ax_stats = fig.add_subplot(gs[0])
ax_stats.set_facecolor("#1a1a2e")
ax_stats.axis("off")

pnl_color = "#00cc66" if total_pnl >= 0 else "#ff4444"
stats = [
    ("Win Rate", f"{win_rate:.1f}%", "white"),
    ("Wins", str(num_wins), "white"),
    ("Losses", str(num_losses), "white"),
    ("Trades", str(num_trades), "white"),
    ("Markets", str(total_markets), "white"),
    ("Avg Price", f"{avg_price:.3f}", "white"),
    ("P&L", f"${total_pnl:+.2f}", pnl_color),
    ("Return", f"{pct_return:+.1f}%", pnl_color),
]

for i, (label, value, color) in enumerate(stats):
    x = 0.055 + i * 0.127
    box = dict(boxstyle="round,pad=0.5", facecolor="#16213e", edgecolor="#4a4a8a", linewidth=1.5)
    ax_stats.text(
        x,
        0.65,
        value,
        transform=ax_stats.transAxes,
        fontsize=18,
        fontweight="bold",
        color=color,
        ha="center",
        va="center",
        bbox=box,
    )
    ax_stats.text(
        x, 0.15, label, transform=ax_stats.transAxes, fontsize=10, color="#aaaacc", ha="center", va="center"
    )

ax_stats.set_title("Polymarket Live Trading Results", color="white", fontsize=15, pad=10)

# --- Scatter plot ---
ax = fig.add_subplot(gs[1])
ax.set_facecolor("#0f0f23")
ax.tick_params(colors="white")
ax.spines[:].set_color("#4a4a8a")

if wins:
    wx = [e["dt"] for e in wins]
    wy = [e["amount"] for e in wins]
    ax.scatter(wx, wy, c="#00cc66", s=120, zorder=3, label=f"Win ({num_wins})", edgecolors="#009944", linewidths=1)

if losses:
    lx = [e["dt"] for e in losses]
    ly = [e["amount"] for e in losses]
    ax.scatter(
        lx, ly, c="#ffcc00", s=120, zorder=3, label=f"Loss ({num_losses})", edgecolors="#cc9900", linewidths=1
    )

all_trades_sorted = sorted(wins + losses, key=lambda e: e["dt"])
ax_pnl = ax.twinx()
ax_pnl.tick_params(colors="#a78bfa")
ax_pnl.spines[:].set_color("#4a4a8a")
ax_pnl.set_ylabel("Cumulative P&L ($)", color="#a78bfa", labelpad=8)
if all_trades_sorted:
    pnl_dts = [e["dt"] for e in all_trades_sorted]
    cumulative_pnl = []
    running = 0
    for e in all_trades_sorted:
        running += e["pnl"]
        cumulative_pnl.append(running)

    ax_pnl.plot(pnl_dts, cumulative_pnl, color="#a78bfa", linewidth=2, zorder=2, label="Cumulative P&L")
    ax_pnl.axhline(0, color="#a78bfa", linewidth=0.8, linestyle="--", alpha=0.4)

ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax.xaxis.set_major_locator(mdates.AutoDateLocator())
plt.setp(ax.xaxis.get_majorticklabels(), color="white", rotation=20, ha="right")
plt.setp(ax.yaxis.get_majorticklabels(), color="white")

ax.set_xlabel("Market Start Time", color="#aaaacc", labelpad=8)
ax.set_ylabel("Amount Traded ($)", color="#aaaacc", labelpad=8)
ax.set_title("Trades Over Time", color="white", pad=10)

scatter_legend = ax.legend(facecolor="#16213e", edgecolor="#4a4a8a", labelcolor="white", fontsize=11)
if all_trades_sorted:
    ax_pnl.legend(facecolor="#16213e", edgecolor="#4a4a8a", labelcolor="white", fontsize=11, loc="upper left")
    ax.add_artist(scatter_legend)

ax.grid(True, color="#2a2a4a", linestyle="--", alpha=0.5, zorder=0)

if num_trades == 0:
    ax.text(
        0.5, 0.5, "No trades found", transform=ax.transAxes, color="white", ha="center", va="center", fontsize=14
    )

plt.savefig("livetest_plot.png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
plt.show()
print("Saved livetest_plot.png")
