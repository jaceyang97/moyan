"""Render docs/progression.png — moyan token-compression progression.

Timeline of every SKILL.md iteration that moved (or failed to move) the metric.
Each point = holdout Δ_median (output-token reduction vs B_zh_normal baseline).

Statistical machinery:
- For every point backed by real traces we also draw a 95% bootstrap CI
  (vertical bar) computed from the per-prompt Δ distribution. Lets readers
  see that single-point differences of 1-2pp are inside the noise band.
- Step line = best-so-far (of kept points only).
- Faint scatter cloud under current-best points = raw per-prompt Δ.

Historical points (v1 era, Sonnet 4.5; v2·0-3) have no traces on disk; they
appear as point estimates only. All Track C & D points load live from traces.

Regenerate after any new iteration:
    pip install matplotlib
    python benchmark/plot.py
"""
from __future__ import annotations

import json
import random
import statistics
from pathlib import Path

import matplotlib.pyplot as plt

from lib import BASELINE_GROUP

BENCH = Path(__file__).resolve().parent


# --- data loading -----------------------------------------------------------

def per_prompt_deltas(run_id: str, moyan_group: str,
                      baseline_run_id: str | None = None,
                      split: str | None = "holdout") -> list[float]:
    """Per-prompt Δ = (1 - moyan_out / baseline_out), as percentages.

    Baseline defaults to same run_id (within-run pairing, the fair comparison).
    `split` restricts to train.txt or holdout.txt prompt IDs; None = all.
    """
    baseline_run_id = baseline_run_id or run_id
    split_ids: set[str] | None = None
    if split:
        f = BENCH / "splits" / f"{split}.txt"
        if f.exists():
            split_ids = {l.strip() for l in f.read_text().splitlines() if l.strip()}

    def totals(rid: str, group: str) -> dict[str, int]:
        d = BENCH / "traces" / rid
        if not d.exists():
            return {}
        out: dict[str, int] = {}
        for p in d.glob("*.json"):
            if p.name.startswith(".") or "_judgments" in p.parts:
                continue
            t = json.loads(p.read_text(encoding="utf-8"))
            if t.get("error") or t.get("group") != group:
                continue
            out[t["prompt_id"]] = out.get(t["prompt_id"], 0) + t["usage"]["output_tokens"]
        return out

    m = totals(run_id, moyan_group)
    b = totals(baseline_run_id, BASELINE_GROUP)
    deltas = []
    for pid, mv in m.items():
        bv = b.get(pid)
        if not bv:
            continue
        if split_ids is not None and pid not in split_ids:
            continue
        deltas.append((1 - mv / bv) * 100)
    return deltas


def bootstrap_median_ci(samples: list[float], n_boot: int = 2000,
                        alpha: float = 0.05,
                        seed: int = 0) -> tuple[float, float]:
    """Percentile-bootstrap CI for the median. Cheap and assumption-free."""
    if len(samples) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(samples)
    meds = []
    for _ in range(n_boot):
        resample = [samples[rng.randrange(n)] for _ in range(n)]
        meds.append(statistics.median(resample))
    meds.sort()
    lo = meds[int(n_boot * alpha / 2)]
    hi = meds[int(n_boot * (1 - alpha / 2))]
    return (lo, hi)


