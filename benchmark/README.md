# benchmark + autoskill

Self-improvement loop for `skills/moyan/SKILL.md`. Pattern from [karpathy/autoresearch](https://github.com/karpathy/autoresearch): the **Claude agent is the loop**. There is no Python orchestrator.

## Quick start (3 commands)

```bash
# 0. Setup (one time)
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

# 1. Bake the baseline (one-shot, ~$3-5, ~10 min)
python run.py --run-id v0 --groups B_zh_normal,D_moyan_jing --models claude-sonnet-4-5 --samples 1

# 2. Start the loop — open Claude Code in the repo root and say:
#    > Read benchmark/program.md and run the autoskill loop for 25 iterations.
```

That's it. The agent reads `program.md`, then for each iter: forms a hypothesis, edits SKILL.md, commits, runs `evaluate.py`, parses `score:`, and `git reset --hard`s on failure. ~$0.65/iter; 25 iters ≈ $16.

## The 4 files that matter (autoresearch shape)

| File | Role | autoresearch analog |
|---|---|---|
| **`program.md`** | Agent loop instructions — read this first | `program.md` |
| **`evaluate.py`** | Read-only metric. Prints `score: 0.XXX` | `prepare.py` (`evaluate_bpb`) |
| **`results.tsv`** | 5-col log: `commit  train_score  holdout_score  status  description` | `results.tsv` |
| **`../skills/moyan/SKILL.md`** | The artifact under optimization | `train.py` |

Everything else (`run.py`, `judge.py`, `lib.py`, `prompts.jsonl`, `splits/`) is infra called by `evaluate.py`.

## Score formula

```
score = delta_median  −  0.5 × max(0, 0.70 − completeness_full)  −  0.2 × guard_fails
```

- `delta_median` — paired output-token reduction vs B (Chinese-normal) baseline, median across prompts
- `completeness_full` — fraction of judge ratings = "full" (computed only with `--with-judge`)
- `guard_fails` — destructive prompts missing 警告; codegen prompts missing code blocks

Threshold 0.70 (not 0.95): pair-compare judge over-flags legitimate compression as "missing"; calibrated against hand-checked judgments. See `RESULTS.md` (v1 history).

## Algorithmic refinements layered into `program.md`

These were added on top of bare-bones autoresearch after observing v1 failure modes:

- **n=2 seeds, averaged** — single-seed noise was a real failure mode (~2-3pp jitter)
- **Holdout-as-promotion-gate** — `keep` requires both train ↑ AND holdout not-down >5pp. Catches v1-iter-4-style train-overfits.
- **3-hypothesis diversity** — agent drafts 3 candidates internally, picks one most distinct from recent discards

All three live in `program.md` as agent prose, not Python. Tunable in one place.

## Manual probe (one iteration, no loop)

```bash
# Edit SKILL.md however you like, commit, then:
python evaluate.py --run-id manual_test --baseline v0
python evaluate.py --run-id manual_test --baseline v0 --with-judge --skip-bench   # adds ~$0.10
python evaluate.py --run-id manual_test --baseline v0 --split holdout --with-judge  # holdout check
```

## Trace schema (per API call, on disk)

```json
{
  "prompt_id": "L2-debug-01-useeffect-loop",
  "group": "D_moyan_jing",
  "model": "claude-sonnet-4-5",
  "seed": 0,
  "usage": { "input_tokens": 1823, "output_tokens": 412, "...": "..." },
  "analysis": {
    "has_code_block": true,
    "filler_hits": { "客套": 0, "填词": 1, "铺垫": 0, "犹豫": 2, "自指": 0 },
    "contains_warning": false
  },
  "response": "...",
  "system_prompt": "..."
}
```

Stored at `traces/{run_id}/{prompt_id}__{group}__seed{n}.json`. Judgments at `traces/{run_id}/_judgments/`.

## What this replaces (v1 → v2)

v1 used a Python orchestrator (`autoskill.py`, ~580 lines) + proposer prompt (`AUTOSKILL.md`) + rich aggregation (`analyze.py`, `attribute.py`). All gone — autoresearch's 4-file shape doesn't include them. Recover from git if needed:

```bash
git show d63d923:benchmark/autoskill.py > /tmp/autoskill_v1.py
git show d63d923:benchmark/analyze.py   > /tmp/analyze_v1.py
```

## Known limitations

- SKILL.md injection costs ~2k input tokens — only really nets out with prompt caching (long sessions)
- LLM-as-judge has systematic verbosity bias; `completeness_full=0.70` threshold is the workaround
- `temperature=0` ≠ deterministic; n=2 seeds smooths but doesn't eliminate noise
- Multi-turn coverage thin (3 prompts) — long-conversation effects under-measured
- Holdout n=13; CIs are wide
