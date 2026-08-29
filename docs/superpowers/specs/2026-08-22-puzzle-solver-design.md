# Puzzle solver, not a funnel — design

**Date:** 2026-08-22
**Status:** drafted from the design talk; not an implementation plan
**Holds:** no new pricing overlay on the live sheet until Google-Search
notes exist for every cluster and have been inspected

The system is a **puzzle solver**. Every photo stays in play until
identity stabilizes. Then every cluster is valued (attempted). Shop fit
is a buying decision, never a drop.

Lane: `src/intake/`, `src/assemble/`, `src/appraiser/` (search notes),
console wiring. Bidmath stays Claude’s for `allocate` / `clerk_directive`
/ `mechanic_from_ruling` except two small seams named in §6. Do not
encode 181 into bidmath. Cloud Run `GET /` never calls Vertex embed.

---

## 1. Goal

Replace the three stacked funnels with one loop:

```
observe every photo
  → compare each piece across the entire auction
  → propose same-item / same-lot relationships
  → merge or split clusters
  → re-identify clusters using all available views
  → repeat until assignments and identities stabilize
  → then, and only then: mechanic → valuation attempt → shop annotations
    → allocate → clerk / console / pitch
```

**Is**

- Every photo a potential sale object. A wall, panel, door, or window
  might *be* the lot. There is no “not an item” class.
- Unmatched photo → singleton cluster.
- Multi-angle photos → one cluster, one valuation attempt, not duplicate
  prices.
- Weak evidence lowers confidence. It does not hide the cluster.
- Missing comps empty the dollar field. They do not invent a price.

**Is not**

- `worth_appraising` as a gate.
- Dropping `is_lot=false` gallery filler.
- Fit-score skipping `price_lot` before comps are read.
- Pricing or validation “agents.” Vertex API calls plus Python that can
  fail.
- COLMAP / FAISS / OpenCV hash stack.
- A live-request Vertex embed or search on Cloud Run `GET /`.
- Overlaying a new pricing run onto allocate until search-all is
  inspected (this hold).

---

## 2. What is wrong today

Three drop points, measured on the Aug 22 live sheet (353 clusters,
`$1,000` all-in cap):

1. **Triage funnel.** `worth_appraising=false` never reaches Stage 2
   unless the lot is in `REFERENCE_COMPS`. `group_into_lots` discards
   `is_lot=false` with no `same_lot_as_previous`. **159 of 353** clusters
   never entered `grounded_prices.json` because they were never
   appraised.
2. **Identity is one-shot, walk-local, merge-only.** Caption lot numbers
   + `same_lot_as_previous` + mutual-top-1 reshoot edges. No split, no
   iterate, appraisal of the primary photo only. `apply_trajectory` is
   still test-only in production.
3. **Pricing coverage gated on fit and agreement.** `fit < 0.35` →
   `SKIP` with no number, comps unread. Of the **228** that *were*
   searched: **116 usable / 112 refused (50.9%)**. 98 of the 112 failed
   because the three Google-Search highs disagreed by more than 1.6×.
   The console still says “no external comp” for those 76 live cards.
   Sixteen SKIP lots have a usable grounded range in cache that bidmath
   never applied.

The 9-lot / `$275` absentee email is a closed artifact
(`get_aug22_state(sheet="sent")`). This spec is the full sheet.

---

## 3. Cluster assignment

The board is every photo. Every photo is a node. Nothing is dropped.

### 3.1 Constraints vs proposals

**Must-link / cannot-link** come only from the auctioneer’s lot numbers
in captions.

- Same number → they are one lot. A split cannot cut this.
- Different numbers → they are not, even if they look alike.
- Uncaptioned photos are unconstrained.

**Proposals** can be wrong and are revisited each round:

- Walk adjacency (`same_lot_as_previous`, spatial trajectory).
- Mutual-top-1 embedding edges, walk-adjacent excluded before nn,
  `SANITY_FLOOR = 0.80`. This is 2↔181. Unchanged from Slice A.

`is_lot=false` is not a trapdoor. It is another photo that may merge or
stay singleton.

One grouping space: `BT-00N`. Same as today.

### 3.2 A round

1. Seed: singletons, then apply must-links.
2. Merge along proposals (respect cannot-link).
3. Re-identify changed clusters from all member views (§4).
4. Split when identity is mixed **and** no must-link forbids it.
   Two photos the auctioneer numbered as one lot that look like
   different objects stay one cluster: container / choice, not a split.
