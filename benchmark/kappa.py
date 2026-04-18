"""Inter-judge agreement (κ) across two LLM judges on the same trace pairs.

Usage:
  # 1. Judge run already produced _judgments/ with judge-model-A (e.g. Opus 4.6)
  # 2. Run a second judge on the same pairs:
  python kappa.py judge2 --run-id v2-haiku --judge-model claude-sonnet-4-6 --limit 30
  # 3. Compute κ between the two judges:
  python kappa.py score --run-id v2-haiku \\
      --judge-a claude-opus-4-6 --judge-b claude-sonnet-4-6

The second-judge output lands in _judgments_kappa/{safe_model}/ so primary results
are untouched.
"""
from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from lib import BASELINE_GROUP, MOYAN_GROUPS, BENCH_ROOT, get_client, load_prompts
from judge import judge_pair, load_response


LABELS = ["full", "partial", "missing"]


def kappa_judgment_path(run_id: str, prompt_id: str, judge_model: str,
                        responder_model: str, moyan_group: str, seed: int) -> Path:
    safe_judge = judge_model.replace("/", "_")
    safe_resp = responder_model.replace("/", "_")
    d = BENCH_ROOT / "traces" / run_id / "_judgments_kappa" / safe_judge
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{prompt_id}__{safe_resp}__{moyan_group}__seed{seed}.json"


