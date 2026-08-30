# Brief: rebase feat/puzzle-solver onto master — captain lane, 2026-08-29

**Status: APPROVED by the operator 2026-08-29 and delivered to the grok lane.**

To: grok lane (clone at `~/.grok/worktrees/workspace-blue-toad-fleet/btd`,
branch `feat/puzzle-solver`, tip `8719eab`)
From: captain lane
Re: landing the puzzle solver for the Devpost submission (deadline Monday
Aug 31, 2026, 7:00pm CDT / 5:00pm PDT — the rebase should land Saturday to leave review margin)

## 0. The review verdict

The puzzle solver is approved in direction and mostly in implementation. I
read the design doc, all 11 commits, the full diff (23 files, 907 insertions,
`git diff --stat origin/master...HEAD`), and ran your suite in your worktree:
**708 passed, 7 skipped**. The design respects the lane boundary, states the
mechanics correctly, and wires BOTH lot-construction paths — the two-sheets-
disagree trap is avoided. Two findings block the merge; both are small. This
brief is the complete work order.

## 1. The rebase

Base has moved. Your branch forked at `2c5ba52`; master is now `46404b3`,
**13 commits ahead of your fork point** (your 11 are not in master; master's
13 are not in your branch). Rebase onto `46404b3` (or current master tip at
rebase time — check first, other lanes push live):

    git fetch origin
    git rebase origin/master

Before rebasing, **commit your worktree**: `src/appraiser/engine.py` and
`curator_voice.txt` are modified, and nine untracked files include your own
design docs (`docs/superpowers/specs/2026-08-22-puzzle-solver-design.md`, the
plan, `scripts/run_grounded_search_remaining.py` + its sidecar). The design
doc is the feature's contract — it belongs in the branch, not loose on one
disk.

## 2. Must-fix #1 — grouping is nondeterministic (demonstrated, not suspected)

`_merge_clusters` in `src/intake/puzzle.py` iterates `edges` from a Python
`set`. When a proposal chain crosses a caption cannot-link — an uncaptioned
photo between two numbered lots, the standard walk boundary — whichever edge
iterates first wins the photo, and set order varies by hash seed. Captain-lane
probe (A captioned "Lot 1", C captioned "Lot 2", uncaptioned B, proposals A–B
and B–C), run across eight PYTHONHASHSEED values:

    seed=0 -> [('A',), ('B','C')]     seed=1 -> [('A','B'), ('C',)]
    seed=4 -> [('A',), ('B','C')]     seed=2 -> [('A','B'), ('C',)]
    seed=5 -> [('A',), ('B','C')]     seed=3 -> [('A','B'), ('C',)]
    seed=6 -> [('A',), ('B','C')]     seed=7 -> [('A','B'), ('C',)]

Same input, different lot sheet — two identical cycle runs could bid
differently. Fix: iterate edges in a sorted, stable order (e.g.
`sorted(edges, key=lambda e: tuple(sorted(e)))`), and pin it with a test that
constructs exactly this A/B/C conflict and asserts one canonical outcome.
pytest cannot catch this on its own — one process, one seed — so the test
must assert the *choice*, not just stability.

## 3. Must-fix #2 — the budget cap goes back to $600

