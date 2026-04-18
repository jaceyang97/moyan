"""Compute Δ_median / Δ_mean per (model, moyan_group) vs B_zh_normal baseline.

Mirrors evaluate.py's delta logic but scans all 3 moyan groups, splits by
train/holdout, and breaks down by category. Used for the Haiku run write-up.

Usage:
  python haiku_stats.py --run-id v2-haiku
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

from lib import BASELINE_GROUP, MOYAN_GROUPS, BENCH_ROOT, load_prompts


def load_totals(run_id: str):
    """Return {(prompt_id, group): total_output_tokens}, summing multi-turn."""
    d = BENCH_ROOT / "traces" / run_id
    totals: dict[tuple[str, str], int] = defaultdict(int)
    for p in d.glob("*.json"):
        if "_judgments" in p.parts or "_judgments_kappa" in p.parts:
            continue
        t = json.loads(p.read_text(encoding="utf-8"))
        if t.get("error"):
            continue
        totals[(t["prompt_id"], t["group"])] += t["usage"]["output_tokens"]
    return totals


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()

    prompts = {p["id"]: p for p in load_prompts()}
    totals = load_totals(args.run_id)

    train_ids = set((BENCH_ROOT / "splits" / "train.txt").read_text().split())
    holdout_ids = set((BENCH_ROOT / "splits" / "holdout.txt").read_text().split())

    def split_of(pid: str) -> str:
        return "holdout" if pid in holdout_ids else "train" if pid in train_ids else "?"

    # For each (moyan_group, split), collect per-prompt Δ.
    buckets: dict[tuple[str, str], list[tuple[str, float]]] = defaultdict(list)
    cat_buckets: dict[tuple[str, str, str], list[float]] = defaultdict(list)

    for pid, meta in prompts.items():
        base = totals.get((pid, BASELINE_GROUP))
        if not base:
            continue
        sp = split_of(pid)
        for mg in MOYAN_GROUPS:
            m = totals.get((pid, mg))
            if not m:
                continue
            delta = 1 - m / base
            buckets[(mg, sp)].append((pid, delta))
            cat_buckets[(mg, meta["category"], sp)].append(delta)

    print(f"=== haiku_stats · run={args.run_id} ===\n")
    print(f"{'group':<20} {'split':<10} {'n':>4} {'Δ_median':>10} {'Δ_mean':>10}")
    for mg in MOYAN_GROUPS:
        for sp in ("train", "holdout", "all"):
            if sp == "all":
                deltas = [d for (g, s), lst in buckets.items() if g == mg
                          for (_, d) in lst]
            else:
                deltas = [d for (_, d) in buckets.get((mg, sp), [])]
            if not deltas:
                continue
            med = statistics.median(deltas)
            mean = statistics.mean(deltas)
            print(f"{mg:<20} {sp:<10} {len(deltas):>4} {med*100:>9.1f}% {mean*100:>9.1f}%")

    # Per-category, holdout only — Haiku's compression-by-category.
    print("\n--- per-category Δ_median (train+holdout) ---")
    cats = sorted({c for (_, c, _) in cat_buckets.keys()})
    print(f"{'category':<14} " + " ".join(f"{mg[2:]:>14}" for mg in MOYAN_GROUPS) + f"{'n':>6}")
    for cat in cats:
        row_deltas = {}
        n_cat = 0
        for mg in MOYAN_GROUPS:
            all_d = cat_buckets.get((mg, cat, "train"), []) + cat_buckets.get((mg, cat, "holdout"), [])
            if all_d:
                row_deltas[mg] = statistics.median(all_d)
                n_cat = max(n_cat, len(all_d))
            else:
                row_deltas[mg] = None
        cells = []
        for mg in MOYAN_GROUPS:
            v = row_deltas[mg]
            cells.append(f"{v*100:>13.1f}%" if v is not None else f"{'—':>14}")
        print(f"{cat:<14} " + " ".join(cells) + f"{n_cat:>6}")


if __name__ == "__main__":
    main()