# --- timeline ---------------------------------------------------------------
# `run` / `group` filled in for points we can load from traces. Others are
# hand-curated (traces not retained). x is display order, not a real axis.
EVENTS = [
    # v1 era — Sonnet 4.5, hand + autoskill iterations on 精 (no traces on disk)
    dict(x=0,  d=52.7, keep=True,  tag="v1 init"),
    dict(x=1,  d=52.3, keep=False, tag="v1·0"),
    dict(x=2,  d=56.5, keep=True,  tag="v1·1"),
    dict(x=3,  d=56.0, keep=False, tag="v1·2"),
    dict(x=4,  d=61.0, keep=True,  tag="v1·3"),
    dict(x=5,  d=63.7, keep=False, tag="v1·4"),
    # model upgrade — no SKILL.md change
    dict(x=6,  d=65.8, keep=True,  tag="Sonnet 4.6", marker="D"),
    # v2 era — Sonnet 4.6, autoskill iters (all discarded)
    dict(x=7,  d=67.8, keep=False, tag="v2·0"),
    dict(x=8,  d=65.9, keep=False, tag="v2·1"),
    dict(x=9,  d=66.3, keep=False, tag="v2·2"),
    dict(x=10, d=63.1, keep=False, tag="v2·3"),
    # discovery — level switch (no rule change)
    dict(x=11, d=70.6, keep=True,  tag="文言文", marker="*"),
    # Track C — SKILL.md v2.2 trim (has traces)
    dict(x=12, keep=True,  tag="v2.2 精",
         run="v2-sonnet-v22", group="D_moyan_jing"),
    dict(x=13, keep=True,  tag="v2.2 文言文", marker="*",
         run="v2-sonnet-v22", group="E_moyan_wenyan"),
    # Track D — autoskill under Opus 4.7 judge
    dict(x=14, keep=False, tag="iter 3 (精 35%)", train_only=True,
         d=65.84, note="train only"),
    dict(x=15, keep=False, tag="iter 4 (+填词)", train_only=True,
         d=67.09, note="train only"),
    dict(x=16, keep=True,  tag="iter 5 版式 精",
         run="skill23-holdout-allgroups", group="D_moyan_jing"),
    dict(x=17, keep=True,  tag="iter 5 版式 文言文", marker="*",
         run="skill23-holdout-allgroups", group="E_moyan_wenyan"),
    dict(x=18, keep=True,  tag="iter 5 版式 简",
         run="skill23-holdout-allgroups", group="C_moyan_jian"),
    dict(x=19, keep=False, tag="iter 6 删 SQL 示例",
         run="holdout_006", group="D_moyan_jing"),
]

# Resolve data-backed events: compute median + 95% CI + cloud from traces.
for e in EVENTS:
    if "run" in e:
        deltas = per_prompt_deltas(e["run"], e["group"])
        if deltas:
            e["d"] = statistics.median(deltas)
            e["ci"] = bootstrap_median_ci(deltas)
            e["cloud"] = deltas
            e["n"] = len(deltas)


