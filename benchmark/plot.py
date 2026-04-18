"""Render docs/progression.png — moyan token-compression progression.

Timeline of every SKILL.md iteration + level discoveries that moved the needle.
Each point: Δ_median (output-token reduction vs B_zh_normal) on the benchmark.
Big colored dot = kept/discovered. Gray dot = discarded. Number above every dot.
Step line = best-so-far. Per-prompt scatter cloud under current-best entries
so you can see the underlying distribution, not just the headline median.

Data is hand-curated from RESULTS{,_v2}.md + git log + local traces.
Regenerate after any new iteration:
    pip install matplotlib
    python benchmark/plot.py
"""
from __future__ import annotations

import json
import random
from pathlib import Path

import matplotlib.pyplot as plt

from lib import BASELINE_GROUP

BENCH = Path(__file__).resolve().parent

# --- timeline ---------------------------------------------------------------
# Δ = moyan 精 holdout Δ_median vs B_zh_normal (same prompts, same metric).
# The final entry flips to 文言文 — kept in the headline because it's the
# mode we now recommend for debug/explain and it's the current SOTA.
EVENTS = [
    # v1 era — Sonnet 4.5, hand + autoskill iterations on 精
    dict(x=0,  d=52.7, keep=True,  tag="v1 init"),
    dict(x=1,  d=52.3, keep=False, tag="v1·0"),
    dict(x=2,  d=56.5, keep=True,  tag="v1·1"),
    dict(x=3,  d=56.0, keep=False, tag="v1·2"),
    dict(x=4,  d=61.0, keep=True,  tag="v1·3"),
    dict(x=5,  d=63.7, keep=False, tag="v1·4"),
    # model upgrade — no SKILL.md change
    dict(x=6,  d=65.8, keep=True,  tag="Sonnet 4.6", marker="D"),
    # v2 era — Sonnet 4.6, autoskill iters (all discarded — plateau)
    dict(x=7,  d=67.8, keep=False, tag="v2·0"),
    dict(x=8,  d=65.9, keep=False, tag="v2·1"),
    dict(x=9,  d=66.3, keep=False, tag="v2·2"),
    dict(x=10, d=63.1, keep=False, tag="v2·3"),
    # discovery — level switch (no rule change), Sonnet 4.6 holdout 文言文
    dict(x=11, d=70.6, keep=True,  tag="文言文", marker="*"),
    # Track C — SKILL.md v2.2 trim + quantitative level targets
    dict(x=12, d=70.0, keep=True,  tag="v2.2 精"),
    dict(x=13, d=74.5, keep=True,  tag="v2.2 文言文", marker="*"),
]

# Per-prompt Δ cloud — drawn as a faint vertical strip under the median dot
# for entries where we still have local traces. Gives the viewer a sense of
# the distribution behind every headline median.
def load_cloud(run_id: str, group: str) -> list[float]:
    d = BENCH / "traces" / run_id
    if not d.exists():
        return []
    totals_m: dict[str, int] = {}
    totals_b: dict[str, int] = {}
    for p in d.glob("*.json"):
        if p.name.startswith(".") or "_judgments" in p.parts:
            continue
        t = json.loads(p.read_text(encoding="utf-8"))
        if t.get("error"):
            continue
        pid = t["prompt_id"]
        out = t["usage"]["output_tokens"]
        if t["group"] == group:
            totals_m[pid] = totals_m.get(pid, 0) + out
        elif t["group"] == BASELINE_GROUP:
            totals_b[pid] = totals_b.get(pid, 0) + out
    deltas = []
    for pid, m in totals_m.items():
        b = totals_b.get(pid)
        if not b:
            continue
        deltas.append((1 - m / b) * 100)
    return deltas


CLOUDS = {
    12: load_cloud("v2-sonnet-v22", "D_moyan_jing"),
    13: load_cloud("v2-sonnet-v22", "E_moyan_wenyan"),
}


def best_so_far(events):
    best, out = -1e9, []
    for e in events:
        if e.get("keep"):
            best = max(best, e["d"])
        out.append(best)
    return out