5. Repeat.

Initial state of a drop is singletons + must-links, then the loop.

---

## 4. Re-identify and stop

After membership moves, identify the cluster from **all** of its views.
That means a per-photo appraisal of every member, then today’s assemble
rule on the set — not one call on the primary frame:

- Worst `condition_penalty` wins.
- Identification from the best-evidence photo (highest appraiser
  confidence; tie → primary).
- Comps are looked up, never blended.

**Do not use identity text as the stop.** A model will rephrase every
pass. The stop is:

1. Photo membership unchanged from the previous round, then one final
   re-identify on that frozen set.
2. Hard cap of **3 rounds**, even if still moving.

Unchanged clusters are not re-appraised. Embeddings stay the on-disk
cache. `GET /` still does not call Vertex embed.

Fit score may be recorded on the identity. It does not merge, split,
drop, or skip re-identify.

---

## 5. After the puzzle

The puzzle’s job ends when membership is stable. What follows is a
**sheet**, not another funnel.

```
stable clusters
  → how the house sells it (mechanic, k)
  → valuation attempt (search notes → number, or empty dollar)
  → shop annotations (fit, labor, velocity) — never a drop
  → allocate against the $1,000 all-in cap
  → clerk line, console, pitch
```

**Mechanic first.** Straight / choice / times-the-money. A ruling on
file wins; unknown stays unknown and fail-closes auto-send. This is why
BT-002 is `$25` per unit × 3, not a `$25` lot. `mechanic_from_ruling`
is unchanged.

**Then valuation attempt** (§6). **Then shop annotations** (§7).
**Then allocate.** Surfaces: every cluster visible (seats + unplaced
holding strip). Cards carry identity, labor, money-or-empty, clerk
line. Curator pitch reads the allocated sheet only.

---

## 6. Valuation — attempt every cluster, invent nothing

Chosen reading **B:** identity is complete; the dollar field stays empty
until usable comps exist. “Valuation” means coverage was attempted, not
that a price was invented.

### 6.1 API calls, not agents

No pricing agent. No validation agent. A validation LLM is the model
grading its own homework — and when asked to fill a `sources` field it
returned `https://www.bssauction.com`, which cites nothing.

| Step | Who | Why |
|---|---|---|
| 3× Google Search notes | `generate_content` + `GoogleSearch` | Attend the web; keep tool-authored citations |
| Extract `{low, high, sold_count}` | schema call, **no search** | Cannot invent a figure the note did not state |
| Agree / refuse | Python (`price_is_usable`, `median_price`) | Deterministic |
| Bid fraction, $5 snap, all-in | bidmath | Already not a model |

This is what `src/appraiser/pricing.py` already does (`MIN_CALLS = 3`,
`MAX_SPREAD_RATIO = 1.6`, `MIN_SOLD_COMPS = 2`, citations from
`grounding_metadata`). Keep it.

`value_magnitude_hint` is never a price. Grounded overlay, then
`REFERENCE_COMPS` winning on the 12, stays as it is **after** the hold
in §6.3 lifts.

Optional fourth call: `gemini-3.6-flash` (or 3.7 when Vertex serves it,
pinned in `src/appraiser/routing.py`) sees only cluster identity + the
three notes + citation URLs. No search tool. Python still decides
usable vs empty. Do not let that call average `$40–$60` with
`$40–$147.50` into a fake consensus.

Mechanic `UNKNOWN` is not a valuation refuse. The cluster can have a
number; we still need a ruling before the clerk spends it.

### 6.2 Fit does not run here

Today `fit_score < 0.35` skips `price_lot` before comps. After this
spec, a low-fit cluster with usable comps still has max / all-in; we
may not bid (§7).

**Bidmath seams (small, named):**

- `price_lot` computes a number whenever comps exist, including low-fit
  lots.
- `allocate` never spends `Priority.SKIP` leftovers when budget remains.
  Explicit skip, not “no money so it cannot allocate.”
- Do not rewrite greedy allocation, `clerk_directive`, or
  `mechanic_from_ruling`.

### 6.3 Hold — search all, then inspect, then price overlay

Do not start another live-sheet pricing run until Google-Search notes
exist for **every** cluster and have been inspected.

