"""Phrase-level savings attribution.

For each paired (baseline B → moyan D), diff the text at sentence level,
categorize removed phrases by the FILLER_PATTERNS taxonomy, and aggregate.
Answers: "which SKILL.md rules actually save tokens in practice?"

Also surfaces:
  - Top 10 "best compressions" (large delta + full completeness)
  - Top 10 "over-compressions" (judge flagged missing points)
  - Top 10 "under-compressions" (small delta despite compressible prompt)

Output: results/{run_id}/attribution.md
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from lib import BASELINE_GROUP, BENCH_ROOT, FILLER_PATTERNS, MOYAN_GROUPS


def split_sentences(text: str) -> list[str]:
    """Split on CJK + Latin sentence boundaries; keep code blocks intact as one unit."""
    # Protect code fences
    parts = re.split(r"(```.*?```)", text, flags=re.DOTALL)
    out = []
    for part in parts:
        if part.startswith("```"):
            out.append(part)
        else:
            for sent in re.split(r"(?<=[。！？.!?\n])", part):
                sent = sent.strip()
                if sent:
                    out.append(sent)
    return out


def categorize_phrase(phrase: str) -> str | None:
    for cat, needles in FILLER_PATTERNS.items():
        if any(n in phrase for n in needles):
            return cat
    return None


def diff_responses(baseline: str, moyan: str) -> dict:
    """Return counts of phrase categories removed from baseline to moyan."""
    b_sents = split_sentences(baseline)
    m_sents = split_sentences(moyan)
    sm = difflib.SequenceMatcher(a=b_sents, b=m_sents, autojunk=False)
    removed = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("delete", "replace"):
            removed.extend(b_sents[i1:i2])

    cat_counts = Counter()
    uncategorized = []
    for phrase in removed:
        if phrase.startswith("```"):
            continue  # never count code blocks as savings
        cat = categorize_phrase(phrase)
        if cat:
            cat_counts[cat] += 1
        else:
            uncategorized.append(phrase)
    return {
        "categorized": dict(cat_counts),
        "uncategorized_sample": uncategorized[:5],
        "removed_chars": sum(len(p) for p in removed if not p.startswith("```")),
    }


def load_final_trace(run_id: str, prompt_id: str, group: str, seed: int) -> dict | None:
    d = BENCH_ROOT / "traces" / run_id
    files = sorted(d.glob(f"{prompt_id}__{group}__seed{seed}*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))


def load_judgments(run_id: str) -> dict:
    out = {}
    d = BENCH_ROOT / "traces" / run_id / "_judgments"
    if not d.exists():
        return out
    for p in d.glob("*.json"):
        j = json.loads(p.read_text(encoding="utf-8"))
        if j.get("error"):
            continue
        key = (j["prompt_id"], j["model"], j["moyan_group"], j["seed"])
        out[key] = j
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    args = ap.parse_args()

    out_dir = BENCH_ROOT / "results" / args.run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    per_prompt_csv = out_dir / "per_prompt.csv"
    if not per_prompt_csv.exists():
        raise SystemExit(f"run analyze.py first: {per_prompt_csv} missing")
    paired = pd.read_csv(per_prompt_csv)

    judgments = load_judgments(args.run_id)

    # Aggregate attribution across all paired (prompt, moyan_group, model)
    # using seed=0 traces for diff (stable choice).
    category_totals = Counter()
    per_prompt_attrib = []
    for _, row in paired.iterrows():
        base = load_final_trace(args.run_id, row["prompt_id"], BASELINE_GROUP, 0)
        moy = load_final_trace(args.run_id, row["prompt_id"], row["group"], 0)
        if not base or not moy:
            continue
        if base["model"] != row["model"] or moy["model"] != row["model"]:
            continue
        diff = diff_responses(base["response"], moy["response"])
        for cat, c in diff["categorized"].items():
            category_totals[cat] += c
        per_prompt_attrib.append({
            "prompt_id": row["prompt_id"],
            "model": row["model"],
            "group": row["group"],
            "delta_out": row["delta_out"],
            "removed_chars": diff["removed_chars"],
            **{f"cat_{c}": diff["categorized"].get(c, 0) for c in FILLER_PATTERNS},
        })

    attrib_df = pd.DataFrame(per_prompt_attrib)
    attrib_df.to_csv(out_dir / "attribution.csv", index=False)

    # Rankings
    best = attrib_df.nlargest(10, "delta_out")
    worst = attrib_df.nsmallest(10, "delta_out")

    # Judge-flagged over-compressions
    over_comp = []
    for (pid, model, mg, seed), j in judgments.items():
        if j.get("completeness") in ("partial", "missing") and j.get("missing_points"):
            over_comp.append({
                "prompt_id": pid, "model": model, "group": mg, "seed": seed,
                "completeness": j.get("completeness"),
                "missing_points": j.get("missing_points"),
            })
    over_comp = sorted(over_comp, key=lambda d: len(d["missing_points"]), reverse=True)[:10]

    lines = []
    lines.append(f"# Attribution — `{args.run_id}`\n")

    lines.append("## Phrase categories removed (aggregate)\n")
    if category_totals:
        tot = sum(category_totals.values())
        cat_df = pd.DataFrame([
            {"category": c, "removals": n, "share": n / tot}
            for c, n in category_totals.most_common()
        ])
        lines.append(cat_df.to_markdown(index=False, floatfmt=".3f"))
    else:
        lines.append("_No categorized removals detected._")
    lines.append("")

    lines.append("## Top 10 best compressions (highest Δ output tokens)\n")
    lines.append(best[["prompt_id", "model", "group", "delta_out", "removed_chars"]]
                 .to_markdown(index=False, floatfmt=".3f"))
    lines.append("")

    lines.append("## Top 10 under-compressions (lowest Δ — moyan barely saved anything)\n")
    lines.append(worst[["prompt_id", "model", "group", "delta_out", "removed_chars"]]
                 .to_markdown(index=False, floatfmt=".3f"))
    lines.append("")

    lines.append("## Top 10 over-compressions (judge flagged missing info)\n")
    if over_comp:
        for oc in over_comp:
            lines.append(f"- **{oc['prompt_id']}** ({oc['group']}, {oc['model']}, seed={oc['seed']}, {oc['completeness']})")
            for m in oc["missing_points"][:3]:
                lines.append(f"  - missing: {m}")
    else:
        lines.append("_No over-compressions detected (or no judgments run)._")
    lines.append("")

    # Actionable suggestions for SKILL.md
    lines.append("## Regression candidates for SKILL.md\n")
    if worst["delta_out"].min() < 0.1:
        lines.append("- **Under-compression:** prompts above have Δ < 10%. Check if they fall into a category")
        lines.append("  (e.g. debug, review) where SKILL.md's rules don't bite. Consider adding targeted guidance.")
    if over_comp:
        lines.append(f"- **Over-compression:** {len(over_comp)} judged cases lost information. Review")
        lines.append("  whether the Auto-Clarity exceptions need to be broadened (e.g. multi-step procedures).")
    if not category_totals:
        lines.append("- **No filler hits:** FILLER_PATTERNS lists in `lib.py` may not match real removals.")
        lines.append("  Expand patterns based on manual inspection of baseline responses.")
    lines.append("")

    (out_dir / "attribution.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out_dir}/attribution.md  ({len(attrib_df)} pairs attributed)")


if __name__ == "__main__":
    main()
