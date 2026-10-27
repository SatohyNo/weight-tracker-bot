"""Weight chart as PNG bytes."""
import io
from datetime import timedelta

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

import stats

INK, MUTED, GRID = "#1f2937", "#9ca3af", "#e5e7eb"
DOT, TREND, PLAN = "#93c5fd", "#2563eb", "#f59e0b"


def render(entries, goal, title):
    days = [d for d, _ in entries]
    kgs = [w for _, w in entries]
    trend = stats.rolling(entries)

    fig, ax = plt.subplots(figsize=(10, 5.2), dpi=130)
    ax.scatter(days, kgs, s=18, color=DOT, zorder=2, label="Взвешивания")
    ax.plot(days, [w for _, w in trend], color=TREND, lw=2.4, zorder=3, label="Среднее за 7 дней")

    # where the weight would be at the ideal pace for the chosen goal
    name, rate, _ = stats.GOALS[goal]
    start_d, start_w = trend[0]
    span = (days[-1] - start_d).days
    if span > 0:
        ax.plot([start_d, days[-1]], [start_w, start_w + rate * span / 7], ls="--", lw=1.6,
                color=PLAN, zorder=1, label=f"План: {name.lower()} {rate:+.2f} кг/нед")

    for (d, w), va in ((min(entries, key=lambda e: e[1]), "top"), (max(entries, key=lambda e: e[1]), "bottom")):
        if d == days[-1]:
            continue  # the last point has its own label
        ax.annotate(f"{w:.1f}", (d, w), xytext=(0, -9 if va == "top" else 9), textcoords="offset points",
                    ha="center", va=va, fontsize=9, color=MUTED)
    ax.annotate(f"{kgs[-1]:.1f} кг", (days[-1], kgs[-1]), xytext=(8, 0), textcoords="offset points",
                va="center", fontsize=11, fontweight="bold", color=INK)

    pad = max(0.5, (max(kgs) - min(kgs)) * 0.12)
    ax.set_ylim(min(kgs) - pad, max(kgs) + pad)
    ax.set_xlim(days[0] - timedelta(days=1), days[-1] + timedelta(days=max(2, span // 12)))
    loc = mdates.AutoDateLocator(minticks=4, maxticks=10)
    ax.xaxis.set_major_locator(loc)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d.%m" if span < 300 else "%m.%Y"))
    ax.set_ylabel("кг", color=MUTED)
    ax.set_title(title, loc="left", fontsize=13, color=INK, pad=12)
    ax.grid(axis="y", color=GRID)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_color(GRID)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=MUTED)
    ax.legend(loc="best", frameon=False, fontsize=9)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()