Your branch changes `STATE["budget_cap"]` 600.00 → 1000.00, the
`user_constraints` envelope, and the pipeline default (
`scripts/run_vertex_pipeline.py` docstring + `run_pipeline` signature). No
operator ruling authorizes $1,000: a full-tree search of tracked files found
no $1,000 cap anywhere in the main repo — every real `budget_cap` value in
code and data is 600.0 (or the demo's 2205.00), and the committed artifact of
the Aug-22 sheet itself, `data/aug22_gallery_4160518/pipeline_state.json:4`,
reads `"budget_cap": 600.0`. Your design doc's premise ("measured on the Aug
22 live sheet … $1,000 all-in cap") is therefore contradicted by that sheet's
own committed state file, and the doc cites no ruling for the figure.
**Revert all three sites to 600.00 during the rebase**, and correct the spec's
$1,000 references while you are in there. If the
operator rules $1,000, that lands as its own commit quoting the ruling, the
same way every mechanic ruling is recorded. A silent money-constant change is
the BT-087 incident class ($25 cap vs the authorized $15) and will not pass
review.

## 4. Times-the-money reconciliation — the tests that must stand

Your branch forked before `ca03311` ("times-the-money is all or nothing — an
election cannot cap it"), `98cdaf5`, and `1722a97`. The operator's ruling,
verbatim: *"all or nothing, take all N. Which is different than buyers
choice, dont confuse the two."* Consequences now pinned in master:

- `units_committed` ignores `units_wanted` on TTM lots.
- `elect()` refuses k<N on a TTM lot.
- `mechanic_from_ruling` treats "x3 bid, take 2" as a contradiction → UNKNOWN.
- A hypothesis property in `tests/test_pricing_invariants.py` asserts the
  asymmetry (CHOICE honors election, TTM does not).

Both sides touched `tests/test_bid_mechanics.py` and
`tests/test_elective_quantity.py` since the fork — master by 53 insertions /
10 deletions (the TTM rewrite), your branch by 4 lines (field-order pins for
the appended `labor` / `coverage_gap` fields, commit `a83f946`). Resolution
rule: **master's test bodies win everywhere; your only change is appending
`labor` and `coverage_gap` to the field-order pin lists.** If any TTM or
election test fails after your bidmath hunks apply, the fix is on your side —
those tests encode a ruling, not a preference.

Your bidmath edits themselves (LaborAspect/CoverageGap enums, appended Lot/
Decision fields, the price_lot SKIP short-circuit removal, the allocate SKIP
guard) are inside the two seams the design doc names and are approved as
designed. Nothing else in `src/bidmath/` moves.

## 5. What master gained that touches your surface

- **`a373423` — the walk strip.** `src/server.py` now has `/walk` and
  `/walk/photo/{seq}` routes plus a `_manifest_by_sequence()` helper; the
  walk route translates seat members matching `BT-<digits>` to manifest photo
  ids before rendering (non-BT members pass through untouched, so manifest-id
  seats work unmodified). `tests/test_walkstrip.py` (14 tests) must stay
  green after your grouping replaces the funnel — note
  `test_walk_page_joins_seats_to_manifest_photos` asserts grouped tiles
  exist; none of the tests pin the ungrouped COUNT, so seq 303 becoming a
  singleton under the puzzle loop is expected and welcome (it is the demo of
  your feature).
- **`46404b3` — `tests/conftest.py` now exists** (autouse fixture isolating
  the Gemma voice cache via `BTF_VOICE_CACHE`). You have no conftest, so no
  conflict — but do not delete or bypass it, and never run a local uvicorn
  against `/tmp` expectations in tests.
- **`get_aug22_state` has moved under you** (lot rulings, grounded-status
  seams). Re-apply your puzzle_loop wiring onto master's current function by
  hand — do not let the rebase auto-resolve that hunk. Same for the server
  import block.
- **Reshoot edges are approval-gated in master (F10).** Production consumes
  only the reviewed/approved edge sidecar. Wire `proposal_edges` from the
  same approved source the current grouping uses — proposals may be wrong
  and revisited, but an edge class the repo demoted to "proposed, unreviewed"
  must not re-enter production through the puzzle loop's back door.

## 6. Out of scope — do not touch

- `mechanic_from_ruling`, `clerk_directive`, greedy `allocate` ordering, and
  everything else in bidmath outside the two named seams.
- The sent sheet: `get_aug22_state(sheet="sent")` stays 9 lots / $275.00 /
  $316.25. `tests/test_sheet_matches_what_was_sent.py` is the tie.
- The walk strip renderer (`src/gate/walkstrip.py`) — grouping feeds it; the
  renderer is captain lane's.
- `scripts/run_vertex_pipeline.py` beyond your existing 60-line hunk: the
  live lane holds an uncommitted 974-line refactor of that file (F21). Your
  rebase lands first; they rebase onto you. Keep your footprint in that file
  minimal so their merge stays tractable.

## 7. The verification bar before you hand back

1. Full suite green in your worktree against the rebased branch —
   `.venv/bin/python -m pytest` from the repo venv (system python has no
   pytest). Master's clean-tree baseline is 834 collected / 827 passed +
   7 network skips; yours lands higher with your tests.
2. The determinism test from §2, red before the fix, green after — say so in
   the report, with the probe output.
3. `tests/test_walkstrip.py`, `tests/test_sheet_matches_what_was_sent.py`,
   `tests/test_pricing_invariants.py` all green — named explicitly because
   they are the three contracts your change is most able to break.
4. Report with evidence per house rules: every figure carries its command
   output; anything unverifiable is labelled. No "should work."

## 8. Landing

Push the rebased branch to origin as `feat/puzzle-solver` immediately after
the suite is green — those 11 commits currently exist on exactly one disk
(GitHub's upload-pack rejects the tip as "not our ref"; verified). Captain
lane reviews the bidmath and server hunks on the pushed branch, then the
operator calls the merge. Do not merge to master yourself.
