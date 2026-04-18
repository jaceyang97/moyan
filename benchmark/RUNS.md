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

- `_judgments/` — primary judge verdicts (Opus 4.7 as of 2026-04)
- `_judgments_kappa/{judge_model}/` — alternate-judge verdicts for κ
- `_bench.log` — autoskill bench subprocess log

## Commands

```bash
# Run a new benchmark (writes .meta.json automatically)
python run.py --run-id sonnet-skill2.2 \
  --models claude-sonnet-4-6 \
  --groups B_zh_normal,C_moyan_jian,D_moyan_jing,E_moyan_wenyan \
  --samples 1 --prompt-file splits/holdout.txt \
  --notes "v2.2 holdout validation"

# Summary stats
python run_stats.py --run-id sonnet-skill2.2

# Judge + κ
python judge.py --run-id sonnet-skill2.2 --judge-model claude-opus-4-7
python kappa.py judge2 --run-id sonnet-skill2.2 --judge-model claude-sonnet-4-6
python kappa.py score  --run-id sonnet-skill2.2 \
  --judge-a claude-opus-4-7 --judge-b claude-sonnet-4-6
```
