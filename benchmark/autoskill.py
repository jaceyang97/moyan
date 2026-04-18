"""autoskill: autonomous SKILL.md optimization loop.

Pattern: karpathy/autoresearch adapted for prompt-file optimization.

Each iteration:
  1. Proposer LLM reads state → returns {hypothesis, new_skill_md_body}
  2. Harness writes SKILL.md (frontmatter preserved) + git commits
  3. Harness runs benchmark on train split (D_moyan_jing only; B baseline pre-computed once)
  4. Harness scores: delta_out_median − 0.5·max(0, 0.95−completeness) − 0.2·guard_fails
  5. If score improves: keep; else: git reset --hard HEAD^

Stops on: max iters, plateau (no improvement for K), or budget exhausted.

Usage:
  python autoskill.py --tag v1 --baseline-run-id v0 --max-iters 20 --judge-every 3
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from lib import (
    BASELINE_GROUP,
    BENCH_ROOT,
    SKILL_PATH,
    analyze_response,
    get_client,
    load_prompts,
)

REPO_ROOT = SKILL_PATH.parent.parent.parent
TRAIN_LIST = BENCH_ROOT / "splits" / "train.txt"
AUTOSKILL_MD = BENCH_ROOT / "AUTOSKILL.md"
TSV_PATH = BENCH_ROOT / "results" / "autoskill.tsv"

PROPOSER_MODEL = "claude-sonnet-4-5"
BENCH_MODEL = "claude-sonnet-4-5"
JUDGE_MODEL = "claude-sonnet-4-5"


# ------------------------- SKILL.md IO -------------------------

def split_skill(text: str) -> tuple[str, str]:
    """Split SKILL.md into (frontmatter_block_with_delims, body)."""
    if not text.startswith("---"):
        raise ValueError("SKILL.md missing YAML frontmatter")
    m = re.match(r"(---\n.*?\n---\n)(.*)", text, re.DOTALL)
    if not m:
        raise ValueError("SKILL.md frontmatter malformed")
    return m.group(1), m.group(2).lstrip("\n")


def write_skill(new_body: str):
    current = SKILL_PATH.read_text(encoding="utf-8")
    frontmatter, _ = split_skill(current)
    SKILL_PATH.write_text(frontmatter + "\n" + new_body.rstrip() + "\n", encoding="utf-8")


# ------------------------- Validation of proposal -------------------------

HARD_CONSTRAINTS = {
    "has_level_table": lambda body: all(x in body for x in ["简", "精", "文言文"]),
    "has_commit_section": lambda body: "commit" in body.lower() and ("Conventional" in body or "conventional" in body or "祈使" in body),
    "has_review_section": lambda body: "review" in body.lower() or "审查" in body or "review 代码" in body,
    "has_auto_clarity": lambda body: ("Auto-Clarity" in body or "破例" in body),
    "no_holdout_leak": lambda body: "[HOLDOUT]" not in body and "holdout" not in body.lower(),
}


def validate_proposal(new_body: str, old_body: str) -> tuple[bool, str]:
    # Size bound
    old_n = len(old_body)
    new_n = len(new_body)
    if new_n == 0:
        return False, "empty body"
    ratio = new_n / old_n
    if ratio < 0.7 or ratio > 1.3:
        return False, f"size change {ratio:.2f}× outside [0.7, 1.3]"
    for name, check in HARD_CONSTRAINTS.items():
        if not check(new_body):
            return False, f"failed constraint: {name}"
    return True, "ok"


# ------------------------- Git helpers -------------------------

def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=REPO_ROOT, check=check,
                       capture_output=True, text=True)
    if r.returncode != 0 and check:
        raise RuntimeError(f"git {args}: {r.stderr}")
    return r.stdout.strip()


def git_head() -> str:
    return git("rev-parse", "HEAD")


def git_commit_skill(message: str):
    git("add", "skills/moyan/SKILL.md")
    git("commit", "-m", message, "--allow-empty")


def git_revert_to(sha: str):
    git("reset", "--hard", sha)


# ------------------------- Eval -------------------------

def run_bench(run_id: str, prompt_file: Path, groups: str = "D_moyan_jing",
              model: str = BENCH_MODEL, samples: int = 1, force: bool = True,
              max_attempts: int = 3, min_traces: int = 30):
    """Run benchmark, streaming output to a log file. Retries on failure;
    drops --force after first attempt so completed traces are skipped (resume)."""
    cmd = [
        sys.executable, "-u", str(BENCH_ROOT / "run.py"),
        "--run-id", run_id,
        "--groups", groups,
        "--prompt-file", str(prompt_file),
        "--samples", str(samples),
        "--models", model,
    ]
    if force:
        cmd.append("--force")
    log_path = BENCH_ROOT / "traces" / run_id / "_bench.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    primary_group = groups.split(",")[0]
    for attempt in range(1, max_attempts + 1):
        with log_path.open("a") as logf:
            logf.write(f"\n--- attempt {attempt} ---\n")
            r = subprocess.run(cmd, cwd=BENCH_ROOT, stdout=logf,
                               stderr=subprocess.STDOUT)
        if "--force" in cmd:
            cmd.remove("--force")  # subsequent attempts resume
        n = len(list((BENCH_ROOT / "traces" / run_id).glob(f"*__{primary_group}__*.json")))
        if r.returncode == 0 and n >= min_traces:
            return True
        print(f"!! bench attempt {attempt}: rc={r.returncode}, traces={n}", file=sys.stderr)
        time.sleep(5 * attempt)
    return False


def maybe_push(branch: str):
    """Best-effort git push. Doesn't raise on failure."""
    try:
        r = subprocess.run(["git", "push", "-u", "origin", branch],
                           cwd=REPO_ROOT, capture_output=True, text=True, timeout=60)
        print(f"  push {branch}: {'ok' if r.returncode == 0 else r.stderr[-200:]}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"!! push exception: {e}", file=sys.stderr)


def load_out_tokens(run_id: str, group: str) -> dict[str, int]:
    """Return {prompt_id: total_output_tokens} for a given group in a run.
    Sums across multi-turn entries."""
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


def guard_fails(run_id: str, group: str) -> int:
    prompts = {p["id"]: p for p in load_prompts()}
    d = BENCH_ROOT / "traces" / run_id
    fails = 0
    for p in d.glob(f"*__{group}__*.json"):
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


def compute_delta_median(iter_run_id: str, baseline_run_id: str) -> tuple[float, int]:
    moyan = load_out_tokens(iter_run_id, "D_moyan_jing")
    base = load_out_tokens(baseline_run_id, BASELINE_GROUP)
    deltas = []
    for pid, m in moyan.items():
        b = base.get(pid)
        if not b:
            continue
        deltas.append(1 - m / b)
    if not deltas:
        return float("nan"), 0
    return float(np.median(deltas)), len(deltas)


def run_judge_subset(iter_run_id: str, baseline_run_id: str, n_prompts: int = 10) -> float | None:
    """Judge a fixed 10-prompt subset. Returns completeness_full_rate."""
    # Use first 10 train prompts (deterministic).
    with TRAIN_LIST.open() as f:
        ids = [l.strip() for l in f if l.strip()][:n_prompts]
    client = get_client()
    # Import here to avoid circular
    from judge import judge_pair  # type: ignore

    prompts = {p["id"]: p for p in load_prompts()}
    import random
    rng = random.Random(42)
    results = []
    base_traces = {p.stem.split("__")[0]: p
                   for p in (BENCH_ROOT / "traces" / baseline_run_id).glob(f"*__{BASELINE_GROUP}__seed0.json")}
    iter_traces = {p.stem.split("__")[0]: p
                   for p in (BENCH_ROOT / "traces" / iter_run_id).glob("*__D_moyan_jing__seed0.json")}

    jdir = BENCH_ROOT / "traces" / iter_run_id / "_judgments"
    jdir.mkdir(parents=True, exist_ok=True)
    for pid in ids:
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
            (jdir / f"{pid}.json").write_text(json.dumps(j, ensure_ascii=False, indent=2), encoding="utf-8")
            if "completeness" in j:
                results.append(j["completeness"])
        except Exception as e:  # noqa: BLE001
            print(f"  judge err {pid}: {e}", file=sys.stderr)
    if not results:
        return None
    return sum(1 for r in results if r == "full") / len(results)


def compute_score(delta_median: float, completeness_full: float | None,
                  guard_fails_n: int) -> float:
    # Threshold 0.70 (not 0.95): pair-compare judge flags baseline verbosity
    # as "missing", so 40-50% complete often reflects appropriate compression.
    q_penalty = 0.0
    if completeness_full is not None:
        q_penalty = 0.5 * max(0.0, 0.70 - completeness_full)
    return delta_median - q_penalty - 0.2 * guard_fails_n


# ------------------------- Proposer -------------------------

def weak_points_snippet(baseline_run_id: str, top_k: int = 5) -> str:
    """Find top_k under-compressed prompts + brief excerpt of both responses."""
    moyan_cur = load_out_tokens(baseline_run_id, "D_moyan_jing")
    base = load_out_tokens(baseline_run_id, BASELINE_GROUP)
    if not moyan_cur:
        # Fallback: no D traces in baseline_run_id yet (first iter). Use any.
        return "(no prior iteration data)"

    deltas = []
    for pid, m in moyan_cur.items():
        b = base.get(pid)
        if not b:
            continue
        deltas.append((pid, 1 - m / b, b, m))
    deltas.sort(key=lambda x: x[1])
    weakest = deltas[:top_k]

    lines = []
    for pid, d, b, m in weakest:
        # Load responses (seed0 path)
        base_p = BENCH_ROOT / "traces" / baseline_run_id / f"{pid}__{BASELINE_GROUP}__seed0.json"
        moy_p = BENCH_ROOT / "traces" / baseline_run_id / f"{pid}__D_moyan_jing__seed0.json"
        if not base_p.exists() or not moy_p.exists():
            continue
        br = json.loads(base_p.read_text(encoding="utf-8"))["response"][:400]
        mr = json.loads(moy_p.read_text(encoding="utf-8"))["response"][:400]
        lines.append(f"### {pid} — Δ={d:.1%}  (baseline {b} tok → moyan {m} tok)")
        lines.append(f"**Baseline excerpt:**\n{br}\n")
        lines.append(f"**Moyan excerpt:**\n{mr}\n---\n")
    return "\n".join(lines)


def history_snippet(rows: list[dict], n: int = 5) -> str:
    if not rows:
        return "(first iteration — no history)"
    recent = rows[-n:]
    lines = ["| iter | hypothesis | score | Δ_out_med | complete_full | guard_fails | decision |",
             "|------|------------|-------|-----------|---------------|-------------|----------|"]
    for r in recent:
        lines.append(
            f"| {r['iter']} | {r['hypothesis'][:50]} | {r['score']:.3f} | "
            f"{r['delta_median']:.3f} | {r.get('completeness_full') or '—'} | "
            f"{r['guard_fails']} | {r['decision']} |"
        )
    return "\n".join(lines)


def propose(client, current_body: str, baseline_run_id: str,
            history: list[dict], best_score: float) -> dict:
    system = AUTOSKILL_MD.read_text(encoding="utf-8")
    weak = weak_points_snippet(baseline_run_id)
    hist = history_snippet(history)
    user = f"""# 当前 SKILL.md body

{current_body}

# 当前最佳 score: {best_score:.3f}

# 最近实验历史

{hist}

# 弱点样本（当前最难压缩的 prompt + 真实回复对比）

{weak}

---

基于以上：提议一处**具体**、**小**的编辑。只改一件事，便于归因。返回 JSON。
"""
    resp = client.messages.create(
        model=PROPOSER_MODEL,
        system=system,
        messages=[{"role": "user", "content": user}],
        max_tokens=8192,
        temperature=0.3,  # light diversity between iterations
    )
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    text = text.strip()
    # Strip outer code fence if model added one despite instructions
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```\s*$", "", text)

    # Parse: first line is JSON metadata, then <<<BODY_START>>>...<<<BODY_END>>>
    body_match = re.search(r"<<<BODY_START>>>\s*(.*?)\s*<<<BODY_END>>>", text, re.DOTALL)
    if not body_match:
        raise ValueError(f"body markers not found. First 300 chars: {text[:300]}")
    new_body = body_match.group(1).strip() + "\n"

    meta_text = text[: body_match.start()].strip()
    meta_match = re.search(r"\{[^\n]*\}", meta_text)
    if not meta_match:
        raise ValueError(f"JSON metadata not found before body. Got: {meta_text[:200]}")
    meta = json.loads(meta_match.group(0))
    if "hypothesis" not in meta:
        raise ValueError(f"missing hypothesis in metadata: {meta}")

    proposal = {"hypothesis": meta["hypothesis"], "new_skill_md_body": new_body}
    proposal["_usage"] = {
        "input_tokens": getattr(resp.usage, "input_tokens", 0),
        "output_tokens": getattr(resp.usage, "output_tokens", 0),
    }
    return proposal


# ------------------------- TSV log -------------------------

TSV_COLS = [
    "iter", "timestamp", "hypothesis", "score", "delta_median",
    "n_paired", "completeness_full", "guard_fails", "decision", "commit_sha",
    "proposer_tokens_in", "proposer_tokens_out",
]


def append_tsv(row: dict):
    TSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    header_needed = not TSV_PATH.exists()
    with TSV_PATH.open("a", encoding="utf-8") as f:
        if header_needed:
            f.write("\t".join(TSV_COLS) + "\n")
        f.write("\t".join(str(row.get(c, "")) for c in TSV_COLS) + "\n")


def load_tsv() -> list[dict]:
    if not TSV_PATH.exists():
        return []
    df = pd.read_csv(TSV_PATH, sep="\t")
    return df.to_dict(orient="records")


# ------------------------- Main loop -------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="v1")
    ap.add_argument("--baseline-run-id", default="v0",
                    help="run_id holding the B baseline traces (computed once)")
    ap.add_argument("--max-iters", type=int, default=20)
    ap.add_argument("--plateau-k", type=int, default=5,
                    help="stop if no improvement > 0.02 in last K iters")
    ap.add_argument("--judge-every", type=int, default=3,
                    help="run subset judge every N iterations")
    ap.add_argument("--push-branch", default="",
                    help="git branch to push after each kept iter (best-effort)")
    ap.add_argument("--dry-run", action="store_true", help="run proposer once and exit")
    args = ap.parse_args()

    # Ensure baseline B traces exist.
    base_dir = BENCH_ROOT / "traces" / args.baseline_run_id
    if not any(base_dir.glob(f"*__{BASELINE_GROUP}__*.json")):
        raise SystemExit(f"baseline traces not found under {base_dir}. Run run.py first.")

    client = get_client()
    history = load_tsv()
    best_score = max((h["score"] for h in history), default=-1.0)

    # Resume orphan: if HEAD is "autoskill <tag> iter N" but TSV has no row N,
    # the harness was killed mid-iter. Just reset HEAD^ so the SKILL.md is
    # clean. The wasted traces remain for debug but don't contaminate scoring.
    head_msg = git("log", "-1", "--pretty=%s").strip()
    existing_iters = {h["iter"] for h in history}
    m = re.match(rf"autoskill {re.escape(args.tag)} iter (\d+): ", head_msg)
    if m and int(m.group(1)) not in existing_iters:
        orphan_iter = int(m.group(1))
        print(f"!! orphan detected: HEAD is iter {orphan_iter} but no TSV row. Reverting.", flush=True)
        git_revert_to(f"HEAD^")

    for i in range(len(history), len(history) + args.max_iters):
        print(f"\n{'='*60}\nautoskill iter {i} · best_score={best_score:.3f}  ({time.strftime('%H:%M:%S')})\n{'='*60}", flush=True)
        parent_sha = git_head()
        try:
            current = SKILL_PATH.read_text(encoding="utf-8")
            frontmatter, old_body = split_skill(current)

            # 1. Propose
            try:
                proposal = propose(client, old_body, args.baseline_run_id, history, best_score)
            except Exception as e:  # noqa: BLE001
                print(f"!! proposal failed: {e}", file=sys.stderr)
                append_tsv({
                    "iter": i, "timestamp": int(time.time()),
                    "hypothesis": f"proposal_error: {type(e).__name__}",
                    "score": -1, "delta_median": float("nan"), "n_paired": 0,
                    "completeness_full": "", "guard_fails": 0,
                    "decision": "proposal_failed", "commit_sha": parent_sha,
                    "proposer_tokens_in": 0, "proposer_tokens_out": 0,
                })
                history = load_tsv()
                time.sleep(30)
                continue

            hypothesis = proposal["hypothesis"]
            new_body = proposal["new_skill_md_body"]
            print(f"hypothesis: {hypothesis}", flush=True)

            # 2. Validate
            ok, reason = validate_proposal(new_body, old_body)
            if not ok:
                print(f"!! invalid proposal ({reason})", flush=True)
                append_tsv({
                    "iter": i, "timestamp": int(time.time()),
                    "hypothesis": hypothesis, "score": -1,
                    "delta_median": float("nan"), "n_paired": 0,
                    "completeness_full": "", "guard_fails": 0,
                    "decision": f"rejected:{reason}", "commit_sha": parent_sha,
                    "proposer_tokens_in": proposal["_usage"]["input_tokens"],
                    "proposer_tokens_out": proposal["_usage"]["output_tokens"],
                })
                history = load_tsv()
                continue

            if args.dry_run:
                print("--dry-run: stopping after proposal")
                print(f"\n--- PROPOSED BODY (first 500 chars) ---\n{new_body[:500]}")
                return

            # 3. Write + commit
            write_skill(new_body)
            git_commit_skill(f"autoskill {args.tag} iter {i}: {hypothesis}")

            # 4. Eval (with retry; streams to traces/{run_id}/_bench.log)
            run_id = f"autoskill_{args.tag}_{i:03d}"
            ok = run_bench(run_id, TRAIN_LIST)
            if not ok:
                print("!! bench failed permanently, reverting", flush=True)
                git_revert_to(parent_sha)
                append_tsv({
                    "iter": i, "timestamp": int(time.time()),
                    "hypothesis": hypothesis, "score": -1,
                    "delta_median": float("nan"), "n_paired": 0,
                    "completeness_full": "", "guard_fails": 0,
                    "decision": "bench_failed", "commit_sha": parent_sha,
                    "proposer_tokens_in": proposal["_usage"]["input_tokens"],
                    "proposer_tokens_out": proposal["_usage"]["output_tokens"],
                })
                history = load_tsv()
                continue

            delta_med, n_paired = compute_delta_median(run_id, args.baseline_run_id)
            gfails = guard_fails(run_id, "D_moyan_jing")

            completeness = None
            if (i + 1) % args.judge_every == 0:
                print("running judge subset...", flush=True)
                try:
                    completeness = run_judge_subset(run_id, args.baseline_run_id)
                except Exception as e:  # noqa: BLE001
                    print(f"!! judge failed: {e}", file=sys.stderr)

            score = compute_score(delta_med, completeness, gfails)
            print(f"Δ_med={delta_med:.3f}  completeness_full={completeness}  guard_fails={gfails}  score={score:.3f}", flush=True)

            # 5. Keep or revert
            if score > best_score + 0.02:
                best_score = score
                decision = "keep"
                kept_sha = git_head()
                if args.push_branch:
                    maybe_push(args.push_branch)
            else:
                git_revert_to(parent_sha)
                decision = "revert"
                kept_sha = parent_sha

            append_tsv({
                "iter": i, "timestamp": int(time.time()),
                "hypothesis": hypothesis, "score": round(score, 4),
                "delta_median": round(delta_med, 4), "n_paired": n_paired,
                "completeness_full": "" if completeness is None else round(completeness, 3),
                "guard_fails": gfails, "decision": decision, "commit_sha": kept_sha,
                "proposer_tokens_in": proposal["_usage"]["input_tokens"],
                "proposer_tokens_out": proposal["_usage"]["output_tokens"],
            })
            history = load_tsv()

        except KeyboardInterrupt:
            print("\n!! interrupted, stopping cleanly", flush=True)
            break
        except Exception as e:  # noqa: BLE001
            # Belt-and-suspenders: any unhandled error → log, restore tree, continue.
            print(f"!! iter {i} crashed with {type(e).__name__}: {e}", file=sys.stderr)
            try:
                git_revert_to(parent_sha)
            except Exception:
                pass
            append_tsv({
                "iter": i, "timestamp": int(time.time()),
                "hypothesis": f"crash: {type(e).__name__}",
                "score": -1, "delta_median": float("nan"), "n_paired": 0,
                "completeness_full": "", "guard_fails": 0,
                "decision": "iter_crashed", "commit_sha": parent_sha,
                "proposer_tokens_in": 0, "proposer_tokens_out": 0,
            })
            history = load_tsv()
            time.sleep(30)
            continue

        # 6. Plateau check (only after successful iters)
        if len(history) >= args.plateau_k:
            recent = history[-args.plateau_k:]
            kept = sum(1 for r in recent if r["decision"] == "keep")
            if kept == 0:
                print(f"plateau: 0 keeps in last {args.plateau_k} iters, stopping", flush=True)
                break

    print(f"\ndone. best_score={best_score:.3f}  total iters={len(history)}")
    print(f"log: {TSV_PATH}")


if __name__ == "__main__":
    main()
