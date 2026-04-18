# moyan benchmark + autoskill

Two layered jobs:

1. **Benchmark** — measure how much `moyan` saves vs Chinese-normal baseline, on 52 paired prompts. Run once to establish numbers (`v0` baseline).
2. **Autoskill loop** — autonomously iterate on `skills/moyan/SKILL.md` to push the score higher. Pattern from [karpathy/autoresearch](https://github.com/karpathy/autoresearch): the **agent is the loop**. No Python orchestrator.

## File map (autoresearch shape)

| File | Role | autoresearch analog |
|---|---|---|
| `program.md` | Agent loop instructions | `program.md` |
| `evaluate.py` | Read-only scalar metric (prints `score: …`) | `prepare.py` (`evaluate_bpb`) |
| `results.tsv` | 5-col log: `commit  delta_median  completeness  status  description` | `results.tsv` |
| `skills/moyan/SKILL.md` | Artifact under optimization | `train.py` |
| `run.py` / `judge.py` / `lib.py` | Bench infra (called by `evaluate.py`) | trainer infra |
| `prompts.jsonl`, `splits/` | Eval set + train/holdout split | data |

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

## 1. Establish baseline (one-shot, ~$3-5)

The autoskill loop needs a precomputed `B_zh_normal` baseline to compare against on every iteration. Bake it once.

```bash
# Full 52-prompt baseline — both groups so we have D_moyan_jing starting point too
python run.py --run-id v0 \
  --groups B_zh_normal,D_moyan_jing \
  --models claude-sonnet-4-5 \
  --samples 1
```

Traces land in `traces/v0/`. The autoskill loop reads `B_zh_normal` traces from this dir on every score computation.

## 2. Sanity-check `evaluate.py`

```bash
python evaluate.py --run-id v0 --baseline v0 --skip-bench
# Expected output:
#   score: 0.XX
#   delta_median: 0.XX
#   ...
#   status: ok
```

## 3. Run the autoskill loop

There is **no orchestrator script**. Open a Claude Code session with this repo as cwd and feed the agent `benchmark/program.md`:

```bash
# In Claude Code:
> Read benchmark/program.md and run the autoskill loop for 25 iterations.
```

The agent does everything itself: reads state, edits `SKILL.md`, commits, runs `evaluate.py`, parses score, decides keep/revert via `git reset --hard`, appends a row to `results.tsv`. See `program.md` for the full spec.

To manually probe one iteration:

```bash
# Edit SKILL.md however you like, commit, then:
python evaluate.py --run-id manual_test --baseline v0
# (or with judge — adds ~$0.10:)
python evaluate.py --run-id manual_test --baseline v0 --with-judge
```

## 4. Holdout check

The loop runs on `splits/train.txt` (39 prompts). Periodic holdout eval (`splits/holdout.txt`, 13 prompts) catches train-overfit:

```bash
python evaluate.py --run-id holdout_check --baseline v0 --split holdout --with-judge
```

If holdout `delta_median` lags train by >10pp, the loop is overfitting → revert.

## Score formula

```
score = delta_median  −  0.5 × max(0, 0.70 − completeness_full)  −  0.2 × guard_fails
```

- `delta_median`: paired output-token reduction vs B baseline (median across train prompts)
- `completeness_full`: fraction of judge ratings = "full" (only when `--with-judge`)
- `guard_fails`: destructive prompts missing 警告; codegen prompts missing code blocks

Threshold 0.70 (not 0.95) — pair-compare judge over-flags legitimate compression as "missing"; 0.70 calibrated against ~50 hand-checked judgments. See top-level `RESULTS.md`.

## What got removed

The first iteration had a Python orchestrator (`autoskill.py`, ~580 lines) plus a proposer system prompt (`AUTOSKILL.md`), plus rich aggregation (`analyze.py`, `attribute.py`). All gone — autoresearch's 4-file shape doesn't include them. The agent's tool freedom in `program.md` covers everything those scripts used to do, and any reporting can be regenerated from `traces/` on demand.

Recover any of them from git:

```bash
git show d63d923:benchmark/autoskill.py > /tmp/autoskill_v1.py
```

## Trace schema (unchanged)

```json
{
  "prompt_id": "L2-debug-01-useeffect-loop",
  "group": "D_moyan_jing",
  "model": "claude-sonnet-4-5",
  "seed": 0,
  "usage": { "input_tokens": 1823, "output_tokens": 412, ... },
  "analysis": {
    "char_count": 380,
    "code_block_chars": 120,
    "filler_hits": { "客套": 0, "填词": 1, ... },
    "contains_warning": false,
    ...
  },
  "response": "...",
  "system_prompt": "..."
}
```

## Known limitations

- SKILL.md injection costs ~2k input tokens; only really saves with prompt caching (long sessions)
- LLM-as-judge has systematic verbosity bias — `completeness_full=0.70` is calibrated for that
- `temperature=0` ≠ deterministic; `--samples 1` accepts that single-seed noise
- Multi-turn coverage is thin (3 prompts) — long-conversation effects are under-measured
- Holdout n=13; CIs are wide
