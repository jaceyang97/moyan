# benchmark + autoskill

Self-improvement loop for `skills/moyan/SKILL.md`. Pattern from [karpathy/autoresearch](https://github.com/karpathy/autoresearch): the **Claude agent is the loop**. There is no Python orchestrator.

## Quick start (3 commands)

```bash
# 0. Setup (one time)
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...

# 1. Bake the baseline (one-shot, ~$3-5, ~10 min) — Sonnet 4.6 = bench respondent
python run.py --run-id sonnet-baseline --groups B_zh_normal,D_moyan_jing \
  --models claude-sonnet-4-6 --samples 1 --notes "Sonnet baseline for autoskill"

# 2. Start the loop — open Claude Code with Opus 4.7 selected, then:
#    > Read benchmark/program.md and run the autoskill loop for 25 iterations.
```

That's it. The agent reads `program.md`, then for each iter: forms a hypothesis, edits SKILL.md, commits, runs `evaluate.py`, parses `score:`, and `git reset --hard`s on failure. ~$0.85/iter; 25 iters ≈ $21.

## Models

| Role | Model |
|---|---|
| Proposer (the Claude Code session driving the loop) | `claude-opus-4-7` |
| Bench respondent (what we optimize for) | `claude-sonnet-4-6` |
| Judge (pairwise A/B completeness) | `claude-opus-4-7` |

Hard tasks (proposer, judge) get Opus; high-volume task (bench) gets Sonnet. Cross-family between respondent (Sonnet) and judge (Opus) decorrelates them.

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
score = delta_median  −  0.5 × max(0, 0.30 − completeness_full)  −  0.2 × guard_fails
```

- `delta_median` — paired output-token reduction vs B (Chinese-normal) baseline, median across prompts
- `completeness_full` — fraction of judge ratings = "full" (computed only with `--with-judge`)
- `guard_fails` — destructive prompts missing 警告; codegen prompts missing code blocks

Threshold 0.30 matches the Opus 4.7 judge's measured full-rate on v2.2 (see
`RESULTS_v2.md` Track C). Opus 4.6 was lenient (0.44 on the same pairs), so
the old 0.70 / 0.40 thresholds no longer apply.

## Algorithmic refinements layered into `program.md`

These were added on top of bare-bones autoresearch after observing v1 failure modes:

- **n=2 seeds, averaged** — single-seed noise was a real failure mode (~2-3pp jitter)
- **Holdout-as-promotion-gate** — `keep` requires both train ↑ AND holdout not-down >5pp. Catches v1-iter-4-style train-overfits.
- **3-hypothesis diversity** — agent drafts 3 candidates internally, picks one most distinct from recent discards

All three live in `program.md` as agent prose, not Python. Tunable in one place.

## Manual probe (one iteration, no loop)

`--baseline-run-id` is whichever run holds the precomputed `B_zh_normal`
traces you want to compare against (see `RUNS.md` for the inventory).

```bash
# Edit SKILL.md however you like, commit, then:
python evaluate.py --run-id manual_test --baseline-run-id sonnet-baseline
python evaluate.py --run-id manual_test --baseline-run-id sonnet-baseline --with-judge --skip-bench   # adds ~$0.10
python evaluate.py --run-id manual_test --baseline-run-id sonnet-baseline --split holdout --with-judge  # holdout check
```

## Trace schema (per API call, on disk)

```json
{
  "prompt_id": "L2-debug-01-useeffect-loop",
  "group": "D_moyan_jing",
  "model": "claude-sonnet-4-6",
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

Stored at `traces/{run_id}/{prompt_id}__{group}__seed{n}.json`. Judgments at `traces/{run_id}/_judgments/`. Run-level metadata (SKILL.md version, judge, split, created_at) at `traces/{run_id}/.meta.json` — see `RUNS.md`.

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
