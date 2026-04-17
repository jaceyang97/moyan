"""Split prompts.jsonl into train / holdout sets with a fixed seed.

Usage:
  python split.py --train-frac 0.77 --seed 42

Holdout is STRATIFIED by category so every category is represented in both splits.
Writes:
  splits/train.txt     — one prompt_id per line
  splits/holdout.txt   — one prompt_id per line
"""
from __future__ import annotations

import argparse
import random
from collections import defaultdict
from pathlib import Path

from lib import BENCH_ROOT, load_prompts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-frac", type=float, default=40 / 52)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    prompts = load_prompts()
    by_cat: dict[str, list[str]] = defaultdict(list)
    for p in prompts:
        by_cat[p["category"]].append(p["id"])

    rng = random.Random(args.seed)
    train_ids, holdout_ids = [], []
    for cat, ids in by_cat.items():
        rng.shuffle(ids)
        n_train = max(1, round(len(ids) * args.train_frac))
        # Ensure at least one holdout if we have >= 2 prompts in the category.
        if len(ids) >= 2 and n_train == len(ids):
            n_train = len(ids) - 1
        train_ids.extend(ids[:n_train])
        holdout_ids.extend(ids[n_train:])

    train_ids.sort()
    holdout_ids.sort()

    out = BENCH_ROOT / "splits"
    out.mkdir(exist_ok=True)
    (out / "train.txt").write_text("\n".join(train_ids) + "\n", encoding="utf-8")
    (out / "holdout.txt").write_text("\n".join(holdout_ids) + "\n", encoding="utf-8")

    print(f"train:   {len(train_ids):3d}  → splits/train.txt")
    print(f"holdout: {len(holdout_ids):3d}  → splits/holdout.txt")

    print("\ncategory distribution:")
    print(f"  {'category':14} {'train':>6} {'holdout':>8}")
    for cat in sorted(by_cat):
        t = sum(1 for i in train_ids if i in by_cat[cat])
        h = sum(1 for i in holdout_ids if i in by_cat[cat])
        print(f"  {cat:14} {t:6d} {h:8d}")


if __name__ == "__main__":
    main()
