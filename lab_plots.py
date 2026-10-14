from io import BytesIO
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
from matplotlib import font_manager
from matplotlib.figure import Figure
import numpy as np


def make_figure(clean, summary, groups, measurement, title, ylabel):
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    font = font_manager.FontProperties(fname=str(font_path)) if font_path.exists() else None
    fig = Figure(figsize=(max(7, min(16, len(summary) * 0.75)), 4.8), layout="constrained")
    ax = fig.subplots()
    x = np.arange(len(summary))
    ax.bar(x, summary["mean"], color="#148578", alpha=0.8, width=0.6)
    replicated = summary["n"] > 1
    ax.errorbar(x[replicated], summary.loc[replicated, "mean"],
                yerr=summary.loc[replicated, "sd"], fmt="none", ecolor="#183a36", capsize=4)
    labels = []
    for i, row in summary.iterrows():
        mask = np.ones(len(clean), dtype=bool)
        for col in groups:
            mask &= clean[col].eq(row[col]).to_numpy()
        values = clean.loc[mask, measurement].to_numpy()
        offsets = np.linspace(-0.12, 0.12, len(values)) if len(values) > 1 else [0]
        ax.scatter(i + np.asarray(offsets), values, s=22, color="#172b28", zorder=3)
        labels.append("\n".join(f"{col}={row[col]}" for col in groups) + f"\nn={row['n']}")
    ax.set_xticks(x, labels, rotation=25 if len(summary) > 5 else 0, ha="right" if len(summary) > 5 else "center", fontproperties=font)
    ax.set_title(title, fontproperties=font, pad=15)
    ax.set_ylabel(ylabel, fontproperties=font)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(axis="y", alpha=0.18)
    ax.set_axisbelow(True)
    return fig


def figure_bytes(fig, fmt):
    output = BytesIO()
    fig.savefig(output, format=fmt, dpi=300, facecolor="white")
    return output.getvalue()
