from io import BytesIO
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from matplotlib import font_manager
from matplotlib.figure import Figure
import numpy as np

# A*STAR palette (sampled from the logo): blue #002F86, red #D8291B, ink #0B1F4B.
BAR_COLOUR = "#002F86"
BAR_ALPHA = 0.75
ERROR_COLOUR = "#0B1F4B"
POINT_COLOUR = "#D8291B"
GRID_COLOUR = "#C9D5EC"
INK = "#0B1F4B"


def order_summary(summary, mode: str):
    """Reorder the summary rows: 'given', 'label', 'mean_desc', 'mean_asc'."""
    if summary.empty or mode in (None, "given"):
        return summary
    if mode == "mean_desc":
        return summary.sort_values("mean", ascending=False, kind="stable").reset_index(drop=True)
    if mode == "mean_asc":
        return summary.sort_values("mean", ascending=True, kind="stable").reset_index(drop=True)
    if mode == "label":
        keys = [c for c in summary.columns if c not in ("n", "mean", "sd")]
        return summary.sort_values(keys, kind="stable").reset_index(drop=True) if keys else summary
    return summary


def make_figure(clean, summary, groups, measurement, title, ylabel,
                bar_colour: str = BAR_COLOUR, point_colour: str = POINT_COLOUR,
                show_errors: bool = True, show_values: bool = False,
                show_points: bool = True, y_from: float | None = None,
                y_to: float | None = None, horizontal: bool = False):
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    font = font_manager.FontProperties(fname=str(font_path)) if font_path.exists() else None
    fig = Figure(figsize=(max(7, min(16, len(summary) * 0.75)), 4.8), layout="constrained")
    fig.patch.set_facecolor("white")
    ax = fig.subplots()
    ax.set_facecolor("white")
    x = np.arange(len(summary))
    ax.bar(x, summary["mean"], color=bar_colour, alpha=BAR_ALPHA, width=0.6, zorder=2)
    if show_errors:
        replicated = summary["n"] > 1
        ax.errorbar(x[replicated], summary.loc[replicated, "mean"],
                    yerr=summary.loc[replicated, "sd"], fmt="none", ecolor=ERROR_COLOUR,
                    elinewidth=1.6, capsize=5, capthick=1.6, zorder=4)
    labels = []
    for i, row in summary.iterrows():
        values = np.array([])
        if show_points or show_values:
            mask = np.ones(len(clean), dtype=bool)
            for col in groups:
                mask &= clean[col].eq(row[col]).to_numpy()
            values = clean.loc[mask, measurement].to_numpy()
        if show_points and len(values):
            offsets = np.linspace(-0.12, 0.12, len(values)) if len(values) > 1 else [0]
            ax.scatter(i + np.asarray(offsets), values, s=26, color=point_colour,
                       edgecolors="white", linewidths=0.8, zorder=5)
        if show_values and row["mean"] == row["mean"]:
            ax.annotate(f"{row['mean']:.3g}", (i, row["mean"]), textcoords="offset points",
                        xytext=(0, 6), ha="center", fontsize=8.5, color=INK,
                        fontproperties=font, zorder=6)
        labels.append("\n".join(f"{col}={row[col]}" for col in groups) + f"\nn={row['n']}")
    ax.set_xticks(x, labels, rotation=25 if len(summary) > 5 else 0,
                  ha="right" if len(summary) > 5 else "center", fontproperties=font)
    ax.set_title(title, fontproperties=font, pad=15, color=INK, fontweight="bold")
    ax.set_ylabel(ylabel, fontproperties=font, color=INK)
    if y_from is not None or y_to is not None:
        low, high = ax.get_ylim()
        ax.set_ylim(y_from if y_from is not None else low, y_to if y_to is not None else high)
    ax.tick_params(colors="#33415C")
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(GRID_COLOUR)
    ax.grid(axis="y", color=GRID_COLOUR, alpha=0.55, linewidth=0.8)
    ax.set_axisbelow(True)
    return fig


def figure_bytes(fig, fmt, dpi: int = 300):
    output = BytesIO()
    fig.savefig(output, format=fmt, dpi=dpi, facecolor="white")
    return output.getvalue()