- Existing 228 rows stay in `data/aug22_gallery_4160518/grounded_prices.json`.
- The 159 never-run clusters are searched by
  `scripts/run_grounded_search_remaining.py` into the sidecar
  `data/aug22_gallery_4160518/grounded_search_remaining.json`.
- The sidecar records notes + samples + a *would-be* `usable` flag.
  `load_grounded_prices()` does **not** read it. The `$1,000` sheet
  does not move.
- After inspection: decide whether to merge the sidecar, loosen
  `MAX_SPREAD_RATIO`, or keep empty dollars. That decision is out of
  this spec.

Search is an offline batch. Console `GET /` does not call it.

---

## 7. Buying (fit last)

| Signal | Does | Does not |
|---|---|---|
| **Fit** | `SKIP` = we will not bid | hide the cluster or erase a price |
| **Labor** | shelf / list / research tag | drop or unprice |
| **Velocity** | 14-day public cadence, when it exists | drop from identity |
| **Budget** | `$1,000` all-in, `$5` increments, 15% fee | change identity |
| **Auto-send** | fail-closed | send SKIP, empty dollar, `UNKNOWN` mechanic, speculative remainder |

Operator caps and recorded rulings still win on the lots that have them.
Labor is already stamped in assemble (`src/assemble/labor.py`). Velocity
is not in this spec’s first implementation slice.

---

## 8. Console / API

- Every stable cluster is a card. Empty dollar renders as empty dollar,
  not “no external comp” when search ran and was refused. Copy must
  distinguish **never searched**, **searched but disagreed**, and
  **no sold comps**.
- Labor tag stays on the card (`shelf` / `list` / `research`).
- Seats + holding strip unchanged from Slice A.
- `/api/lots` already has `labor` and grounded fields. Add a coverage
  reason when the dollar is empty (`not_searched` / `spread` /
  `no_sold_comps` / `asking_only`). Do not invent a number to fill it.

---

## 9. Tests (contracts)

Pin these; they are the design.

- A photo with `is_lot=false` and no same-lot flag becomes a singleton,
  not a drop.
- Caption must-link cannot be split; different caption numbers cannot
  merge.
- Mixed unconstrained identities split; mixed must-linked identities
  stay one cluster.
- Loop stops when membership is unchanged; identity rephrase alone does
  not continue the loop. Round 4 never runs.
- `price_lot` on a low-fit lot with comps returns a number and
  `Priority.SKIP`.
- `allocate` does not spend SKIP when budget remains.
- `load_grounded_prices` ignores the remaining-search sidecar.
- Console HTML for a spread-refused lot does not say “no external comp.”

Existing field-order pins on `Lot` / `Decision` stay: new fields append
last.

---

## 10. Key decisions

1. **Puzzle, not funnel.** No `worth_appraising` gate, no photo drop.
2. **No “not an item” class.** We cannot know a panel is not merchandise.
3. **Must-link = caption lot numbers only.** Everything else is a
   proposal.
4. **Stop on membership, cap 3.** Not on identity string equality.
5. **Valuation B.** Empty dollar if comps unusable; do not invent.
6. **API + Python, not agents.** Three search notes, extract, Python
   keep-or-empty.
7. **Fit last.** Number can exist on a SKIP. Allocate will not spend it.
8. **Search-all hold.** Sidecar for the 159; live sheet frozen until
   inspection.
9. **Sent email closed.** `sheet="sent"` stays 9 / `$275` / `$316.25`.

---

## 11. Out of scope for the first implementation slice

- Loosening `MAX_SPREAD_RATIO` or redefining “usable.”
- 14-day eBay cadence scrape on 353 lots.
- Production `apply_trajectory` beyond using it as a walk *proposal*
  inside the puzzle loop (it may be wired; it is not the whole solver).
- Gemma curator rewrite.
- Package rename, COLMAP, Pub/Sub, GKE.

---

## 12. Implementation outline (not a plan)

Order after this spec is approved:

1. Assignment + no-drop grouping tests, then code (`group_into_lots`
   stop dropping; must/cannot-link).
2. Puzzle loop: merge proposals, split, membership stop, round cap.
   Re-identify all views via assemble rule.
3. Bidmath seams in §6.2. Console copy for empty-dollar reasons.
4. Search-all sidecar is already in flight. Inspection, then a separate
   decision to overlay.

Each step is TDD. Do not start 4’s overlay in the same PR as 1–3.
