# program.md — autoskill agent loop

> **Pattern:** [karpathy/autoresearch](https://github.com/karpathy/autoresearch). Agent **is** the loop. There is no Python orchestrator — you read this file, then iterate using your own tools (Read, Edit, Bash, git).

## Models in this loop

| Role | Model | Why |
|---|---|---|
| **Proposer** (you, the agent reading this file) | `claude-opus-4-6` | Hard task, low volume (~25 hypotheses/run). Start the Claude Code session in Opus 4.6. |
| **Bench respondent** (what we're optimizing for) | `claude-sonnet-4-6` | High volume (~78 calls/iter × 25 iters ≈ 2k calls). Want speed and cost. |
| **Judge** (pairwise A/B completeness) | `claude-opus-4-6` | Hard pairwise reasoning, low volume (~10 calls every 3 iters). Cross-family with respondent decorrelates. |

If you're running this loop and you're NOT Opus 4.6, stop and ask the user to restart you in Opus 4.6.

## What you're optimizing

`skills/moyan/SKILL.md` — the body (everything after the YAML frontmatter).
Goal: maximize the scalar `score` printed by `benchmark/evaluate.py`.

```
score = delta_median  −  0.5 × max(0, 0.70 − completeness_full)  −  0.2 × guard_fails
```

- `delta_median` — output-token reduction vs `B_zh_normal` baseline, median across train prompts (0–1; higher = more savings)
- `completeness_full` — fraction of judge ratings = "full" (only computed when `--with-judge`)
- `guard_fails` — destructive prompts missing 警告; codegen prompts missing code blocks

## Hard constraints (loop reverts on violation)

1. **Do NOT touch YAML frontmatter** of `SKILL.md`. Only edit body.
2. Preserve 3-level system: `简` / `精` / `文言文` must all appear.
3. Preserve sections: commit / review / Auto-Clarity (破例). Wording editable; section presence not.
4. Body size change must stay within `[0.7×, 1.3×]` of prior body.
5. Body must not contain literal `[HOLDOUT]` or the word `holdout`.

If a proposal violates these, `git reset --hard HEAD^` and try a different edit next iter.

## The loop (do this; don't ask)

For each iteration `N` (start from `cat benchmark/results.tsv | wc -l`):

```bash
PARENT=$(git rev-parse HEAD)
BEST=$(awk -F'\t' 'NR>1 && $4=="keep" {print $2}' benchmark/results.tsv | sort -g | tail -1)
BEST=${BEST:-0.0}
BEST_HOLDOUT=$(awk -F'\t' 'NR>1 && $4=="keep" && $3!="" && $3!="skip" {print $3}' benchmark/results.tsv | sort -g | tail -1)
BEST_HOLDOUT=${BEST_HOLDOUT:-0.0}

# The run_id that holds precomputed B_zh_normal traces for this responder.
# See benchmark/RUNS.md — pick one with the right responder + enough prompts.
BASELINE_RUN_ID="${BASELINE_RUN_ID:-sonnet-baseline}"
```

1. **Read state**
   - `cat skills/moyan/SKILL.md` — current artifact
   - `tail -20 benchmark/results.tsv` — recent iterations + decisions
   - `cat benchmark/traces/$BASELINE_RUN_ID/_judgments/*.json | head -200` — last judge feedback (if any)
   - Look at the worst-Δ prompts in baseline: find ids in `benchmark/traces/$BASELINE_RUN_ID` where `D_moyan_jing` saved least vs `B_zh_normal`. Read both responses. That's your weakness signal.

2. **Draft 3 candidate hypotheses internally; pick the most promising.** Diversity guard: skip any candidate that closely resembles the last 5 `discard`ed descriptions in `results.tsv`. Pick by: (a) targets a different weakness than the last 2 keeps, (b) is the smallest edit that could plausibly move the metric, (c) hasn't been tried. Output: ONE hypothesis, one edit. Single-edit attribution > big rewrites.

3. **Edit `skills/moyan/SKILL.md`** with the Edit tool. Touch nothing else.

4. **Validate locally** before committing — check the 5 hard constraints above. If you wrote a violating edit, undo and rewrite.

5. **Commit**:
   ```bash
   git add skills/moyan/SKILL.md
   git commit -m "autoskill iter N: <≤20-char hypothesis>"
   ```

6. **Evaluate on train (n=2 seeds, averaged)** — single-seed noise was a real failure mode in v1:
   ```bash
   N_PADDED=$(printf %03d $N)
   python benchmark/evaluate.py --run-id "iter_${N_PADDED}_a" --baseline-run-id "$BASELINE_RUN_ID" > /tmp/eval_a.log 2>&1
   python benchmark/evaluate.py --run-id "iter_${N_PADDED}_b" --baseline-run-id "$BASELINE_RUN_ID" > /tmp/eval_b.log 2>&1
   SCORE_A=$(grep '^score: ' /tmp/eval_a.log | tail -1 | awk '{print $2}')
   SCORE_B=$(grep '^score: ' /tmp/eval_b.log | tail -1 | awk '{print $2}')
   SCORE_TRAIN=$(awk "BEGIN { print ($SCORE_A + $SCORE_B) / 2 }")

   # Judge every 3 iters (~$0.10), only on the -a run for cost:
   if (( N % 3 == 0 )); then
     python benchmark/evaluate.py --run-id "iter_${N_PADDED}_a" --baseline-run-id "$BASELINE_RUN_ID" --with-judge --skip-bench >> /tmp/eval_a.log 2>&1
   fi
   ```

7. **Holdout gate** — only when train score looks like a keep (`SCORE_TRAIN > BEST + 0.02`):
   ```bash
   if awk "BEGIN { exit !($SCORE_TRAIN > $BEST + 0.02) }"; then
     python benchmark/evaluate.py --run-id "holdout_${N_PADDED}" --baseline-run-id "$BASELINE_RUN_ID" --split holdout --with-judge > /tmp/eval_h.log 2>&1
     SCORE_HOLDOUT=$(grep '^score: ' /tmp/eval_h.log | tail -1 | awk '{print $2}')
   else
     SCORE_HOLDOUT="skip"
   fi
   ```
   This catches v1-iter-4-style train-overfits where train Δ jumps but completeness collapses.

8. **Decide**:
   - **Train fails** (`SCORE_TRAIN ≤ BEST + 0.02`): `git reset --hard $PARENT`. Status = `discard`.
   - **Train passes, holdout drops > 5pp from `BEST_HOLDOUT`**: `git reset --hard $PARENT`. Status = `discard:holdout-overfit`.
   - **Both pass**: keep. The next iter's `BEST` and `BEST_HOLDOUT` re-read from `results.tsv`.
   - **Crash / `status: fail:*`**: `git reset --hard $PARENT`. Status = `crash`.

9. **Log** (TAB-separated, append one row):
   ```bash
   COMMIT=$(git rev-parse HEAD)
   printf "%s\t%s\t%s\t%s\t%s\n" "$COMMIT" "$SCORE_TRAIN" "$SCORE_HOLDOUT" "$STATUS" "$DESCRIPTION" \
     >> benchmark/results.tsv
   ```
   `results.tsv` columns: `commit  train_score  holdout_score  status  description`
   - `train_score` = n=2-seed average from step 6 (always present unless crash)
   - `holdout_score` = step 7 result, or empty when train didn't pass (gate not triggered)
   - `status` ∈ `{keep, discard, discard:holdout-overfit, crash}`

10. **Cost note** (per iter): bench respondent Sonnet 4.6 with n=2 seeds ~$0.45, holdout when triggered ~$0.10, Opus judge every 3 iters ~$0.10 amortized, proposer (you, Opus 4.6) ~$0.20. Budget ~$0.85/iter. 25 iters ≈ $21.

## Plateau handling

After 3 consecutive `discard` iters, your edits are too cautious or wrong. Choose ONE:
- **Radicalize**: propose a structural change (a new sub-rule, a reordering of priorities, a worked example replacement). Stay within the 5 hard constraints.
- **Inspect**: read the last 5 iter responses in `benchmark/traces/iter_*/`. Maybe the metric is saturating in some category — try a different category.

After 8 consecutive `discard`s, stop and write a one-paragraph summary in `benchmark/results.tsv` as a comment line (`# saturated at score=X`). Don't loop forever.

## Hypothesis library (proven patterns; fine to reuse with variation)

- Expand the **去：填词** blacklist (look at responses, find a recurring connector word)
- Add a **比较类** rule: "X vs Y" → diff table first
- Add a **枚举原因** rule: cause-listing → `[cause] — [verify]` short table
- Tighten a wording (e.g. swap a 4-char phrase for 2-char)
- Add an **Auto-Clarity** exception when judge flags over-compression in a specific category

## Anti-patterns (avoid)

- Don't add new top-level sections (`##`)
- Don't reorder major sections
- Don't remove existing rules unless `results.tsv` shows the rule actively hurts
- Don't try to "identify the test distribution" — you can't see holdout, and gaming train won't survive holdout check

## Where to look for ideas (reference only — not loaded as code)

- `karpathy/autoresearch` `program.md` — the original loop pattern; nothing here Claude-specific
- `anthropics/skills/skills/skill-creator` — official skill design rubric; useful when stuck on `description` quality (but frontmatter is locked here)

## Stop conditions

- 25 iterations done (default cap)
- 8 consecutive discards (saturated)
- Holdout score regresses by >5pp from prior best holdout (overfitting confirmed) — revert to last best commit and stop
- Manual: user kills the session

That's it. No orchestrator, no proposal-format JSON, no harness. Just you, the artifact, the metric, and git.
