"""Render docs/progression.png — full moyan SKILL.md history.

One point per experiment from v0 (52.7%) all the way through the Opus 4.7
autoskill loop. Every point has a short Chinese note describing what was
changed. Gray = discarded, green = kept. Step line = running best.

x-axis = version labels (v0, v1·1, v2·0, v2.2, D-probe, D-iter5, ...).
y-axis = Δ_median (token reduction %, higher is better).

Scores come from three overlapping regimes:
  - v1: Sonnet 4.5 + Sonnet judge (RESULTS.md)
  - v2: Sonnet 4.6 + Opus 4.6 judge (RESULTS_v2.md Track B/C)
  - Track D: Sonnet 4.6 + Opus 4.7 judge (results.tsv + traces)
Regime shifts are marked with vertical dividers; scores are not perfectly
comparable across regimes but the trajectory is clear.

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
BASELINE_RUN = "sonnet-baseline"


def per_prompt_deltas(run_id: str, moyan_group: str = "D_moyan_jing") -> list[float]:
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


def median_of(run_id: str, group: str = "D_moyan_jing") -> float:
    deltas = per_prompt_deltas(run_id, group)
    return statistics.median(deltas) if deltas else float("nan")


# Full timeline. d = Δ_median %, note = short Chinese description of the change.
# `run`/`group` keys mean load from traces live; otherwise d is hardcoded from docs.
TIMELINE = [
    # v1 era — Sonnet 4.5 + Sonnet judge (RESULTS.md)
    dict(tag="v0",      d=52.7, kept=True,  note="初版：去客套填词",             era="v1"),
    dict(tag="v1·0",    d=52.3, kept=False, note="扩填词表",                     era="v1"),
    dict(tag="v1·1",    d=56.5, kept=True,  note="比较题先给差异表",             era="v1"),
    dict(tag="v1·2",    d=56.0, kept=False, note="枚举短表（措辞差）",           era="v1"),
    dict(tag="v1·3",    d=61.0, kept=True,  note="枚举按优先级排",               era="v1"),
    dict(tag="v1·4",    d=63.7, kept=False, note="答所问不旁支（崩）",           era="v1"),
    # Model upgrade: no SKILL change
    dict(tag="4.6",     d=65.8, kept=True,  note="换 Sonnet 4.5→4.6",            era="bump"),
    # v2 era — Sonnet 4.6 + Opus 4.6 judge
    dict(tag="v2·0",    d=67.8, kept=False, note="加枚举解法（完整性崩）",       era="v2"),
    dict(tag="v2·1",    d=65.9, kept=False, note="扩『留』规则",                 era="v2"),
    dict(tag="v2·2",    d=66.3, kept=False, note="紧级别表描述",                 era="v2"),
    dict(tag="v2·3",    d=63.1, kept=False, note="换 example 为 debug",          era="v2"),
    # Level-switch discovery
    dict(tag="文言文",  d=70.7, kept=True,  note="切默认为文言文",               era="v2"),
    # Track C — SKILL.md trim to v2.2 (Sonnet holdout scores)
    dict(tag="C-精",    d=70.0, kept=True,  note="SKILL 缩 29%（精）",           era="C"),
    dict(tag="C-文言",  d=74.5, kept=True,  note="SKILL 缩 29%（文言）",         era="C"),
    # Track D — autoskill under Opus 4.7 judge. All values hardcoded from
    # RESULTS_v2.md (Track D iteration log + skill23-holdout-allgroups table)
    # so the chart renders without trace files. Train scores are mean of two
    # seeds (a/b); holdout is single-seed n=18.
    dict(tag="D-probe",   d=67.2, kept=True,  note="换 Opus 4.7 判官",        era="D"),
    dict(tag="D-3",       d=65.8, kept=False, note="精 40%→35%（挤压）",       era="D"),
    dict(tag="D-4",       d=67.1, kept=False, note="扩填词表",                era="D"),
    dict(tag="D-5",       d=69.5, kept=True,  note="去 --- 与 ## 标题",       era="D"),
    # Per-level holdout for D-5 (run skill23-holdout-allgroups, RESULTS_v2.md
    # line 318): shows level convergence — 简/精 close ~4pp gap to 文言, but
    # 文言 itself plateaus at 74.5. April-2026 Opus-4.7 calibration confirmed
    # judge-shift on 文言 ≈ 0 (v2.2-文言 = 74.4 under both Opus 4.6 and 4.7).
    dict(tag="D-5 简 ho",  d=73.0, kept=True,  note="简 holdout +5pp vs C-简",  era="D"),
    dict(tag="D-5 精 ho",  d=73.9, kept=True,  note="精 holdout +4pp vs C-精",  era="D"),
    dict(tag="D-5 文言 ho", d=74.5, kept=True,  note="文言 持平（已饱和）",      era="D"),
    dict(tag="D-6",       d=70.6, kept=False, note="删 SQL 示例（train 涨）",  era="D"),
    dict(tag="D-6 ho",    d=64.4, kept=False, note="holdout −8pp（overfit）",  era="D"),
]


def load():
    for i, e in enumerate(TIMELINE):
        e["x"] = i
        if "runs" in e:
            vals = [median_of(r) for r in e["runs"]]
            vals = [v for v in vals if v == v]  # drop nan
            e["d"] = statistics.mean(vals) if vals else float("nan")
    return TIMELINE


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
                            "Noto Sans CJK JP", "WenQuanYi Zen Hei",
                            "PingFang SC", "SimHei")
                if c in {f.name for f in fm.fontManager.ttflist}), None)
    if cjk:
        plt.rcParams["font.family"] = cjk
        plt.rcParams["font.sans-serif"] = [cjk, "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    events = load()
    n = len(events)
    n_kept = sum(1 for e in events if e["kept"])

    fig, ax = plt.subplots(figsize=(20, 9))

    GREEN = "#2ca02c"
    GRAY  = "#b5b5b5"
    DARK  = "#1a1a1a"

    # Era dividers (faint, between era transitions)
    era_bounds = {}
    for e in events:
        era_bounds.setdefault(e["era"], []).append(e["x"])
    prev_era = None
    for e in events:
        if prev_era is not None and e["era"] != prev_era:
            ax.axvline(e["x"] - 0.5, color="#999", linestyle=":",
                       alpha=0.4, zorder=1, linewidth=1)
        prev_era = e["era"]

    # Running-best staircase
    bsf = running_best(events)
    ax.step([e["x"] for e in events], bsf, where="post",
            color=GREEN, linewidth=2.0, alpha=0.85,
            zorder=2, label="Running best")

    # Points
    for e in events:
        if e["kept"]:
            ax.scatter(e["x"], e["d"], s=130, color=GREEN,
                       edgecolor="white", linewidth=1.4, zorder=5)
        else:
            ax.scatter(e["x"], e["d"], s=55, color=GRAY,
                       edgecolor="none", zorder=4)

    # Chinese notes — kept above (green), discarded below (gray), both angled
    for e in events:
        if e["kept"]:
            ax.annotate(e["note"],
                        xy=(e["x"], e["d"]),
                        xytext=(6, 8),
                        textcoords="offset points",
                        fontsize=9.5,
                        color=GREEN,
                        ha="left", va="bottom",
                        rotation=30,
                        rotation_mode="anchor",
                        weight="semibold")
        else:
            ax.annotate(e["note"],
                        xy=(e["x"], e["d"]),
                        xytext=(-6, -8),
                        textcoords="offset points",
                        fontsize=9,
                        color="#888",
                        ha="right", va="top",
                        rotation=30,
                        rotation_mode="anchor")

    # Era band labels at top
    era_names = {
        "v1":   "v1 · Sonnet 4.5",
        "bump": "模型升级",
        "v2":   "v2 · Sonnet 4.6 + Opus 4.6 判官",
        "C":    "Track C · SKILL 精简",
        "D":    "Track D · Opus 4.7 判官 autoskill",
    }
    y_top = max(e["d"] for e in events) + 6
    for era, xs in era_bounds.items():
        mid = (min(xs) + max(xs)) / 2
        ax.text(mid, y_top, era_names[era],
                fontsize=9, color="#666", ha="center", va="bottom",
                style="italic",
                bbox=dict(facecolor="white", edgecolor="#ddd",
                          alpha=0.9, pad=3, boxstyle="round,pad=0.35"))

    ax.set_title(f"Moyan SKILL.md 演进：{n} 次实验，{n_kept} 次 kept",
                 fontsize=14, pad=12, color=DARK, weight="semibold")
    ax.set_xlabel("版本号", fontsize=11, color="#444")
    ax.set_ylabel("Δ_median  (token 节省 %，越高越好)",
                  fontsize=11, color="#444")

    ax.set_xticks([e["x"] for e in events])
    ax.set_xticklabels([e["tag"] for e in events], fontsize=9,
                       rotation=30, ha="right", color="#444")

    all_d = [e["d"] for e in events]
    ax.set_ylim(min(all_d) - 4, max(all_d) + 8)
    ax.set_xlim(-0.7, n + 0.5)
    ax.tick_params(axis="y", labelsize=9.5, labelcolor="#444")

    handles = [
        plt.Line2D([], [], marker="o", color="w", markerfacecolor=GREEN,
                   markeredgecolor="white", markersize=11, label="Kept"),
        plt.Line2D([], [], marker="o", color="w", markerfacecolor=GRAY,
                   markeredgecolor="none", markersize=7, label="Discarded"),
        plt.Line2D([], [], color=GREEN, linewidth=2.0, label="Running best"),
    ]
    ax.legend(handles=handles, loc="lower right", fontsize=9.5,
              framealpha=0.95, edgecolor="#ddd")

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=160, bbox_inches="tight", facecolor="white")
    print(f"wrote {out_path}")


if __name__ == "__main__":
    render(BENCH.parent / "docs" / "progression.png")
