# program.md — autoskill agent loop

> **Pattern:** [karpathy/autoresearch](https://github.com/karpathy/autoresearch). Agent **is** the loop. There is no Python orchestrator — you read this file, then iterate using your own tools (Read, Edit, Bash, git).

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
```

1. **Read state**
   - `cat skills/moyan/SKILL.md` — current artifact
   - `tail -20 benchmark/results.tsv` — recent iterations + decisions
   - `cat benchmark/traces/v0/_judgments/*.json | head -200` — last judge feedback (if any)
   - Look at the worst-Δ prompts in baseline: find ids in `benchmark/traces/v0` where `D_moyan_jing` saved least vs `B_zh_normal`. Read both responses. That's your weakness signal.

2. **Form ONE small hypothesis** (one rule added, one phrase tightened, one example swapped). Single-edit attribution > big rewrites. Look at `results.tsv` `description` column — don't repeat anything that was `discard`ed unless you have new evidence.

3. **Edit `skills/moyan/SKILL.md`** with the Edit tool. Touch nothing else.

4. **Validate locally** before committing — check the 5 hard constraints above. If you wrote a violating edit, undo and rewrite.

5. **Commit**:
   ```bash
   git add skills/moyan/SKILL.md
   git commit -m "autoskill iter N: <≤20-char hypothesis>"
   ```

6. **Evaluate**:
   ```bash
   RUN_ID="iter_$(printf %03d N)"
   python benchmark/evaluate.py --run-id "$RUN_ID" --baseline v0 > /tmp/eval.log 2>&1
   # Run judge every 3 iters (cheap signal vs $0.10 cost):
   if (( N % 3 == 0 )); then
     python benchmark/evaluate.py --run-id "$RUN_ID" --baseline v0 --with-judge --skip-bench >> /tmp/eval.log 2>&1
   fi
   tail -20 /tmp/eval.log
   ```

7. **Parse**: `SCORE=$(grep '^score: ' /tmp/eval.log | tail -1 | awk '{print $2}')`

8. **Decide** (greedy, +0.02 margin):
   - If `SCORE > BEST + 0.02`: keep. New BEST = SCORE.
   - Else: `git reset --hard $PARENT`. Status = `discard`.
   - If `evaluate.py` printed `status: fail:*` or crashed: `git reset --hard $PARENT`. Status = `crash`.

9. **Log** (TAB-separated, append one row):
   ```bash
   COMMIT=$(git rev-parse HEAD)
   printf "%s\t%s\t%s\t%s\t%s\n" "$COMMIT" "$DELTA" "$COMPLETENESS" "$STATUS" "$DESCRIPTION" \
     >> benchmark/results.tsv
   ```
   `results.tsv` columns: `commit  delta_median  completeness  status  description`
   `status` ∈ `{keep, discard, crash}`. `completeness` may be empty when judge skipped.

10. **Holdout check** (every 5 keeps): run `python benchmark/evaluate.py --run-id "holdout_$N" --baseline v0 --split holdout --with-judge`. If holdout `delta_median` lags train by more than 10pp, you're overfitting — next iter, propose a more general rule (something that helps multiple prompt categories, not one).

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
