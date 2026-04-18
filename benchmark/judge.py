"""Blind pairwise quality judge.

For each (prompt, moyan_group, seed), find the matched baseline_B trace,
anonymize as Response A/B with randomized order, ask a separate Claude
whether the moyan response preserves every technical point.

Saves one judgment JSON per pair into traces/{run_id}/_judgments/.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from pathlib import Path

from lib import BASELINE_GROUP, MOYAN_GROUPS, BENCH_ROOT, get_client, load_prompts

JUDGE_SYSTEM = """You are an impartial technical judge. You will be shown a user question and two candidate answers (Response A and Response B). Evaluate whether Response B preserves all the technical substance of Response A.

Focus strictly on technical content — not style, length, or language. Terseness is NOT a defect. Missing a fact, misstating one, or adding a wrong claim IS a defect.

Return STRICT JSON with these keys:
{
  "completeness": "full" | "partial" | "missing",   // does B cover every technical point in A?
  "missing_points": [string, ...],                   // specific facts in A not in B (empty if full)
  "added_errors": [string, ...],                     // claims in B that are wrong or absent from A
  "actionability": 1 | 2 | 3 | 4 | 5,                 // can a developer act on B alone? 5=yes
  "rationale": string                                 // 1-3 sentences
}

Output ONLY the JSON object — no prose, no code fences."""


JUDGE_USER_TEMPLATE = """# User question
{question}

---

# Response A
{resp_a}

---

# Response B
{resp_b}

---

Evaluate whether Response B preserves all technical substance of Response A.
Return the JSON described in the system prompt."""


def load_response(run_id: str, prompt_id: str, group: str, seed: int) -> dict | None:
    """Load the final-turn trace for a multi-turn or single-turn run."""
    d = BENCH_ROOT / "traces" / run_id
    # Find highest turn for this (prompt, group, seed). Single-turn has no _tN suffix.
    files = sorted(d.glob(f"{prompt_id}__{group}__seed{seed}*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a judge response, tolerant of stray prose."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\n", "", text)
        text = re.sub(r"\n```$", "", text)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise ValueError(f"no JSON found in judge output: {text[:200]}")
    return json.loads(m.group(0))


def judge_pair(
    *,
    client,
    judge_model: str,
    question: str,
    baseline_resp: str,
    moyan_resp: str,
    rng: random.Random,
) -> dict:
    """Blind A/B judgment with randomized order. Result normalized so that
    'B' always refers to the moyan response."""
    # Randomize which position is the moyan response.
    moyan_is_b = rng.random() < 0.5
    if moyan_is_b:
        resp_a, resp_b = baseline_resp, moyan_resp
    else:
        resp_a, resp_b = moyan_resp, baseline_resp

    user = JUDGE_USER_TEMPLATE.format(question=question, resp_a=resp_a, resp_b=resp_b)
    t0 = time.time()
    resp = client.messages.create(
        model=judge_model,
        system=JUDGE_SYSTEM,
        messages=[{"role": "user", "content": user}],
        max_tokens=1024,
        temperature=0.0,
    )
    latency = int((time.time() - t0) * 1000)
    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")

    try:
        raw = extract_json(text)
    except Exception as e:  # noqa: BLE001
        return {"error": f"parse: {e}", "raw_text": text, "latency_ms": latency}

    # If moyan was A, flip the interpretation so the output always describes
    # B-as-moyan. The judge's "missing_points" means "things in A but not in B"
    # which, when moyan=A, means "things in moyan but not in baseline" — that's
    # not what we want. Invert.
    if not moyan_is_b:
        raw = {
            **raw,
            "missing_points": raw.get("added_errors", []),
            "added_errors": raw.get("missing_points", []),
            "_inverted": True,
        }
    raw["_moyan_position"] = "B" if moyan_is_b else "A"
    raw["_judge_latency_ms"] = latency
    raw["_judge_usage"] = {
        "input_tokens": getattr(resp.usage, "input_tokens", 0),
        "output_tokens": getattr(resp.usage, "output_tokens", 0),
    }
    return raw


def judgment_path(run_id: str, prompt_id: str, model: str, moyan_group: str, seed: int) -> Path:
    d = BENCH_ROOT / "traces" / run_id / "_judgments"
    d.mkdir(parents=True, exist_ok=True)
    safe_model = model.replace("/", "_")
    return d / f"{prompt_id}__{safe_model}__{moyan_group}__seed{seed}.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--judge-model", default="claude-sonnet-4-5",
                    help="model to use for judging (Sonnet recommended — cheaper)")
    ap.add_argument("--models", default="",
                    help="only judge traces from these models (default: all found)")
    ap.add_argument("--moyan-groups", default=",".join(MOYAN_GROUPS))
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--rng-seed", type=int, default=42, help="for reproducible A/B order")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    prompts = {p["id"]: p for p in load_prompts()}
    moyan_groups = [g.strip() for g in args.moyan_groups.split(",")]

    # Discover model IDs present in traces if not given.
    trace_dir = BENCH_ROOT / "traces" / args.run_id
    if not trace_dir.exists():
        raise SystemExit(f"no traces at {trace_dir}")
    if args.models:
        models = [m.strip() for m in args.models.split(",")]
    else:
        models = sorted({
            json.loads(p.read_text(encoding="utf-8"))["model"]
            for p in trace_dir.glob("*.json")
        })

    client = get_client()
    rng = random.Random(args.rng_seed)
    n_done = n_skipped = n_err = 0

    for model in models:
        print(f"\n== judging model: {model} ==")
        for prompt_id, prompt in prompts.items():
            for mg in moyan_groups:
                for seed in range(args.seeds):
                    outp = judgment_path(args.run_id, prompt_id, model, mg, seed)
                    if outp.exists() and not args.force:
                        n_skipped += 1
                        continue
                    baseline = load_response(args.run_id, prompt_id, BASELINE_GROUP, seed)
                    moyan = load_response(args.run_id, prompt_id, mg, seed)
                    if not baseline or not moyan:
                        continue
                    if baseline.get("model") != model or moyan.get("model") != model:
                        continue
                    if baseline.get("error") or moyan.get("error"):
                        continue

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
                    judgment["model"] = model
                    judgment["moyan_group"] = mg
                    judgment["seed"] = seed
                    outp.write_text(json.dumps(judgment, ensure_ascii=False, indent=2), encoding="utf-8")
                    n_done += 1
                    status = judgment.get("completeness", "ERR")
                    print(f"  {prompt_id:28} {mg:18} seed={seed} → {status}")

    print(f"\ndone. judged={n_done} skipped={n_skipped} errors={n_err}")


if __name__ == "__main__":
    main()
