"""Render docs/progression.png — moyan autoskill loop (karpathy-style).

One point = one benchmark run (one seed, train split).
y-axis  = per-prompt Δ_median against within-run B_zh_normal baseline (higher = more compression).
x-axis  = experiment # (chronological order of autoskill jobs).
green   = kept (improved BEST or first in loop); gray = discarded.
step    = running best over kept experiments.

Scope is strictly the Opus 4.7 judge regime — directly comparable scores only.
Historical v1/v2 ladder and Track C cross-model runs are intentionally excluded.

Regenerate:
    python benchmark/plot.py
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path

import matplotlib.pyplot as plt

from lib import BASELINE_GROUP

BENCH = Path(__file__).resolve().parent
TRAIN_SPLIT = BENCH / "splits" / "train.txt"


BASELINE_RUN = "sonnet-baseline"  # shared B_zh_normal reference used by autoskill


def per_prompt_deltas(run_id: str, moyan_group: str = "D_moyan_jing") -> list[float]:
    """Per-prompt Δ = (1 - moyan_out / baseline_out) × 100, restricted to train split."""
    split_ids = {l.strip() for l in TRAIN_SPLIT.read_text().splitlines() if l.strip()}

    def totals(rid: str, group: str) -> dict[str, int]:
        out: dict[str, int] = {}
        d = BENCH / "traces" / rid
        if not d.exists():
            return out
        for p in d.glob("*.json"):
            if p.name.startswith(".") or "_judgments" in p.parts:
                continue
            t = json.loads(p.read_text(encoding="utf-8"))
            if t.get("error") or t.get("group") != group:
                continue
            out[t["prompt_id"]] = out.get(t["prompt_id"], 0) + t["usage"]["output_tokens"]
        return out

    m = totals(run_id, moyan_group)
    b = totals(BASELINE_RUN, BASELINE_GROUP)
    deltas = []
    for pid, mv in m.items():
        bv = b.get(pid)
        if not bv or pid not in split_ids:
            continue
        deltas.append((1 - mv / bv) * 100)
    return deltas


# Autoskill loop (Opus 4.7 judge · Sonnet responder · train split · 精 default).
# Verdict = iter-level pipeline decision, not per-seed comparison.
EXPERIMENTS = [
    dict(run="probe_v22_a", kept=True,  label="probe (baseline)"),
    dict(run="probe_v22_b", kept=True),
    dict(run="iter_004_a",  kept=False),
    dict(run="iter_004_b",  kept=False),
    dict(run="iter_005_a",  kept=True,  label="keep: 版式规则 (drop --- and ## in short answers)"),
    dict(run="iter_005_b",  kept=True),
    dict(run="iter_006_a",  kept=False, label="discard: train up, holdout -8pp"),
    dict(run="iter_006_b",  kept=False),
]


def load():
    for i, e in enumerate(EXPERIMENTS):
        deltas = per_prompt_deltas(e["run"])
        e["x"] = i
        e["d"] = statistics.median(deltas) if deltas else float("nan")
    return EXPERIMENTS


def running_best(events):
    best, out = -1e9, []
    for e in events:
        if e["kept"]:
            best = max(best, e["d"])
        out.append(best if best > -1e9 else None)
    return out


def render(out_path: Path):
    import matplotlib.font_manager as fm
    plt.style.use("seaborn-v0_8-whitegrid")
    cjk = next((c for c in ("Noto Sans CJK SC", "Noto Sans CJK",
                            "WenQuanYi Zen Hei", "PingFang SC", "SimHei")
                if c in {f.name for f in fm.fontManager.ttflist}), None)
    if cjk:
        plt.rcParams["font.family"] = cjk
        plt.rcParams["font.sans-serif"] = [cjk, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    events = load()
    n = len(events)
    n_kept = sum(1 for e in events if e["kept"])

    fig, ax = plt.subplots(figsize=(13, 6.5))

    GREEN = "#2ca02c"
    GRAY  = "#c9c9c9"
    DARK  = "#1a1a1a"

    bsf = running_best(events)
    ax.step([e["x"] for e in events], bsf, where="post",
            color=GREEN, linewidth=2.2, alpha=0.85,
            zorder=2, label="Running best")

    # Points: kept = solid green (large), discarded = pale gray (small)
    for e in events:
        if e["kept"]:
            ax.scatter(e["x"], e["d"], s=150, color=GREEN,
                       edgecolor="white", linewidth=1.5, zorder=5)
        else:
            ax.scatter(e["x"], e["d"], s=50, color=GRAY,
                       edgecolor="none", zorder=4)

    # Labels — only on annotated events, angled up-right, karpathy style
    for e in events:
        if not e.get("label"):
            continue
        ax.annotate(e["label"],
                    xy=(e["x"], e["d"]),
                    xytext=(8, 6),
                    textcoords="offset points",
                    fontsize=9.5,
                    color=GREEN if e["kept"] else "#888",
                    style="italic",
                    rotation=18,
                    ha="left", va="bottom")

    # Title
    ax.set_title(f"Moyan autoskill: {n} experiments, {n_kept} kept improvements",
                 fontsize=14, pad=12, color=DARK, weight="semibold")

    ax.set_xlabel("Experiment #", fontsize=11, color="#444")
    ax.set_ylabel("Δ_median  (token reduction %, higher is better)",
                  fontsize=11, color="#444")

    ax.set_xticks([e["x"] for e in events])
    all_d = [e["d"] for e in events]
    ax.set_ylim(min(all_d) - 3, max(all_d) + 4)
    ax.set_xlim(-0.5, n - 0.5)
    ax.tick_params(labelsize=9.5, labelcolor="#444")

    # Minimal legend
    handles = [
        plt.Line2D([], [], marker="o", color="w", markerfacecolor=GREEN,
                   markeredgecolor="white", markersize=11, label="Kept"),
        plt.Line2D([], [], marker="o", color="w", markerfacecolor=GRAY,
                   markeredgecolor="none", markersize=7, label="Discarded"),
        plt.Line2D([], [], color=GREEN, linewidth=2.2, label="Running best"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=9.5,
              framealpha=0.95, edgecolor="#ddd")

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=160, bbox_inches="tight", facecolor="white")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    render(BENCH.parent / "docs" / "progression.png")
