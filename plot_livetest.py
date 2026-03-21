import json
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.dates as mdates

JSONL_FILE = "livetest.jsonl"

records = []
with open(JSONL_FILE) as f:
    for line in f:
        line = line.strip()
        if line:
            records.append(json.loads(line))

traded = [r for r in records if r["state"]["trade"] is not None]

wins, losses = [], []
for r in traded:
    trade = r["state"]["trade"]
    is_win = trade["outcome"] == r["outcome"]
    entry = {
        "dt": datetime.fromtimestamp(r["state"]["start_ts"]),
        "amount": trade["amount"],
        "slug": r["state"]["slug"],
    }
    (wins if is_win else losses).append(entry)

num_trades = len(traded)
num_wins = len(wins)
num_losses = len(losses)
win_rate = (num_wins / num_trades * 100) if num_trades > 0 else 0
total_markets = len({r["state"]["slug"] for r in records})
avg_price = sum(r["state"]["trade"]["price"] for r in traded) / num_trades if num_trades > 0 else 0

fig = plt.figure(figsize=(12, 8))
fig.patch.set_facecolor("#1a1a2e")
gs = gridspec.GridSpec(2, 1, height_ratios=[1, 4], hspace=0.4)

# --- Stats row ---
ax_stats = fig.add_subplot(gs[0])
ax_stats.set_facecolor("#1a1a2e")
ax_stats.axis("off")

stats = [
    ("Win Rate", f"{win_rate:.1f}%"),
    ("Wins", str(num_wins)),
    ("Losses", str(num_losses)),
    ("Trades", str(num_trades)),
    ("Markets", str(total_markets)),
    ("Avg Price", f"{avg_price:.3f}"),
]

for i, (label, value) in enumerate(stats):
    x = 0.08 + i * 0.165
    box = dict(boxstyle="round,pad=0.5", facecolor="#16213e", edgecolor="#4a4a8a", linewidth=1.5)
    ax_stats.text(x, 0.65, value, transform=ax_stats.transAxes,
                  fontsize=22, fontweight="bold", color="white",
                  ha="center", va="center", bbox=box)
    ax_stats.text(x, 0.15, label, transform=ax_stats.transAxes,
                  fontsize=10, color="#aaaacc", ha="center", va="center")

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
    ax.scatter(lx, ly, c="#ffcc00", s=120, zorder=3, label=f"Loss ({num_losses})", edgecolors="#cc9900", linewidths=1)

ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
ax.xaxis.set_major_locator(mdates.AutoDateLocator())
plt.setp(ax.xaxis.get_majorticklabels(), color="white", rotation=20, ha="right")
plt.setp(ax.yaxis.get_majorticklabels(), color="white")

ax.set_xlabel("Market Start Time", color="#aaaacc", labelpad=8)
ax.set_ylabel("Amount Traded ($)", color="#aaaacc", labelpad=8)
ax.set_title("Trades Over Time", color="white", pad=10)

legend = ax.legend(facecolor="#16213e", edgecolor="#4a4a8a", labelcolor="white", fontsize=11)

ax.grid(True, color="#2a2a4a", linestyle="--", alpha=0.5, zorder=0)

if num_trades == 0:
    ax.text(0.5, 0.5, "No trades found", transform=ax.transAxes,
            color="white", ha="center", va="center", fontsize=14)

plt.savefig("livetest_plot.png", dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
plt.show()
print("Saved livetest_plot.png")
