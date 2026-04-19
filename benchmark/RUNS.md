# Runs index

Every benchmark run lives at `traces/{run_id}/` with a `.meta.json` stamp.
This index mirrors those stamps so humans and agents can scan runs without
opening 71 JSON files.

## Current runs

| run_id | responder | SKILL.md | split | judge | notes |
|---|---|---|---|---|---|
| `v2-haiku` | Haiku 4.5 | v2.0 | all (71) | Opus 4.6 | Track B — initial Haiku run |
| `v2-haiku-v21` | Haiku 4.5 | v2.1 | all (71) | Opus 4.6 | Track C iter — v2.1 trim |
| `v2-haiku-v22` | Haiku 4.5 | v2.2 | all (71) | Opus 4.6 | Track C — level collapse persists on Haiku |
| `v2-sonnet-v22` | Sonnet 4.6 | v2.2 | holdout | Opus 4.6 | Track C — current best (74.5% 文言文 Δ_median) |
| `sonnet-baseline` | Sonnet 4.6 | n/a | all (71) | — | `B_zh_normal` baseline for autoskill iters |
| `probe_v22_a` / `_b` | Sonnet 4.6 | v2.2 | train | Opus 4.7 | autoskill probe — establishes BEST=0.6718 |
| `iter_004_a` / `_b` | Sonnet 4.6 | v2.2+填词 | train | — | autoskill iter 4 — discarded (−0.09pp noise) |
| `iter_005_a` / `_b` | Sonnet 4.6 | v2.2+版式 | train | Opus 4.7 (a) | autoskill iter 5 — **KEEP**, train 0.6948 |
| `holdout_005` | Sonnet 4.6 | v2.2+版式 | holdout | Opus 4.7 | iter 5 holdout — 0.7237 (+5.2pp) |
| `skill23-holdout-allgroups` | Sonnet 4.6 | v2.2+版式 | holdout (4 groups) | — | 横向验证：简 73.0% / 精 73.9% / 文言文 74.5% — 级别排序保持单调 |
| `iter_006_a` / `_b` | Sonnet 4.6 | v2.2+版式−SQL 例 | train | Opus 4.7 | autoskill iter 6 — discarded (holdout-overfit) |
| `holdout_006` | Sonnet 4.6 | v2.2+版式−SQL 例 | holdout | Opus 4.7 | iter 6 holdout — 0.6440 (−8pp)，SKILL.md 已回滚 |

`.meta.json` holds the authoritative version of the above plus SKILL.md commit,
byte length, sample count, and created_at. Always read `.meta.json` before
comparing two runs — visual run_ids can be ambiguous (`v2-haiku` was SKILL v2.0,
not v2.x).

## Naming convention going forward

```
{responder}-skill{version}[-{note}]
```

Examples: `sonnet-skill2.2`, `sonnet-skill2.2-holdout`, `haiku-skill2.3`.
Drops the ambiguous `v2` prefix (which conflated era with SKILL version).
Legacy `v2-*` run_ids are frozen — do not invent new ones in that scheme.

## Secondary directories inside a run

- `_judgments/` — judge verdicts (Opus 4.7 as of 2026-04)
- `_bench.log` — autoskill bench subprocess log

## Commands

```bash
# Run a new benchmark (writes .meta.json automatically)
python run.py --run-id sonnet-skill2.3 \
  --models claude-sonnet-4-6 \
  --groups B_zh_normal,C_moyan_jian,D_moyan_jing,E_moyan_wenyan \
  --samples 1 --prompt-file splits/holdout.txt \
  --notes "holdout validation"

# Score one run (loop-internal metric)
python evaluate.py --run-id sonnet-skill2.3 --baseline-run-id sonnet-baseline

# With judge (full autoskill iter)
python judge.py --run-id sonnet-skill2.3 --judge-model claude-opus-4-7
```
