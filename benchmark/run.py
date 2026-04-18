"""Run the benchmark: for each (prompt × group × seed), call the API and save a trace.

Usage:
  python run.py --run-id smoke --groups B_zh_normal,D_moyan_jing --limit 5
  python run.py --run-id v0    --groups B_zh_normal,D_moyan_jing --samples 1
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from lib import (
    GROUPS,
    Analysis,
    Trace,
    Usage,
    analyze_response,
    call_claude,
    get_client,
    load_prompts,
    save_trace,
    trace_path,
    write_run_meta,
)


def run_one(
    *,
    client,
    run_id: str,
    model: str,
    prompt_entry: dict,
    group: str,
    seed: int,
    temperature: float,
    force: bool,
) -> None:
    gcfg = GROUPS[group]
    system_prompt = gcfg["system"]
    user_turns = prompt_entry.get("turns") or [prompt_entry["prompt"]]

    # Carry-forward conversation for multiturn; each API call is one trace.
    history: list[dict] = []
    for turn_idx, user_text in enumerate(user_turns):
        out_path = trace_path(run_id, prompt_entry["id"], group, seed, turn_idx)
        if out_path.exists() and not force:
            # Resume: load prior response to continue multiturn
            prior = json.loads(out_path.read_text(encoding="utf-8"))
            history.append({"role": "user", "content": user_text})
            history.append({"role": "assistant", "content": prior["response"]})
            continue

        history.append({"role": "user", "content": user_text})
        err = None
        text = ""
        usage = None
        latency = 0
        try:
            text, usage, latency = call_claude(
                client=client,
                model=model,
                system_prompt=system_prompt,
                turns=history,
                max_tokens=2048,
                temperature=temperature,
            )
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            print(f"  ! {prompt_entry['id']} {group} seed={seed} turn={turn_idx}: {err}", file=sys.stderr)

        analysis = analyze_response(text) if text else None
        trace = Trace(
            prompt_id=prompt_entry["id"],
            layer=prompt_entry["layer"],
            category=prompt_entry["category"],
            group=group,
            model=model,
            seed=seed,
            timestamp=time.time(),
            latency_ms=latency,
            system_prompt=system_prompt,
            turns=history.copy(),
            response=text,
            usage=usage or Usage(),
            analysis=analysis or Analysis(),
            error=err,
        )
        save_trace(run_id, trace, turn=turn_idx)
        history.append({"role": "assistant", "content": text})

        if usage:
            print(
                f"  {prompt_entry['id']:28} {group:18} seed={seed} t={turn_idx} "
                f"in={usage.input_tokens:>5} out={usage.output_tokens:>4} "
                f"cache_r={usage.cache_read_input_tokens:>5} "
                f"{latency/1000:.1f}s"
            )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True, help="identifier for this run (e.g. smoke, v1)")
    ap.add_argument("--models", default="claude-sonnet-4-6",
                    help="comma-separated model IDs")
    ap.add_argument("--groups", default=",".join(GROUPS.keys()),
                    help="comma-separated group IDs")
    ap.add_argument("--samples", type=int, default=3, help="N seeds per (prompt, group)")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--limit", type=int, default=0, help="only run first N prompts (0 = all)")
    ap.add_argument("--prompt-ids", default="", help="comma-separated prompt IDs; overrides --limit")
    ap.add_argument("--prompt-file", default="", help="path to file with one prompt ID per line (e.g. splits/train.txt)")
    ap.add_argument("--categories", default="", help="comma-separated categories to include")
    ap.add_argument("--force", action="store_true", help="overwrite existing traces")
    ap.add_argument("--notes", default="", help="free-form note for .meta.json")
    args = ap.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    groups = [g.strip() for g in args.groups.split(",") if g.strip()]
    for g in groups:
        if g not in GROUPS:
            raise SystemExit(f"unknown group: {g}. valid: {list(GROUPS)}")

    prompts = load_prompts()
    wanted: set[str] = set()
    if args.prompt_file:
        wanted.update(l.strip() for l in Path(args.prompt_file).read_text().splitlines() if l.strip())
    if args.prompt_ids:
        wanted.update(p.strip() for p in args.prompt_ids.split(","))
    if wanted:
        prompts = [p for p in prompts if p["id"] in wanted]
    if args.categories:
        cats = {c.strip() for c in args.categories.split(",")}
        prompts = [p for p in prompts if p["category"] in cats]
    if args.limit:
        prompts = prompts[: args.limit]

    total = len(prompts) * len(groups) * len(models) * args.samples
    print(
        f"run_id={args.run_id} · {len(prompts)} prompts × {len(groups)} groups × "
        f"{len(models)} models × {args.samples} seeds = {total} calls"
    )

    split = (Path(args.prompt_file).stem if args.prompt_file
             else "custom" if wanted or args.categories or args.limit
             else "all")
    write_run_meta(
        run_id=args.run_id, models=models, groups=groups,
        samples=args.samples, split=split, n_prompts=len(prompts),
        notes=args.notes,
    )

    client = get_client()

    for model in models:
        print(f"\n== model: {model} ==")
        for seed in range(args.samples):
            for prompt_entry in prompts:
                for group in groups:
                    run_one(
                        client=client,
                        run_id=args.run_id,
                        model=model,
                        prompt_entry=prompt_entry,
                        group=group,
                        seed=seed,
                        temperature=args.temperature,
                        force=args.force,
                    )

    print(f"\ndone. traces at: benchmark/traces/{args.run_id}/")


if __name__ == "__main__":
    main()
