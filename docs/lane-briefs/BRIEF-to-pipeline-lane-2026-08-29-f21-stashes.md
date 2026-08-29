# Brief: your F21 WIP is in two stashes — captain lane, 2026-08-29

**Status: APPROVED by the operator 2026-08-29 and delivered — committed to
master, where the pipeline lane works.**

To: pipeline lane (the F21 runner-refactor work in the main worktree)
From: captain lane
Re: what moved under you while the puzzle solver merged, and where your
uncommitted work went

## What happened

The operator ordered the puzzle-solver merge and redeploy this afternoon. The
merge had to write `scripts/run_vertex_pipeline.py` — the file carrying your
uncommitted F21 restructure — so I stashed your WIP rather than let the merge
clobber it or leave conflict markers in your working copy. Both stashes are
labeled and intact:

    stash@{0}: On master: live-lane F21 WIP on test_pipeline_stages — pairs with the run_vertex_pipeline stash
    stash@{1}: On master: live-lane F21 WIP on run_vertex_pipeline — stashed by captain for puzzle-solver merge 2026-08-29

**They are a matched set — apply them together, script first.** Your modified
test imports 12 symbols from `scripts.run_vertex_pipeline`, and 10 of them
(`AppraisalStageResult`, `DecisionStageResult`, `IntakeStageResult`,
`run_appraisal_stage`, `run_decision_stage`, `run_intake_stage`, the three
artifact writers, `exact_requested_rows`) exist only in your stashed script.
Applying the test stash alone against HEAD reproduces a collection
`ImportError` (verified, exit 2) — which is also why I had to stash the test
once the script was stashed.

Nothing else of yours was touched: `.gitignore`, `Makefile`, `docs/TODO.md`,
`requirements-dev.txt`, `docs/evidence/`, `ruff.toml`, and
`tests/test_todo_inventory.py` are still sitting in the working tree exactly
as you left them.

## What changed underneath your stash

Master is now `34588cb`, deployed as revision `blue-toad-fleet-00030-ggk`,
and three things in it affect your re-apply:

1. **The puzzle solver landed** (merge `7346757`, grok's branch). The
   grouping region of `run_vertex_pipeline.py` you refactored against no
   longer exists in the shape you saw: `group_into_lots` + `merge_reshoots`
   became `puzzle_loop` + `as_lot_groups` with walk-edge proposals unioned
   with the F10-approved reshoot edges, and `select_appraisal_candidates` no
   longer drops on `worth_appraising`. Expect real conflicts when you apply
   `stash@{1}`; resolve toward keeping the puzzle wiring — the approved
   sequencing (operator-ruled in the grok rebase brief) is that **F21
   rebases onto the puzzle solver**, not the reverse.
2. **Your own `b07477b` is pushed.** It was local-only when the merge was
   ordered; pushing merged master necessarily carried it to origin. It is
   live: `/health` on `00030-ggk` reports `git_commit` equal to the GitHub
   tip — your parity feature working in production on its first deploy.
3. **The budget cap is $600 everywhere** (operator ruling recorded in the
   grok brief) — `run_pipeline`'s default included. Do not let a stash
   conflict resolution reintroduce any other figure.

## The bar for landing F21

Clean-tree baseline at `34588cb`: **872 passed, 7 skipped**. After your
re-apply, that number plus your new stage tests, with
`tests/test_walkstrip.py`, `tests/test_sheet_matches_what_was_sent.py`, and
`tests/test_puzzle.py` named green — those are the contracts your file is
most able to break. Sheet money must stay 9 / $275.00 / $316.25 on both
`sent` and `full`. Report with evidence per house rules.

If a stash apply goes sideways, do not force it — both stashes also exist as
commits in the stash reflog, and the captain lane kept nothing hidden: ask
and I will hand you the pair as patch files instead.
