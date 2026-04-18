"""Scalar metric for the autoskill loop. Analog of autoresearch/prepare.py.

Runs D_moyan_jing on a split, compares to precomputed B_zh_normal baseline,
prints `score: <float>` (grep-friendly). Agent reads stdout to decide keep/revert.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from lib import BASELINE_GROUP, BENCH_ROOT, get_client, load_prompts

MOYAN_GROUP = "D_moyan_jing"
DEFAULT_MODEL = "claude-sonnet-4-5"
JUDGE_MODEL = "claude-sonnet-4-5"

# Score formula (matches v1 autoskill, kept for continuity):
#   score = delta_median - 0.5 * max(0, 0.70 - completeness_full) - 0.2 * guard_fails
# Threshold 0.70 (not 0.95) because pair-compare judge over-flags "missing"
# on legitimate compression — see RESULTS.md.
COMPLETENESS_TARGET = 0.70
COMPLETENESS_PENALTY = 0.5
GUARD_PENALTY = 0.2


def run_bench(run_id: str, prompt_file: Path, model: str,
              max_attempts: int = 3, min_traces: int = 30) -> bool:
    """Subprocess into run.py for D_moyan_jing on the given prompt list.
    Retries on partial failure; resumes by dropping --force after attempt 1."""
    cmd = [
        sys.executable, "-u", str(BENCH_ROOT / "run.py"),
        "--run-id", run_id,
        "--groups", MOYAN_GROUP,
        "--prompt-file", str(prompt_file),
        "--samples", "1",
        "--models", model,
        "--force",
    ]
    log_path = BENCH_ROOT / "traces" / run_id / "_bench.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, max_attempts + 1):
        with log_path.open("a") as logf:
            logf.write(f"\n--- attempt {attempt} ---\n")
            r = subprocess.run(cmd, cwd=BENCH_ROOT, stdout=logf,
                               stderr=subprocess.STDOUT)
        if "--force" in cmd:
            cmd.remove("--force")  # subsequent attempts resume completed traces
        n = len(list((BENCH_ROOT / "traces" / run_id).glob(
            f"*__{MOYAN_GROUP}__*.json")))
        if r.returncode == 0 and n >= min_traces:
            return True
        print(f"!! bench attempt {attempt}: rc={r.returncode}, traces={n}",
              file=sys.stderr)
        time.sleep(5 * attempt)
    return False


def load_out_tokens(run_id: str, group: str) -> dict[str, int]:
    """Sum output_tokens per prompt_id (handles multi-turn)."""
    d = BENCH_ROOT / "traces" / run_id
    totals: dict[str, int] = Counter()
    for p in d.glob(f"*__{group}__*.json"):
        if "_judgments" in p.parts:
            continue
        t = json.loads(p.read_text(encoding="utf-8"))
        if t.get("error"):
            continue
        totals[t["prompt_id"]] += t["usage"]["output_tokens"]
    return dict(totals)


def compute_deltas(iter_run_id: str, baseline_run_id: str
                   ) -> tuple[list[float], int]:
    moyan = load_out_tokens(iter_run_id, MOYAN_GROUP)
    base = load_out_tokens(baseline_run_id, BASELINE_GROUP)
    deltas = []
    for pid, m in moyan.items():
        b = base.get(pid)
        if not b:
            continue
        deltas.append(1 - m / b)
    return deltas, len(deltas)


def guard_fails(run_id: str) -> int:
    prompts = {p["id"]: p for p in load_prompts()}
    d = BENCH_ROOT / "traces" / run_id
    fails = 0
    for p in d.glob(f"*__{MOYAN_GROUP}__*.json"):
        if "_judgments" in p.parts:
            continue
        t = json.loads(p.read_text(encoding="utf-8"))
        pinfo = prompts.get(t["prompt_id"], {})
        exp = pinfo.get("expected")
        a = t.get("analysis", {})
        if exp == "auto_clarity" and not a.get("contains_warning"):
            fails += 1
        if exp == "preserve_code" and not a.get("has_code_block"):
            fails += 1
    return fails


def run_judge_subset(iter_run_id: str, baseline_run_id: str,
                     prompt_ids: list[str]) -> float | None:
    """Judge a fixed subset. Returns completeness_full_rate or None on fail."""
    from judge import judge_pair  # local import to avoid hard dep at module load

    client = get_client()
    prompts = {p["id"]: p for p in load_prompts()}
    rng = random.Random(42)

    base_traces = {p.stem.split("__")[0]: p for p in
                   (BENCH_ROOT / "traces" / baseline_run_id).glob(
                       f"*__{BASELINE_GROUP}__seed0.json")}
    iter_traces = {p.stem.split("__")[0]: p for p in
                   (BENCH_ROOT / "traces" / iter_run_id).glob(
                       f"*__{MOYAN_GROUP}__seed0.json")}

    jdir = BENCH_ROOT / "traces" / iter_run_id / "_judgments"
    jdir.mkdir(parents=True, exist_ok=True)

    results: list[str] = []
    for pid in prompt_ids:
        if pid not in base_traces or pid not in iter_traces:
            continue
        base = json.loads(base_traces[pid].read_text(encoding="utf-8"))
        moy = json.loads(iter_traces[pid].read_text(encoding="utf-8"))
        if base.get("error") or moy.get("error"):
            continue
        q = prompts[pid].get("prompt") or " | ".join(prompts[pid].get("turns", []))
        try:
            j = judge_pair(client=client, judge_model=JUDGE_MODEL,
                           question=q, baseline_resp=base["response"],
                           moyan_resp=moy["response"], rng=rng)
            j["prompt_id"] = pid
            (jdir / f"{pid}.json").write_text(
                json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
            if "completeness" in j:
                results.append(j["completeness"])
        except Exception as e:  # noqa: BLE001
            print(f"!! judge {pid}: {e}", file=sys.stderr)
    if not results:
        return None
    return sum(1 for r in results if r == "full") / len(results)


def compute_score(delta_median: float, completeness_full: float | None,
                  guard_fails_n: int) -> float:
    q_penalty = 0.0
    if completeness_full is not None:
        q_penalty = COMPLETENESS_PENALTY * max(
            0.0, COMPLETENESS_TARGET - completeness_full)
    return delta_median - q_penalty - GUARD_PENALTY * guard_fails_n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True,
                    help="run_id for this iteration's traces")
    ap.add_argument("--baseline", required=True,
                    help="run_id holding the precomputed B_zh_normal baseline")
    ap.add_argument("--split", default="train", choices=["train", "holdout"],
                    help="which prompt split to evaluate on")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--with-judge", action="store_true",
                    help="run a 10-prompt judge subset (adds ~$0.10)")
    ap.add_argument("--judge-n", type=int, default=10,
                    help="prompts to judge when --with-judge")
    ap.add_argument("--skip-bench", action="store_true",
                    help="skip the bench call; assume traces already exist")
    args = ap.parse_args()

    split_file = BENCH_ROOT / "splits" / f"{args.split}.txt"
    if not split_file.exists():
        print(f"status: fail:no-split-file:{split_file}")
        sys.exit(1)

    base_dir = BENCH_ROOT / "traces" / args.baseline
    if not any(base_dir.glob(f"*__{BASELINE_GROUP}__*.json")):
        print(f"status: fail:no-baseline-traces:{base_dir}")
        sys.exit(1)

    if not args.skip_bench:
        ok = run_bench(args.run_id, split_file, args.model)
        if not ok:
            print("status: fail:bench-failed")
            sys.exit(1)

    deltas, n_paired = compute_deltas(args.run_id, args.baseline)
    if not deltas:
        print("status: fail:no-paired-prompts")
        sys.exit(1)

    delta_median = statistics.median(deltas)
    delta_mean = statistics.mean(deltas)
    gfails = guard_fails(args.run_id)

    completeness: float | None = None
    if args.with_judge:
        ids = [l.strip() for l in split_file.read_text().splitlines()
               if l.strip()][: args.judge_n]
        completeness = run_judge_subset(args.run_id, args.baseline, ids)

    score = compute_score(delta_median, completeness, gfails)

    # Grep-friendly output. autoresearch greps `^val_bpb:`; we grep `^score:`.
    print(f"score: {score:.4f}")
    print(f"delta_median: {delta_median:.4f}")
    print(f"delta_mean: {delta_mean:.4f}")
    print(f"n_paired: {n_paired}")
    print(f"completeness_full: {completeness:.4f}" if completeness is not None
          else "completeness_full: skipped")
    print(f"guard_fails: {gfails}")
    print("status: ok")


if __name__ == "__main__":
    main()
