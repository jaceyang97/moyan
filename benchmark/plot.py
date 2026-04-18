"""Render docs/progression.png — moyan token-compression progression.

Karpathy/autoresearch-style: scatter of every attempt, kept points colored,
discards gray, best-so-far step line, annotations on milestones.

Data is hardcoded here (small, hand-curated from RESULTS.md + RESULTS_v2.md +
results.tsv) — this is a doc generator, not a live dashboard.

Usage:
    pip install matplotlib
    python benchmark/plot.py
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# Chronological timeline. delta = Δ_median (output-token reduction vs B_zh_normal).
# All values for moyan 精 (default), except the final 文言文 entry.
EVENTS = [
    # ----- v1 era: Sonnet 4.5, hand + autoskill iterations -----
    dict(idx=0,  delta=52.7, status="start",   label="v1 init",
         note="基础规则\n去客套·去填词·去铺垫"),
    dict(idx=1,  delta=52.3, status="keep",    label="v1·1",
         note="扩填词黑名单"),
    dict(idx=2,  delta=56.5, status="keep",    label="v1·2",
         note="比较类→差异表"),
    dict(idx=3,  delta=56.0, status="discard", label="v1·3"),
    dict(idx=4,  delta=61.0, status="keep",    label="v1·4",
         note="枚举原因\n按优先级短表"),
    dict(idx=5,  delta=63.7, status="discard", label="v1·5"),
    # ----- transition: model upgrade (no SKILL.md change) -----
    dict(idx=6,  delta=65.8, status="upgrade", label="model 4.6",
         note="切 Sonnet 4.6\n免费 +4.8pp"),
    # ----- v2 era: Sonnet 4.6, autoskill iters (all discarded) -----
    dict(idx=7,  delta=67.8, status="discard", label="v2·0",
         note="枚举解法\nholdout 崩 −20pp"),
    dict(idx=8,  delta=65.9, status="discard", label="v2·1"),
    dict(idx=9,  delta=66.3, status="discard", label="v2·2"),
    dict(idx=10, delta=63.1, status="discard", label="v2·3"),
    # ----- discovery: 文言文 level (no SKILL.md change, just measured) -----
    dict(idx=11, delta=70.6, status="discover", label="文言文",
         note="切级别即得\n最高 +4.8pp"),
]

COLORS = {
    "start":    "#1f77b4",  # blue
    "keep":     "#2ca02c",  # green
    "discard":  "#bdbdbd",  # gray
    "upgrade":  "#9467bd",  # purple
    "discover": "#ff7f0e",  # orange
}
MARKERS = {
    "start": "s", "keep": "o", "discard": "o",
    "upgrade": "D", "discover": "*",
}
SIZES = {
    "start": 160, "keep": 140, "discard": 90,
    "upgrade": 170, "discover": 360,
}


def best_so_far(events):
    best, out = -float("inf"), []
    for e in events:
        if e["status"] in ("keep", "start", "upgrade", "discover"):
            best = max(best, e["delta"])
        out.append(best)
    return out


def render(out_path: Path):
    plt.style.use("seaborn-v0_8-whitegrid")
    # Pick first available CJK-capable font
    import matplotlib.font_manager as fm
    cjk_candidates = ["Noto Sans CJK SC", "Noto Sans CJK", "WenQuanYi Zen Hei",
                      "PingFang SC", "Heiti TC", "SimHei", "Source Han Sans SC"]
    available = {f.name for f in fm.fontManager.ttflist}
    cjk = next((c for c in cjk_candidates if c in available), None)
    plt.rcParams["font.family"] = [cjk, "DejaVu Sans", "sans-serif"] if cjk else ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(13, 7))

    bsf = best_so_far(EVENTS)
    xs = [e["idx"] for e in EVENTS]

    # Best-so-far step line (the headline arc)
    ax.step(xs, bsf, where="post", color="#2ca02c", linewidth=2.6,
            alpha=0.85, zorder=2, label="best so far")
    ax.fill_between(xs, [52.7] * len(xs), bsf, step="post",
                    color="#2ca02c", alpha=0.06, zorder=1)

    # Scatter every attempt
    for e in EVENTS:
        s = e["status"]
        edge = "#222" if s != "discard" else "#888"
        ax.scatter(e["idx"], e["delta"], c=COLORS[s], marker=MARKERS[s],
                   s=SIZES[s], edgecolor=edge, linewidth=0.9, zorder=4)

    # Milestone annotations — positions hand-tuned to avoid overlaps
    annot_layout = {
        0:  dict(dx=0.0,  dy=-1.5, va="top",    ha="center"),  # v1 init below
        1:  dict(dx=0.0,  dy=-1.5, va="top",    ha="center"),  # v1·1 below
        2:  dict(dx=0.0,  dy=+1.4, va="bottom", ha="center"),  # v1·2 above
        4:  dict(dx=0.0,  dy=+1.4, va="bottom", ha="center"),  # v1·4 above
        5:  dict(dx=+0.8, dy=+1.6, va="bottom", ha="left"),    # v1·5 up-right (discard, but offset)
        6:  dict(dx=-0.6, dy=+1.4, va="bottom", ha="right"),   # upgrade up-left
        7:  dict(dx=+0.5, dy=+1.6, va="bottom", ha="left"),    # v2·0 up-right
        11: dict(dx=-0.6, dy=+1.4, va="bottom", ha="right"),   # 文言文 up-left
    }
    for e in EVENTS:
        if "note" not in e:
            continue
        lay = annot_layout.get(e["idx"], dict(dx=0, dy=1.4, va="bottom", ha="center"))
        s = e["status"]
        ax.annotate(
            e["note"],
            xy=(e["idx"], e["delta"]),
            xytext=(e["idx"] + lay["dx"], e["delta"] + lay["dy"]),
            textcoords="data",
            fontsize=8.5,
            ha=lay["ha"], va=lay["va"],
            color="#222" if s != "discard" else "#777",
            linespacing=1.25,
        )

    # Model-switch divider
    ax.axvline(x=6, color="#9467bd", linestyle="--", alpha=0.35, zorder=1)
    ax.text(6, 49.5, "Sonnet 4.5 → 4.6", color="#9467bd",
            fontsize=8.5, ha="center", va="bottom",
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.85, pad=2))

    # Axes
    ax.set_xlabel("experiment timeline", fontsize=11, color="#333")
    ax.set_ylabel("token reduction Δ_median (%)", fontsize=11, color="#333")
    ax.set_title("moyan: token-compression progression",
                 fontsize=15, pad=18, color="#111", weight="bold")
    ax.text(0.5, 1.015,
            "vs Chinese-normal baseline · median across paired prompts · 莫言 精 unless noted",
            transform=ax.transAxes, ha="center", fontsize=9.5, color="#666")

    ax.set_xticks(xs)
    ax.set_xticklabels([e["label"] for e in EVENTS], rotation=25, ha="right",
                       fontsize=9, color="#444")
    ax.set_ylim(48, 76)
    ax.set_xlim(-0.6, 11.6)
    ax.tick_params(axis="y", labelcolor="#444", labelsize=9)

    # Custom legend
    handles = [
        plt.Line2D([], [], marker="s", color="w", markerfacecolor=COLORS["start"],
                   markeredgecolor="#222", markersize=10, label="initial"),
        plt.Line2D([], [], marker="o", color="w", markerfacecolor=COLORS["keep"],
                   markeredgecolor="#222", markersize=10, label="kept (improved)"),
        plt.Line2D([], [], marker="o", color="w", markerfacecolor=COLORS["discard"],
                   markeredgecolor="#888", markersize=9, label="discarded"),
        plt.Line2D([], [], marker="D", color="w", markerfacecolor=COLORS["upgrade"],
                   markeredgecolor="#222", markersize=10, label="model upgrade"),
        plt.Line2D([], [], marker="*", color="w", markerfacecolor=COLORS["discover"],
                   markeredgecolor="#222", markersize=15,
                   label="level switch (no SKILL.md change)"),
        plt.Line2D([], [], color="#2ca02c", linewidth=2.6, label="best so far"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=9,
              framealpha=0.95, edgecolor="#ddd")

    # "Current best" callout pointing at the 文言文 star
    ax.annotate(f"current best  {EVENTS[-1]['delta']}%",
                xy=(11, EVENTS[-1]["delta"]),
                xytext=(9.6, 74.5),
                fontsize=10.5, color="#ff7f0e", weight="bold", ha="left",
                arrowprops=dict(arrowstyle="->", color="#ff7f0e",
                                lw=1.3, alpha=0.85,
                                connectionstyle="arc3,rad=-0.15"))

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=160, bbox_inches="tight", facecolor="white")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    out = Path(__file__).resolve().parent.parent / "docs" / "progression.png"
    render(out)