def cmd_judge2(args):
    """Run a second judge on the same pairs that judge.py produced."""
    client = get_client()
    prompts = {p["id"]: p for p in load_prompts()}
    moyan_groups = [g.strip() for g in args.moyan_groups.split(",")]

    trace_dir = BENCH_ROOT / "traces" / args.run_id
    primary_jdir = trace_dir / "_judgments"
    if not primary_jdir.exists():
        raise SystemExit(f"no primary judgments at {primary_jdir} — run judge.py first")

    # Find all primary judgments — those define which pairs to judge again.
    primary_files = sorted(primary_jdir.glob("*.json"))

    # Stratified-by-primary-verdict sampling if --limit is set.
    rng = random.Random(args.rng_seed)
    if args.limit and args.limit < len(primary_files):
        by_verdict: dict[str, list[Path]] = {}
        for f in primary_files:
            try:
                v = json.loads(f.read_text(encoding="utf-8")).get("completeness", "ERR")
            except Exception:
                v = "ERR"
            by_verdict.setdefault(v, []).append(f)
        per_bucket = max(1, args.limit // max(1, len(by_verdict)))
        chosen: list[Path] = []
        for v, files in by_verdict.items():
            rng.shuffle(files)
            chosen.extend(files[:per_bucket])
        primary_files = chosen[: args.limit]

    n_done = n_skipped = n_err = 0
    for pf in primary_files:
        prim = json.loads(pf.read_text(encoding="utf-8"))
        prompt_id = prim["prompt_id"]
        responder_model = prim["model"]
        mg = prim["moyan_group"]
        seed = prim["seed"]
        outp = kappa_judgment_path(args.run_id, prompt_id, args.judge_model,
                                   responder_model, mg, seed)
        if outp.exists() and not args.force:
            n_skipped += 1
            continue

        baseline = load_response(args.run_id, prompt_id, BASELINE_GROUP, seed)
        moyan = load_response(args.run_id, prompt_id, mg, seed)
        if not baseline or not moyan or baseline.get("error") or moyan.get("error"):
            continue
        prompt = prompts[prompt_id]
        question = prompt.get("prompt") or " | ".join(prompt.get("turns", []))

        try:
            judgment = judge_pair(
                client=client,
                judge_model=args.judge_model,
                question=question,
                baseline_resp=baseline["response"],
                moyan_resp=moyan["response"],
                rng=rng,
            )
        except Exception as e:  # noqa: BLE001
            judgment = {"error": f"{type(e).__name__}: {e}"}
            n_err += 1

        judgment["prompt_id"] = prompt_id
        judgment["model"] = responder_model
        judgment["moyan_group"] = mg
        judgment["seed"] = seed
        judgment["_judge_model"] = args.judge_model
        outp.write_text(json.dumps(judgment, ensure_ascii=False, indent=2), encoding="utf-8")
        n_done += 1
        print(f"  {prompt_id:32} {mg:18} seed={seed} → {judgment.get('completeness', 'ERR')}")

    print(f"\ndone. judged={n_done} skipped={n_skipped} errors={n_err}")


def cmd_score(args):
    """Compute Cohen's κ (unweighted + linear-weighted) between two judges."""
    run_dir = BENCH_ROOT / "traces" / args.run_id
    dir_a = run_dir / "_judgments"
    safe_b = args.judge_b.replace("/", "_")
    dir_b = run_dir / "_judgments_kappa" / safe_b

    if not dir_a.exists() or not dir_b.exists():
        raise SystemExit(f"missing dirs: a={dir_a.exists()} b={dir_b.exists()}")

    # Match by filename (same prompt/model/group/seed → same filename).
    pairs: list[tuple[str, str]] = []
    raw_rows: list[dict] = []
    for fa in sorted(dir_a.glob("*.json")):
        fb = dir_b / fa.name
        if not fb.exists():
            continue
        ja = json.loads(fa.read_text(encoding="utf-8"))
        jb = json.loads(fb.read_text(encoding="utf-8"))
        la = ja.get("completeness")
        lb = jb.get("completeness")
        if la in LABELS and lb in LABELS:
            pairs.append((la, lb))
            raw_rows.append({
                "prompt_id": ja.get("prompt_id"), "group": ja.get("moyan_group"),
                "seed": ja.get("seed"), "a": la, "b": lb,
            })

    n = len(pairs)
    if n == 0:
        raise SystemExit("no matched pairs")

    # Confusion matrix
    idx = {l: i for i, l in enumerate(LABELS)}
    k = len(LABELS)
    cm = [[0] * k for _ in range(k)]
    for la, lb in pairs:
        cm[idx[la]][idx[lb]] += 1

    # Observed agreement and chance agreement (Cohen κ).
    p_o = sum(cm[i][i] for i in range(k)) / n
    row_tot = [sum(cm[i]) for i in range(k)]
    col_tot = [sum(cm[i][j] for i in range(k)) for j in range(k)]
    p_e = sum((row_tot[i] * col_tot[i]) / (n * n) for i in range(k))
    kappa = (p_o - p_e) / (1 - p_e) if p_e < 1 else float("nan")

    # Linear-weighted κ (treat full/partial/missing as ordinal 0/1/2).
    def w(i, j): return 1 - abs(i - j) / (k - 1)
    po_w = sum(w(i, j) * cm[i][j] for i in range(k) for j in range(k)) / n
    pe_w = sum(w(i, j) * row_tot[i] * col_tot[j] / (n * n)
               for i in range(k) for j in range(k))
    kappa_w = (po_w - pe_w) / (1 - pe_w) if pe_w < 1 else float("nan")

    print(f"matched pairs: n={n}")
    print(f"judge A: {args.judge_a}   judge B: {args.judge_b}")
    print("\nconfusion (rows=A, cols=B):")
    print(f"  {'':10}" + "".join(f"{l:>10}" for l in LABELS))
    for i, l in enumerate(LABELS):
        print(f"  {l:10}" + "".join(f"{cm[i][j]:>10}" for j in range(k)))
    print(f"\nobserved agreement:  {p_o:.3f}")
    print(f"chance agreement:    {p_e:.3f}")
    print(f"Cohen's κ (unwt):    {kappa:.3f}")
    print(f"Cohen's κ (linear):  {kappa_w:.3f}")

    # κ interpretation (Landis & Koch 1977): <0 poor, 0-.20 slight, .21-.40 fair,
    # .41-.60 moderate, .61-.80 substantial, .81-1 almost perfect.
    def bucket(x):
        return ("poor" if x < 0 else "slight" if x < .21 else "fair" if x < .41
                else "moderate" if x < .61 else "substantial" if x < .81 else "almost perfect")
    print(f"\ninterpretation:      {bucket(kappa)} (unwt), {bucket(kappa_w)} (wt)")

    if args.out:
        Path(args.out).write_text(json.dumps({
            "n": n, "judge_a": args.judge_a, "judge_b": args.judge_b,
            "confusion": {LABELS[i]: {LABELS[j]: cm[i][j] for j in range(k)} for i in range(k)},
            "p_observed": p_o, "p_chance": p_e,
            "kappa_unweighted": kappa, "kappa_linear_weighted": kappa_w,
            "rows": raw_rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwrote {args.out}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    j2 = sub.add_parser("judge2", help="run second judge on same pairs")
    j2.add_argument("--run-id", required=True)
    j2.add_argument("--judge-model", required=True,
                    help="e.g. claude-sonnet-4-6 (should differ from primary)")
    j2.add_argument("--moyan-groups", default=",".join(MOYAN_GROUPS))
    j2.add_argument("--limit", type=int, default=0,
                    help="stratified-by-primary-verdict sample; 0 = judge every primary pair")
    j2.add_argument("--rng-seed", type=int, default=7)
    j2.add_argument("--force", action="store_true")
    j2.set_defaults(func=cmd_judge2)

    sc = sub.add_parser("score", help="compute κ between two judges")
    sc.add_argument("--run-id", required=True)
    sc.add_argument("--judge-a", required=True, help="primary judge model (for labeling)")
    sc.add_argument("--judge-b", required=True, help="second judge model")
    sc.add_argument("--out", default="", help="optional JSON output path")
    sc.set_defaults(func=cmd_score)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