def render(out_path: Path):
    plt.style.use("seaborn-v0_8-whitegrid")
    import matplotlib.font_manager as fm
    cjk_candidates = ["Noto Sans CJK SC", "Noto Sans CJK", "WenQuanYi Zen Hei",
                      "PingFang SC", "Heiti TC", "SimHei", "Source Han Sans SC"]
    avail = {f.name for f in fm.fontManager.ttflist}
    cjk = next((c for c in cjk_candidates if c in avail), None)
    plt.rcParams["font.family"] = [cjk, "DejaVu Sans", "sans-serif"] if cjk else ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, ax = plt.subplots(figsize=(13, 7))

    GREEN = "#2ca02c"
    GRAY  = "#b5b5b5"
    DARK  = "#1a1a1a"

    xs = [e["x"] for e in EVENTS]
    bsf = best_so_far(EVENTS)

    ax.step(xs, bsf, where="post", color=GREEN, linewidth=2.4,
            alpha=0.9, zorder=2)
    ax.fill_between(xs, [min(e["d"] for e in EVENTS) - 2] * len(xs), bsf,
                    step="post", color=GREEN, alpha=0.05, zorder=1)

    rng = random.Random(0)
    for x, cloud in CLOUDS.items():
        jx = [x + (rng.random() - 0.5) * 0.45 for _ in cloud]
        ax.scatter(jx, cloud, s=14, color=GREEN, alpha=0.18,
                   edgecolor="none", zorder=3)

    for e in EVENTS:
        color = GREEN if e["keep"] else GRAY
        marker = e.get("marker", "o")
        size = 220 if marker == "*" else (160 if marker == "D" else 120)
        ax.scatter(e["x"], e["d"], c=color, marker=marker, s=size,
                   edgecolor=DARK if e["keep"] else "#888",
                   linewidth=0.9, zorder=5)
        ax.annotate(f"{e['d']:.1f}",
                    xy=(e["x"], e["d"]),
                    xytext=(0, 9 if e["keep"] else 7),
                    textcoords="offset points",
                    ha="center", va="bottom",
                    fontsize=9,
                    color=DARK if e["keep"] else "#888",
                    weight="semibold" if e["keep"] else "normal")

    for x, text, color in [
        (5.5, "Sonnet 4.5 → 4.6", "#9467bd"),
        (11.5, "SKILL.md v2.2 (−29%)", "#ff7f0e"),
    ]:
        ax.axvline(x=x, color=color, linestyle="--", alpha=0.4, zorder=1)
        ax.text(x, 49.7, text, color=color, fontsize=8.5,
                ha="center", va="bottom",
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.9, pad=2))

    ax.set_xlabel("experiment timeline", fontsize=11, color="#333")
    ax.set_ylabel("token reduction  Δ_median  (%)", fontsize=11, color="#333")
    ax.set_title("moyan: token-compression progression",
                 fontsize=15, pad=18, color=DARK, weight="bold")
    ax.text(0.5, 1.015,
            "Sonnet responder · holdout median · vs Chinese-normal baseline · 精 unless ★ = 文言文",
            transform=ax.transAxes, ha="center", fontsize=9.5, color="#666")

    ax.set_xticks(xs)
    ax.set_xticklabels([e["tag"] for e in EVENTS], rotation=28, ha="right",
                       fontsize=9, color="#444")
    ax.set_ylim(48, 78)
    ax.set_xlim(-0.6, len(EVENTS) - 0.4)
    ax.tick_params(axis="y", labelcolor="#444", labelsize=9)

    handles = [
        plt.Line2D([], [], marker="o", color="w", markerfacecolor=GREEN,
                   markeredgecolor=DARK, markersize=10, label="kept"),
        plt.Line2D([], [], marker="o", color="w", markerfacecolor=GRAY,
                   markeredgecolor="#888", markersize=10, label="discarded"),
        plt.Line2D([], [], color=GREEN, linewidth=2.4, label="best so far"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=9,
              framealpha=0.95, edgecolor="#ddd", ncol=3)

    best = EVENTS[-1]
    ax.annotate(f"current best  {best['d']:.1f}%",
                xy=(best["x"], best["d"]),
                xytext=(best["x"] - 2.4, 76.5),
                fontsize=10.5, color="#ff7f0e", weight="bold", ha="left",
                arrowprops=dict(arrowstyle="->", color="#ff7f0e",
                                lw=1.3, alpha=0.85,
                                connectionstyle="arc3,rad=-0.15"))

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=160, bbox_inches="tight", facecolor="white")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    render(BENCH.parent / "docs" / "progression.png")