def best_so_far(events):
    best, out = -1e9, []
    for e in events:
        if e.get("keep") and "d" in e:
            best = max(best, e["d"])
        out.append(best if best > -1e9 else None)
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

    fig, ax = plt.subplots(figsize=(16, 7.5))

    GREEN = "#2ca02c"
    GRAY  = "#b5b5b5"
    DARK  = "#1a1a1a"
    CI_C  = "#2ca02c"

    # Exclude events that didn't resolve
    events = [e for e in EVENTS if "d" in e]
    xs = [e["x"] for e in events]

    bsf = best_so_far(events)
    step_xs = [e["x"] for e, b in zip(events, bsf) if b is not None]
    step_ys = [b for b in bsf if b is not None]

    ax.step(step_xs, step_ys, where="post", color=GREEN, linewidth=2.4,
            alpha=0.9, zorder=2, label="best so far")
    ax.fill_between(step_xs,
                    [min(e["d"] for e in events) - 2] * len(step_xs),
                    step_ys, step="post", color=GREEN, alpha=0.05, zorder=1)

    # Scatter clouds for current-best / recent events that have per-prompt data
    rng = random.Random(0)
    cloud_xs = {e["x"] for e in events
                if e.get("keep") and e.get("cloud") and e["x"] >= 12}
    for e in events:
        if e["x"] not in cloud_xs:
            continue
        jx = [e["x"] + (rng.random() - 0.5) * 0.45 for _ in e["cloud"]]
        ax.scatter(jx, e["cloud"], s=12, color=GREEN, alpha=0.15,
                   edgecolor="none", zorder=3)

    # 95% bootstrap CI bars for data-backed events
    for e in events:
        if "ci" not in e:
            continue
        lo, hi = e["ci"]
        color = CI_C if e.get("keep") else "#888"
        ax.plot([e["x"], e["x"]], [lo, hi], color=color, alpha=0.55,
                linewidth=2.0, zorder=4, solid_capstyle="round")

    # Main markers
    for e in events:
        color = GREEN if e.get("keep") else GRAY
        marker = e.get("marker", "o")
        size = 220 if marker == "*" else (160 if marker == "D" else 120)
        if e.get("train_only"):
            size *= 0.7
        ax.scatter(e["x"], e["d"], c=color, marker=marker, s=size,
                   edgecolor=DARK if e.get("keep") else "#888",
                   linewidth=0.9, zorder=5)
        label = f"{e['d']:.1f}"
        if e.get("train_only"):
            label += "\n(train)"
        if "n" in e:
            label += f"\nn={e['n']}"
        ax.annotate(label,
                    xy=(e["x"], e["d"]),
                    xytext=(0, 10 if e.get("keep") else 8),
                    textcoords="offset points",
                    ha="center", va="bottom",
                    fontsize=8.5,
                    color=DARK if e.get("keep") else "#888",
                    weight="semibold" if e.get("keep") else "normal")

    for x, text, color in [
        (5.5,  "Sonnet 4.5 → 4.6",        "#9467bd"),
        (11.5, "SKILL.md v2.2 (−29%)",     "#ff7f0e"),
        (13.5, "Track D · Opus 4.7 judge", "#d62728"),
    ]:
        ax.axvline(x=x, color=color, linestyle="--", alpha=0.4, zorder=1)
        ax.text(x, 48.5, text, color=color, fontsize=8.5,
                ha="center", va="bottom",
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.9, pad=2))

    ax.set_xlabel("experiment timeline", fontsize=11, color="#333")
    ax.set_ylabel("token reduction  Δ_median  (%)", fontsize=11, color="#333")
    ax.set_title("moyan: token-compression progression",
                 fontsize=15, pad=18, color=DARK, weight="bold")
    ax.text(0.5, 1.015,
            "Sonnet responder · holdout median · vs B_zh_normal · bars = 95% bootstrap CI (2k resamples) · ★ = 文言文",
            transform=ax.transAxes, ha="center", fontsize=9.5, color="#666")

    ax.set_xticks(xs)
    ax.set_xticklabels([e["tag"] for e in events], rotation=32, ha="right",
                       fontsize=8.5, color="#444")
    all_d = [e["d"] for e in events]
    ax.set_ylim(min(all_d) - 4, max(all_d) + 5)
    ax.set_xlim(-0.6, max(xs) + 0.4)
    ax.tick_params(axis="y", labelcolor="#444", labelsize=9)

    handles = [
        plt.Line2D([], [], marker="o", color="w", markerfacecolor=GREEN,
                   markeredgecolor=DARK, markersize=10, label="kept"),
        plt.Line2D([], [], marker="o", color="w", markerfacecolor=GRAY,
                   markeredgecolor="#888", markersize=10, label="discarded"),
        plt.Line2D([], [], color=CI_C, linewidth=2.4, alpha=0.55,
                   label="95% CI (bootstrap)"),
        plt.Line2D([], [], color=GREEN, linewidth=2.4, label="best so far"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=9,
              framealpha=0.95, edgecolor="#ddd", ncol=4)

    best = max((e for e in events if e.get("keep")), key=lambda e: e["d"])
    ax.annotate(f"current best  {best['d']:.1f}%"
                + (f"  [{best['ci'][0]:.1f}, {best['ci'][1]:.1f}]"
                   if "ci" in best else ""),
                xy=(best["x"], best["d"]),
                xytext=(best["x"] - 3.0, max(all_d) + 3),
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
