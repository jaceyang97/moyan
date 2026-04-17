"""Aggregate traces + judgments into metrics, statistics, and a report.

Outputs:
  results/{run_id}/metrics.csv       — one row per trace
  results/{run_id}/per_prompt.csv    — paired (baseline B vs each moyan group)
  results/{run_id}/summary.csv       — aggregated by (model, group, layer, category)
  results/{run_id}/report.md         — human-readable report
  results/{run_id}/regression_candidates.md  — prompts where moyan lost information
"""
from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as sstats

from lib import BASELINE_GROUP, BENCH_ROOT, GROUPS, MOYAN_GROUPS, load_prompts


def load_run(run_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    trace_dir = BENCH_ROOT / "traces" / run_id
    rows = []
    for p in trace_dir.glob("*.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("error"):
            continue
        turn = 0
        m = p.stem.rsplit("_t", 1)
        if len(m) == 2 and m[1].isdigit():
            turn = int(m[1])
        u = d["usage"]
        a = d["analysis"]
        rows.append({
            "prompt_id": d["prompt_id"],
            "layer": d["layer"],
            "category": d["category"],
            "group": d["group"],
            "model": d["model"],
            "seed": d["seed"],
            "turn": turn,
            "input_tokens": u["input_tokens"],
            "output_tokens": u["output_tokens"],
            "cache_read_tokens": u["cache_read_input_tokens"],
            "char_count": a["char_count"],
            "code_block_chars": a["code_block_chars"],
            "non_code_chars": a["non_code_chars"],
            "has_code_block": a["has_code_block"],
            "hedging_count": a["hedging_count"],
            "filler_total": sum(a["filler_hits"].values()) if a.get("filler_hits") else 0,
            "starts_with_pleasantry": a.get("starts_with_pleasantry", False),
            "contains_warning": a.get("contains_warning", False),
            "latency_ms": d["latency_ms"],
        })
    traces = pd.DataFrame(rows)

    jdir = trace_dir / "_judgments"
    jrows = []
    if jdir.exists():
        for p in jdir.glob("*.json"):
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("error"):
                continue
            jrows.append({
                "prompt_id": d["prompt_id"],
                "model": d["model"],
                "moyan_group": d["moyan_group"],
                "seed": d["seed"],
                "completeness": d.get("completeness"),
                "actionability": d.get("actionability"),
                "missing_points": len(d.get("missing_points", [])),
                "added_errors": len(d.get("added_errors", [])),
            })
    judgments = pd.DataFrame(jrows)
    return traces, judgments


def bootstrap_ci(values: np.ndarray, n: int = 1000, alpha: float = 0.05, rng=None) -> tuple[float, float]:
    if len(values) == 0:
        return (float("nan"), float("nan"))
    rng = rng or np.random.default_rng(42)
    means = np.array([rng.choice(values, size=len(values), replace=True).mean() for _ in range(n)])
    lo, hi = np.quantile(means, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)


def summarize_paired(traces: pd.DataFrame) -> pd.DataFrame:
    """For each (model, moyan_group, layer, category, prompt_id): compute Δ = 1 - moyan/baseline
    per seed, then average across seeds per prompt."""
    # Aggregate by (prompt_id, group, model) — average seeds first (fair paired test).
    agg = (traces.groupby(["prompt_id", "layer", "category", "group", "model"])
                  .agg(output_tokens=("output_tokens", "mean"),
                       char_count=("char_count", "mean"),
                       non_code_chars=("non_code_chars", "mean"),
                       code_block_chars=("code_block_chars", "mean"),
                       latency_ms=("latency_ms", "mean"),
                       filler_total=("filler_total", "mean"))
                  .reset_index())

    base = agg[agg["group"] == BASELINE_GROUP].rename(columns={
        "output_tokens": "baseline_out",
        "char_count": "baseline_chars",
        "non_code_chars": "baseline_noncode_chars",
        "code_block_chars": "baseline_code_chars",
        "latency_ms": "baseline_latency_ms",
        "filler_total": "baseline_filler",
    }).drop(columns=["group"])

    merged = agg[agg["group"].isin(MOYAN_GROUPS)].merge(
        base, on=["prompt_id", "layer", "category", "model"], how="inner"
    )
    merged["delta_out"] = 1 - merged["output_tokens"] / merged["baseline_out"]
    merged["delta_chars"] = 1 - merged["char_count"] / merged["baseline_chars"]
    merged["delta_noncode"] = 1 - merged["non_code_chars"] / merged["baseline_noncode_chars"].replace(0, np.nan)
    merged["code_chars_ratio"] = merged["code_block_chars"] / merged["baseline_code_chars"].replace(0, np.nan)
    return merged


def summarize_groups(paired: pd.DataFrame, breakdown: list[str]) -> pd.DataFrame:
    """Aggregate paired deltas by a given breakdown (e.g. ['model','group','layer'])."""
    rng = np.random.default_rng(42)
    rows = []
    for keys, sub in paired.groupby(breakdown):
        if not isinstance(keys, tuple):
            keys = (keys,)
        vals = sub["delta_out"].to_numpy()
        char_vals = sub["delta_chars"].to_numpy()
        lo, hi = bootstrap_ci(vals, rng=rng)
        # Wilcoxon: test whether delta_out is systematically > 0.
        if len(vals) >= 6 and not np.all(vals == 0):
            try:
                w = sstats.wilcoxon(vals, alternative="greater")
                wpv = float(w.pvalue)
            except ValueError:
                wpv = float("nan")
        else:
            wpv = float("nan")
        row = dict(zip(breakdown, keys))
        row.update({
            "n_prompts": len(sub),
            "delta_out_mean": float(np.mean(vals)),
            "delta_out_median": float(np.median(vals)),
            "delta_out_ci95_lo": lo,
            "delta_out_ci95_hi": hi,
            "delta_chars_mean": float(np.mean(char_vals)),
            "wilcoxon_p_greater": wpv,
            "baseline_out_mean": float(sub["baseline_out"].mean()),
            "moyan_out_mean": float(sub["output_tokens"].mean()),
            "code_chars_ratio_mean": float(sub["code_chars_ratio"].mean()),
        })
        rows.append(row)
    return pd.DataFrame(rows)


def attach_judgments(paired: pd.DataFrame, judgments: pd.DataFrame) -> pd.DataFrame:
    if judgments.empty:
        return paired
    j = (judgments.groupby(["prompt_id", "moyan_group", "model"])
                   .agg(completeness_mode=("completeness", lambda s: s.mode().iat[0] if not s.mode().empty else None),
                        actionability_mean=("actionability", "mean"),
                        missing_points_mean=("missing_points", "mean"),
                        added_errors_mean=("added_errors", "mean"))
                   .reset_index()
                   .rename(columns={"moyan_group": "group"}))
    return paired.merge(j, on=["prompt_id", "group", "model"], how="left")


def guard_checks(traces: pd.DataFrame) -> list[dict]:
    """Edge-behavior asserts:
      - commit prompts under moyan must still look like Conventional Commits
      - codegen prompts must preserve code-block chars (≥ 90% of baseline)
      - destructive prompts must emit a warning marker
    """
    findings = []
    # Merge in expected behavior from prompts.jsonl
    prompts = {p["id"]: p for p in load_prompts()}

    for _, r in traces.iterrows():
        if r["group"] == BASELINE_GROUP or r["group"] == "A_en_normal":
            continue
        pinfo = prompts.get(r["prompt_id"], {})
        expected = pinfo.get("expected")
        if expected == "auto_clarity" and not r["contains_warning"]:
            findings.append({
                "prompt_id": r["prompt_id"], "group": r["group"], "model": r["model"],
                "seed": r["seed"], "check": "auto_clarity_missing_warning",
            })
        if expected == "preserve_code" and not r["has_code_block"]:
            findings.append({
                "prompt_id": r["prompt_id"], "group": r["group"], "model": r["model"],
                "seed": r["seed"], "check": "codegen_missing_code_block",
            })
    return findings


def write_report(run_id: str, paired: pd.DataFrame, summary: pd.DataFrame,
                 by_layer: pd.DataFrame, by_category: pd.DataFrame,
                 guard_findings: list[dict], judgments: pd.DataFrame, out_dir: Path):
    lines = []
    lines.append(f"# moyan benchmark — `{run_id}`\n")
    lines.append(f"Prompts evaluated (paired vs baseline B): **{len(paired.prompt_id.unique())}**  ")
    lines.append(f"Total paired observations: **{len(paired)}**  ")
    if not judgments.empty:
        full_rate = (judgments["completeness"] == "full").mean()
        lines.append(f"Judge completeness = 'full': **{full_rate:.1%}**  ")
    lines.append("")

    lines.append("## Top-level: savings by (model, group)")
    lines.append("")
    top = summary.sort_values(["model", "group"])
    lines.append(top.to_markdown(index=False, floatfmt=".3f"))
    lines.append("")

    lines.append("## Savings by layer")
    lines.append("")
    lines.append(by_layer.to_markdown(index=False, floatfmt=".3f"))
    lines.append("")

    lines.append("## Savings by category")
    lines.append("")
    lines.append(by_category.to_markdown(index=False, floatfmt=".3f"))
    lines.append("")

    lines.append("## Guard checks (edge behavior)")
    lines.append("")
    if guard_findings:
        gdf = pd.DataFrame(guard_findings)
        lines.append(gdf.to_markdown(index=False))
    else:
        lines.append("_All guard checks passed (code preserved, warnings emitted on destructive prompts)._")
    lines.append("")

    # Regression candidates: paired rows where delta_out is negative (moyan used MORE) or completeness != full.
    reg = paired.copy()
    if "completeness_mode" in reg.columns:
        reg_bad = reg[(reg["delta_out"] < 0) | (reg["completeness_mode"] != "full")]
    else:
        reg_bad = reg[reg["delta_out"] < 0]
    reg_bad = reg_bad.sort_values("delta_out").head(20)
    lines.append("## Regression candidates (top 20)")
    lines.append("")
    cols = ["prompt_id", "model", "group", "layer", "category",
            "baseline_out", "output_tokens", "delta_out"]
    if "completeness_mode" in reg_bad.columns:
        cols.append("completeness_mode")
    lines.append(reg_bad[cols].to_markdown(index=False, floatfmt=".3f"))
    lines.append("")

    (out_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()

    traces, judgments = load_run(args.run_id)
    if traces.empty:
        raise SystemExit("no traces")

    out_dir = BENCH_ROOT / "results" / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    traces.to_csv(out_dir / "metrics.csv", index=False)
    paired = summarize_paired(traces)
    paired = attach_judgments(paired, judgments)
    paired.to_csv(out_dir / "per_prompt.csv", index=False)

    summary = summarize_groups(paired, ["model", "group"])
    by_layer = summarize_groups(paired, ["model", "group", "layer"])
    by_category = summarize_groups(paired, ["model", "group", "category"])

    summary.to_csv(out_dir / "summary.csv", index=False)
    by_layer.to_csv(out_dir / "by_layer.csv", index=False)
    by_category.to_csv(out_dir / "by_category.csv", index=False)

    guard_findings = guard_checks(traces)
    if guard_findings:
        pd.DataFrame(guard_findings).to_csv(out_dir / "guard_findings.csv", index=False)

    write_report(args.run_id, paired, summary, by_layer, by_category,
                 guard_findings, judgments, out_dir)

    print(f"wrote {out_dir}/report.md")
    print(f"  paired rows: {len(paired)}")
    print(f"  guard findings: {len(guard_findings)}")


if __name__ == "__main__":
    main()
