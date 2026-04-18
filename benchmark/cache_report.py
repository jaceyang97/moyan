"""Cache-hit reporter: measures how much of the moyan system-prompt overhead is
actually billed, given Anthropic ephemeral prompt caching.

Anthropic cache pricing (relative to base input token cost):
  base input:          1.00×
  cache creation:      1.25×
  cache read:          0.10×

For a big system prompt like SKILL.md (~2.95k tokens), caching matters a lot
on turn 2+ of multi-turn conversations.

Usage:
  python cache_report.py --run-id v2-haiku
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

from lib import BASELINE_GROUP, BENCH_ROOT, GROUPS


CACHE_MULT = {"input": 1.00, "creation": 1.25, "read": 0.10}


def iter_traces(run_id: str):
    d = BENCH_ROOT / "traces" / run_id
    for p in sorted(d.glob("*.json")):
        if p.name.startswith("."):
            continue
        yield json.loads(p.read_text(encoding="utf-8"))


def effective_input(u: dict) -> float:
    return (u["input_tokens"] * CACHE_MULT["input"]
            + u.get("cache_creation_input_tokens", 0) * CACHE_MULT["creation"]
            + u.get("cache_read_input_tokens", 0) * CACHE_MULT["read"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()

    bucket: dict[tuple[str, int], dict[str, float]] = defaultdict(
        lambda: {"n": 0, "in": 0, "cache_r": 0, "cache_w": 0, "out": 0, "eff_in": 0.0})

    for t in iter_traces(args.run_id):
        if t.get("error"):
            continue
        # turns layout is [u, a, u, a, ...]; turn index = assistant-reply index
        turn_idx = max(0, len(t["turns"]) // 2 - 1)
        u = t["usage"]
        b = bucket[(t["group"], turn_idx)]
        b["n"] += 1
        b["in"] += u["input_tokens"]
        b["cache_r"] += u.get("cache_read_input_tokens", 0)
        b["cache_w"] += u.get("cache_creation_input_tokens", 0)
        b["out"] += u["output_tokens"]
        b["eff_in"] += effective_input(u)

    groups = sorted({g for (g, _) in bucket.keys()}, key=lambda g: list(GROUPS.keys()).index(g) if g in GROUPS else 99)
    turns = sorted({t for (_, t) in bucket.keys()})

    print(f"=== cache report · run={args.run_id} ===\n")
    print(f"{'group':<20} {'turn':>4} {'n':>4} {'avg_in':>8} {'avg_cache_r':>11} "
          f"{'avg_cache_w':>11} {'avg_out':>8} {'avg_eff_in':>10} {'cache_hit%':>10}")
    for g in groups:
        for t in turns:
            b = bucket.get((g, t))
            if not b or b["n"] == 0:
                continue
            n = b["n"]
            cache_hit_pct = 100 * b["cache_r"] / (b["in"] + b["cache_r"] + b["cache_w"]) \
                if (b["in"] + b["cache_r"] + b["cache_w"]) else 0
            print(f"{g:<20} {t:>4} {n:>4} {b['in']/n:>8.0f} {b['cache_r']/n:>11.0f} "
                  f"{b['cache_w']/n:>11.0f} {b['out']/n:>8.0f} {b['eff_in']/n:>10.1f} "
                  f"{cache_hit_pct:>9.1f}%")

    print(f"\n--- turn-0 effective input tokens vs {BASELINE_GROUP} ---")
    base = bucket.get((BASELINE_GROUP, 0))
    if base and base["n"]:
        base_eff = base["eff_in"] / base["n"]
        for g in groups:
            b = bucket.get((g, 0))
            if not b or b["n"] == 0:
                continue
            g_eff = b["eff_in"] / b["n"]
            delta = g_eff - base_eff
            sign = "+" if delta >= 0 else ""
            print(f"  {g:<20}  eff_in={g_eff:>7.1f}   Δ vs B = {sign}{delta:.1f}")

    mt_turns = [t for t in turns if t > 0]
    if mt_turns:
        print("\n--- multi-turn cache warm-up (same group, turn 0 vs last) ---")
        for g in groups:
            t0 = bucket.get((g, 0))
            tlast = None
            for t in sorted(mt_turns, reverse=True):
                if bucket.get((g, t)):
                    tlast = bucket[(g, t)]
                    tlast_idx = t
                    break
            if not t0 or not tlast or t0["n"] == 0 or tlast["n"] == 0:
                continue
            t0_eff = t0["eff_in"] / t0["n"]
            tl_eff = tlast["eff_in"] / tlast["n"]
            t0_raw = t0["in"] / t0["n"]
            tl_raw = tlast["in"] / tlast["n"]
            print(f"  {g:<20}  t0: raw={t0_raw:.0f} eff={t0_eff:.1f} | "
                  f"t{tlast_idx}: raw={tl_raw:.0f} eff={tl_eff:.1f}")


if __name__ == "__main__":
    main()
