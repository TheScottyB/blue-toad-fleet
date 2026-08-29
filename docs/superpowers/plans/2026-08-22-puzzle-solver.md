# Puzzle Solver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every photo becomes a cluster; clusters stabilize by merge/split; every cluster is valuation-attempted; shop fit only decides whether we bid.

**Architecture:** New `src/intake/puzzle.py` owns seed / proposals / loop. `group_into_lots` stops dropping photos. Bidmath two seams only: `price_lot` still prices low-fit lots; `allocate` never spends `SKIP`. Console distinguishes empty-dollar reasons. Search sidecar stays off the live sheet.

**Tech Stack:** Python 3.14, pytest, existing Vertex Google-Search batch (already running into the sidecar). No new dependencies. No agents.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-22-puzzle-solver-design.md`
- Do not rewrite `allocate` greedy sort, `clerk_directive`, or `mechanic_from_ruling`
- Do not encode 181 into bidmath
- Cloud Run `GET /` never calls Vertex embed or Google Search
- No COLMAP / FAISS / OpenCV hash stack
- No pricing or validation agents
- `load_grounded_prices()` does not read `grounded_search_remaining.json`
- Do not overlay the sidecar onto allocate in this plan
- Sent sheet `get_aug22_state(sheet="sent")` stays 9 / $275 / $316.25
- `Lot` / `Decision` new fields append last
- Budget cap stays `$600.00` all-in
- `SANITY_FLOOR = 0.80`; walk-adjacent is `|Δseq| == 1`
- TDD: failing test first on every task
- Do not commit unless the operator asked; skip commit steps if the working tree policy is “no commit”

## File map

- Create: `src/intake/puzzle.py` — `Cluster`, constraints, seed, proposals, loop
- Modify: `src/intake/manifest.py` — `group_into_lots` no-drop
- Modify: `src/intake/__init__.py` — export puzzle symbols
- Modify: `src/assemble/__init__.py` — accept precomputed groups
- Modify: `src/assemble/grounded.py` — refuse the sidecar path
- Modify: `src/bidmath/__init__.py` — `CoverageGap`, `price_lot` fit-last, `allocate` SKIP guard
- Modify: `src/gate/render.py` — empty-dollar copy
- Modify: `src/server.py` — puzzle_loop, coverage_gap, `/api/lots`
- Modify: `scripts/run_vertex_pipeline.py` — no `worth_appraising` gate
- Modify: `scripts/dry_run_single_photo.py` — do not STOP on `worth_appraising=false`
- Test: `tests/test_lot_grouping.py`, `tests/test_puzzle.py`, `tests/test_bidmath.py` / `tests/test_pricing_invariants.py`, `tests/test_corpus.py`, `tests/test_labor.py` field-order files, `tests/test_server.py`, `tests/test_docs_match_the_sheet.py`

---

### Task 1: No photo is dropped

**Files:**
- Modify: `src/intake/manifest.py` (`group_into_lots`)
- Modify: `tests/test_lot_grouping.py`

**Interfaces:**
- Consumes: `TriagedPhoto(photo_id, caption, is_lot, same_lot_as_previous)`
- Produces: `group_into_lots` still returns `list[LotGroup]`; unmatched `is_lot=false` is a singleton, not a skip

- [ ] **Step 1: Write the failing test**

Replace `test_filler_photos_are_not_lots` in `tests/test_lot_grouping.py` with:

```python
def test_an_unmatched_non_lot_photo_is_a_singleton():
    """A banner might be a panel they are selling. Unmatched → singleton."""
    groups = group_into_lots([
        photo("p1", "Tonka crane"),
        photo("p2", "Blue Toad Auctions banner", is_lot=False),
    ])
    assert {g.photo_ids for g in groups} == {("p1",), ("p2",)}
```

Keep `test_non_lot_photo_flagged_same_as_previous_still_attaches` as-is.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_lot_grouping.py::test_an_unmatched_non_lot_photo_is_a_singleton -q --tb=short`

Expected: FAIL — `p2` missing, only `("p1",)`

- [ ] **Step 3: Write minimal implementation**

In `src/intake/manifest.py` `group_into_lots`, delete the drop:

```python
        if p.same_lot_as_previous and last is not None:
            last["photos"].append(p.photo_id)
            continue

        g = {"key": f"seq:{p.photo_id}", "photos": [p.photo_id]}
        groups.append(g)
        last = g
```

Remove the `if not p.is_lot: continue` branch. Update the function docstring: `is_lot=False` with no same-lot flag is a singleton, not filler discard.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_lot_grouping.py tests/test_spatial.py tests/test_assemble.py -q --tb=short`

Expected: PASS. If a spatial test assumed filler drop, update that test to the singleton contract — do not restore the drop.

- [ ] **Step 5: Commit** (skip if no-commit policy)

```bash
git add src/intake/manifest.py tests/test_lot_grouping.py
git commit -m "feat: unmatched photos become singleton clusters, not drops"
```

---

### Task 2: Caption must-link / cannot-link and seed

**Files:**
- Create: `src/intake/puzzle.py`
- Modify: `src/intake/__init__.py`
- Test: `tests/test_puzzle.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class Cluster: cluster_id: str; photo_ids: tuple[str, ...]`
  - `caption_must_components(photos: list[TriagedPhoto]) -> list[tuple[str, ...]]`
  - `cannot_link(photos: list[TriagedPhoto]) -> set[frozenset[str]]`
  - `seed_clusters(photos: list[TriagedPhoto]) -> list[Cluster]`
  - `GENERIC_CATEGORIES = frozenset({"other", "unsorted", "general estate", ""})`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_puzzle.py`:

```python
from src.intake.manifest import TriagedPhoto
from src.intake.puzzle import cannot_link, seed_clusters


def P(pid, caption="", same=False, is_lot=True):
    return TriagedPhoto(photo_id=pid, caption=caption,
                        is_lot=is_lot, same_lot_as_previous=same)


class TestSeed:
    def test_uncaptioned_photos_start_as_singletons(self):
        cs = seed_clusters([P("a"), P("b")])
        assert sorted(c.photo_ids for c in cs) == [("a",), ("b",)]

    def test_same_caption_lot_number_is_must_link(self):
        cs = seed_clusters([
            P("a", "Lot 47 truck"),
            P("b", "Lot 12 glass"),
            P("c", "Lot 47 reverse"),
        ])
        by = {frozenset(c.photo_ids): c for c in cs}
        assert frozenset({"a", "c"}) in by
        assert frozenset({"b"}) in by

    def test_different_lot_numbers_are_cannot_link(self):
        photos = [P("a", "Lot 47 truck"), P("b", "Lot 48 trumpet")]
        assert frozenset({"a", "b"}) in cannot_link(photos)

    def test_walk_flag_does_not_seed_a_merge(self):
        """Walk is a proposal, not a constraint."""
        cs = seed_clusters([P("a", "truck"), P("b", "angle", same=True)])
        assert sorted(c.photo_ids for c in cs) == [("a",), ("b",)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_puzzle.py -q --tb=short`

Expected: FAIL — `src.intake.puzzle` missing

- [ ] **Step 3: Write minimal implementation**

Create `src/intake/puzzle.py`:

```python
"""Puzzle assignment: every photo is a node. Caption numbers constrain; everything else proposes."""

from dataclasses import dataclass
from src.intake.manifest import TriagedPhoto, lot_number_from

GENERIC_CATEGORIES = frozenset({"other", "unsorted", "general estate", ""})


@dataclass(frozen=True)
class Cluster:
    cluster_id: str
    photo_ids: tuple[str, ...]


def cannot_link(photos: list[TriagedPhoto]) -> set[frozenset[str]]:
    numbered = [(p.photo_id, lot_number_from(p.caption)) for p in photos]
    out: set[frozenset[str]] = set()
    for i, (a, na) in enumerate(numbered):
        if na is None:
            continue
        for b, nb in numbered[i + 1:]:
            if nb is not None and na != nb:
                out.add(frozenset({a, b}))
    return out


def seed_clusters(photos: list[TriagedPhoto]) -> list[Cluster]:
    by_num: dict[str, list[str]] = {}
    singles: list[str] = []
    for p in photos:
        n = lot_number_from(p.caption)
        if n is None:
            singles.append(p.photo_id)
        else:
            by_num.setdefault(n, []).append(p.photo_id)
    clusters = [Cluster(cluster_id=num, photo_ids=tuple(ids))
                for num, ids in by_num.items()]
    clusters.extend(Cluster(cluster_id=f"seq:{pid}", photo_ids=(pid,))
                    for pid in singles)
    return clusters
```

Export `Cluster`, `seed_clusters`, `cannot_link`, `GENERIC_CATEGORIES` from `src/intake/__init__.py`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_puzzle.py -q --tb=short`

Expected: PASS

- [ ] **Step 5: Commit** (skip if no-commit policy)

```bash
git add src/intake/puzzle.py src/intake/__init__.py tests/test_puzzle.py
git commit -m "feat: seed clusters from caption must-links only"
```

---

### Task 3: Puzzle loop — merge, split, stop

**Files:**
- Modify: `src/intake/puzzle.py`
- Modify: `tests/test_puzzle.py`

**Interfaces:**
- Consumes: `Cluster`, `seed_clusters`, `cannot_link` from Task 2
- Produces:
  - `walk_proposal_edges(photos: list[TriagedPhoto]) -> set[frozenset[str]]`
  - `identities_mixed(members: list[tuple[str, str]]) -> bool`  # (identification, category) per photo
  - `split_cluster(cluster: Cluster, per_photo: dict[str, tuple[str, str]], must_together: set[frozenset[str]]) -> list[Cluster]`
  - `puzzle_loop(photos, *, proposal_edges: set[frozenset[str]], identify: Callable[[tuple[str, ...]], dict[str, tuple[str, str]]], max_rounds: int = 3) -> list[Cluster]`
  - `identify(photo_ids) -> dict[photo_id, (identification, category)]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_puzzle.py`:

```python
from src.intake.puzzle import (
    identities_mixed, puzzle_loop, split_cluster, walk_proposal_edges,
)


class TestProposalsAndSplit:
    def test_walk_flag_is_a_proposal_edge(self):
        photos = [P("a", "truck"), P("b", "angle", same=True)]
        assert frozenset({"a", "b"}) in walk_proposal_edges(photos)

    def test_cannot_link_blocks_a_walk_proposal(self):
        photos = [P("a", "Lot 47 truck"), P("b", "Lot 48 trumpet", same=True)]
        assert frozenset({"a", "b"}) not in walk_proposal_edges(photos)

    def test_jewelry_vs_edison_is_mixed(self):
        assert identities_mixed([
            ("costume jewelry tray", "jewelry"),
            ("Edison cylinder records", "phonograph / records"),
        ]) is True

    def test_two_other_categories_are_not_mixed(self):
        assert identities_mixed([
            ("box of smalls", "other"),
            ("another box", "other"),
        ]) is False

    def test_must_link_is_not_split(self):
        from src.intake.puzzle import Cluster
        c = Cluster("47", ("a", "b"))
        out = split_cluster(
            c,
            {"a": ("jewelry", "jewelry"), "b": ("edison", "phonograph / records")},
            must_together={frozenset({"a", "b"})},
        )
        assert out == [c]


class TestLoop:
    def test_walk_proposal_merges_then_stops(self):
        photos = [P("a", "truck"), P("b", "angle", same=True)]
        calls = []

        def identify(ids):
            calls.append(ids)
            return {pid: ("truck", "vintage toys") for pid in ids}

        out = puzzle_loop(photos, proposal_edges=walk_proposal_edges(photos),
                          identify=identify)
        assert [c.photo_ids for c in out] == [("a", "b")]
        assert len(calls) <= 3

    def test_mixed_unconstrained_photos_split(self):
        photos = [P("a"), P("b")]
        ids = {
            "a": ("costume jewelry", "jewelry"),
            "b": ("Edison cylinders", "phonograph / records"),
        }
        out = puzzle_loop(
            photos,
            proposal_edges={frozenset({"a", "b"})},
            identify=lambda pids: {p: ids[p] for p in pids},
        )
        assert sorted(c.photo_ids for c in out) == [("a",), ("b",)]

    def test_identity_rephrase_does_not_continue_the_loop(self):
        photos = [P("a", "truck")]
        n = {"i": 0}

        def identify(ids):
            n["i"] += 1
            return {pid: (f"truck pass {n['i']}", "vintage toys") for pid in ids}

        puzzle_loop(photos, proposal_edges=set(), identify=identify)
        assert n["i"] <= 2  # one identify on seed set + optional final; never 4

    def test_round_cap_is_three(self):
        photos = [P("a"), P("b"), P("c")]
        rounds = {"n": 0}

        def identify(ids):
            rounds["n"] += 1
            # always disagree so a naive loop would never halt
            return {pid: (pid, pid) for pid in ids}

        puzzle_loop(
            photos,
            proposal_edges={frozenset({"a", "b"}), frozenset({"b", "c"})},
            identify=identify, max_rounds=3,
        )
        assert rounds["n"] <= 4  # 3 rounds + final freeze identify
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_puzzle.py -q --tb=short`

Expected: FAIL — missing symbols

- [ ] **Step 3: Write minimal implementation**

Add to `src/intake/puzzle.py` (keep seed helpers). Loop algorithm:

1. `clusters = seed_clusters(photos)`
2. `blocked = cannot_link(photos)`
3. `must =` pairs that share a caption lot number (same components as seed)
4. `edges = {e for e in proposal_edges if e not in blocked}` union walk edges already filtered
5. For `round in range(max_rounds)`:
   - snapshot membership as `frozenset` of `frozenset(photo_ids)`
   - union-find merge clusters along `edges` that do not join a blocked pair
   - `identify` each cluster whose membership is new or never identified
   - `split_cluster` any mixed cluster unless `must` keeps those photos together
   - if membership equals snapshot: `identify` any cluster still missing identity; break
6. After 3 rounds, stop even if still moving; one final `identify` on the frozen set

`identities_mixed`: True iff two members have categories `ca, cb` where both `casefold` values are nonempty, not in `GENERIC_CATEGORIES`, and `ca != cb`.

`walk_proposal_edges`: consecutive photos in input order; emit `{prev, curr}` when `curr.same_lot_as_previous` and `{prev, curr}` not in `cannot_link(photos)`.

`split_cluster`: if not mixed or must-together covers all photos, return `[cluster]`. Else partition by category (generic stays with no one — each generic photo a singleton unless must-linked).

Union-find merge: same pattern as `merge_reshoots` in `src/intake/spatial.py`. Cluster id: caption number if any member has one, else `seq:{first_photo_id}`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_puzzle.py -q --tb=short`

Expected: PASS

- [ ] **Step 5: Commit** (skip if no-commit policy)

```bash
git add src/intake/puzzle.py tests/test_puzzle.py
git commit -m "feat: puzzle loop merge/split with membership stop and round cap 3"
```

---

### Task 4: Wire the loop into assemble and the live sheet

**Files:**
- Modify: `src/assemble/__init__.py`
- Modify: `src/server.py` (`get_aug22_state`)
- Modify: `scripts/run_vertex_pipeline.py`
- Test: `tests/test_assemble.py` or `tests/test_puzzle.py` (integration with `assemble_lots`)

**Interfaces:**
- Consumes: `puzzle_loop`, `walk_proposal_edges`, `merge_reshoots` / reshoot edges
- Produces: `assemble_lots(..., groups: list[LotGroup] | None = None)` — if `groups` given, skip internal `group_into_lots`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_puzzle.py`:

```python
from src.assemble import AppraisedPhoto, assemble_lots
from src.intake.manifest import LotGroup
from src.intake.puzzle import Cluster


def test_assemble_accepts_precomputed_groups():
    photos = [
        AppraisedPhoto(photo_id="a", caption="x", identification="truck",
                       category="vintage toys", is_lot=True),
        AppraisedPhoto(photo_id="b", caption="y", identification="truck",
                       category="vintage toys", is_lot=True),
    ]
    groups = [LotGroup(lot_key="seq:a", photo_ids=("a", "b"))]
    lots = assemble_lots(photos, groups=groups)
    assert len(lots) == 1
    assert lots[0].lot_id == "seq:a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_puzzle.py::test_assemble_accepts_precomputed_groups -q --tb=short`

Expected: FAIL — unexpected keyword `groups`

- [ ] **Step 3: Write minimal implementation**

In `assemble_lots`, add `groups: list | None = None`. When `groups` is None, keep `group_into_lots` + optional `merge_reshoots`. When provided, use those groups and still apply `merge_reshoots` if `reshoot_edges` is passed *only if the caller did not already*. **Caller contract:** server/pipeline run `puzzle_loop` with `proposal_edges = walk_proposal_edges | reshoot_edges`, convert clusters to `LotGroup`, pass `groups=` and `reshoot_edges=None` so edges are not applied twice.

Helper in `src/intake/puzzle.py`:

```python
def as_lot_groups(clusters: list[Cluster]) -> list[LotGroup]:
    from src.intake.manifest import LotGroup
    return [LotGroup(lot_key=c.cluster_id, photo_ids=c.photo_ids) for c in clusters]
```

In `get_aug22_state` and `run_pipeline`, after building `appraised_photos` / `triaged_photos` and loading reshoot edges:

```python
from src.intake.puzzle import puzzle_loop, walk_proposal_edges, as_lot_groups

identify = lambda pids: {
    pid: (
        (by_id[pid].identification or by_id[pid].caption, by_id[pid].category)
        if pid in by_id else ("", "unsorted")
    )
    for pid in pids
}
# by_id maps photo_id → AppraisedPhoto (or a tiny stub with caption/category)
clusters = puzzle_loop(
    triaged_photos,
    proposal_edges=walk_proposal_edges(triaged_photos) | {frozenset(e) if not isinstance(e, frozenset) else e for e in edges},
    identify=identify,
)
lots = assemble_lots(appraised_photos, comps=comps, groups=as_lot_groups(clusters))
```

Reshoot `edges` is already `set[frozenset]`. Union with walk proposals. Do not call `merge_reshoots` again.

`identify` must not call Vertex. It reads cached appraisals / captions only.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_puzzle.py tests/test_assemble.py tests/test_reshoot.py tests/test_server.py::test_api_lots_summary_and_bids tests/test_sheet_matches_what_was_sent.py -q --tb=short`

Expected: PASS. Sent sheet still 9 / $275.

- [ ] **Step 5: Commit** (skip if no-commit policy)

```bash
git add src/assemble/__init__.py src/intake/puzzle.py src/server.py scripts/run_vertex_pipeline.py tests/test_puzzle.py
git commit -m "feat: assemble and live sheet consume puzzle_loop groups"
```

---

### Task 5: `price_lot` prices low-fit lots (fit last)

**Files:**
- Modify: `src/bidmath/__init__.py` (`price_lot`)
- Test: `tests/test_bidmath.py` or `tests/test_pricing_invariants.py`

**Interfaces:**
- Consumes: existing `Lot`, `CompEstimate`, `_priority_for`
- Produces: `price_lot` on fit `< 0.35` with comps returns `max_bid is not None` and `priority is Priority.SKIP`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_bidmath.py` (use the existing `lot` / `comp` helpers in that file):

```python
def test_low_fit_with_comps_still_has_a_number():
    from src.bidmath import Priority, price_lot
    d = price_lot(lot(lot_id="L", fit=0.20, c=comp(low=40, high=80, n=3)))
    assert d.priority is Priority.SKIP
    assert d.max_bid is not None and d.max_bid > 0
    assert d.needs_human_pricing is False
```

If `lot()` in that file uses a different signature, match it. If there is no `lot` helper, construct `Lot(...)` the same way neighboring tests do.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_bidmath.py::test_low_fit_with_comps_still_has_a_number -q --tb=short`

Expected: FAIL — `max_bid is None`

- [ ] **Step 3: Write minimal implementation**

In `price_lot`, **delete** the early return:

```python
    if priority is Priority.SKIP:
        return Decision(..., max_bid=None, ...)
```

Keep computing comps / snap as today. After a successful number (or empty-dollar no-comp branch):

- If no comps: existing `needs_human_pricing=True`, `max_bid=None`; if fit was SKIP, `priority=Priority.SKIP` still.
- If comps and fit SKIP: `priority=Priority.SKIP`, **keep** `max_bid` / `all_in`.
- If computed max `< BID_INCREMENT`: still SKIP with `max_bid=None` (not worth a slot) — that is increment discipline, not fit.

Do not change `_priority_for`. Do not change `clerk_directive` or `mechanic_from_ruling`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_bidmath.py tests/test_pricing_invariants.py tests/test_bid_mechanics.py tests/test_elective_quantity.py tests/test_regressions.py -q --tb=short`

Expected: PASS. If an invariant assumed SKIP ⇒ `max_bid is None`, update that invariant to: SKIP ⇒ `allocated is False` after allocate, number may exist.

- [ ] **Step 5: Commit** (skip if no-commit policy)

```bash
git add src/bidmath/__init__.py tests/test_bidmath.py tests/test_pricing_invariants.py
git commit -m "feat: price_lot keeps a number on low-fit lots"
```

---

### Task 6: `allocate` never spends SKIP

**Files:**
- Modify: `src/bidmath/__init__.py` (`allocate`)
- Test: `tests/test_bidmath.py`

**Interfaces:**
- Consumes: `Decision` with `priority` and `max_bid`
- Produces: SKIP decisions always `allocated=False`, even when `committed_all_in` fits the remaining cap

- [ ] **Step 1: Write the failing test**

```python
def test_allocate_does_not_spend_skip_leftovers():
    from src.bidmath import Decision, Priority, allocate, all_in_cost
    skip = Decision(
        lot_id="S", category="c", priority=Priority.SKIP,
        max_bid=50.0, all_in=all_in_cost(50.0), bid_fraction=0.375,
        reason="fit", needs_human_pricing=False,
    )
    out = allocate([skip], budget_cap=10_000.0)
    assert out[0].allocated is False
    assert out[0].auto_send is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_bidmath.py::test_allocate_does_not_spend_skip_leftovers -q --tb=short`

Expected: FAIL — `allocated is True` (SKIP ranks last but still spends)

- [ ] **Step 3: Write minimal implementation**

In `allocate`, inside the `for d in priced` loop, before the cap check:

```python
        if d.priority is Priority.SKIP:
            out.append(replace(d, allocated=False, auto_send=False))
            continue
```

Do not change sort keys, density, or auto_send rules for A/B/C.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_bidmath.py tests/test_pricing_invariants.py tests/test_bid_mechanics.py -q --tb=short`

Expected: PASS

- [ ] **Step 5: Commit** (skip if no-commit policy)

```bash
git add src/bidmath/__init__.py tests/test_bidmath.py
git commit -m "feat: allocate never spends SKIP leftover budget"
```

---

### Task 7: Empty-dollar reasons (console + API + sidecar hold)

**Files:**
- Modify: `src/bidmath/__init__.py` — `CoverageGap` enum, `Decision.coverage_gap` appended last
- Modify: `src/gate/render.py` — refuse copy
- Modify: `src/server.py` — stamp `coverage_gap`; `/api/lots` field
- Modify: `src/assemble/grounded.py` — ignore sidecar filename even if passed
- Modify: `tests/test_bid_mechanics.py`, `tests/test_elective_quantity.py` field-order pins
- Modify: `tests/test_labor.py` console test still looks for labor tags
- Test: `tests/test_server.py`, `tests/test_puzzle.py` or `tests/test_gate.py`

**Interfaces:**
- Produces: `class CoverageGap(str, Enum): NONE=""; NOT_SEARCHED="not_searched"; SPREAD="spread"; NO_SOLD_COMPS="no_sold_comps"; ASKING_ONLY="asking_only"`
- `Decision.coverage_gap: CoverageGap = CoverageGap.NONE` (last field, after `labor`)
- Console refuse copy:
  - `not_searched` → “Not searched yet”
  - `spread` → “Search disagreed — human pricing required”
  - `no_sold_comps` / `asking_only` → “No sold comps — human pricing required”
  - default / NONE with `needs_human_pricing` → keep “No external comp — human pricing required” only when we truly have no search row
- `/api/lots` includes `"coverage_gap": d.coverage_gap.value`
- `load_grounded_prices()`: if `path` name is `grounded_search_remaining.json`, return `{}`

- [ ] **Step 1: Write the failing tests**

Field-order (update existing pins):

```python
assert names[6:] == ["mechanic", "unit_count", "units_wanted", "labor"]
# Decision:
assert names[10:] == [..., "speculative", "labor", "coverage_gap"]
```

New:

```python
def test_sidecar_is_not_a_price_cache():
    from src.assemble.grounded import load_grounded_prices
    from pathlib import Path
    p = Path("data/aug22_gallery_4160518/grounded_search_remaining.json")
    got = load_grounded_prices(p)
    assert got == {}


def test_spread_refuse_copy_does_not_say_no_external_comp():
    from dataclasses import replace
    from src.bidmath import CoverageGap, Decision, Priority
    from src.gate import CycleView, render_console
    from src.appraisal import build_queue
    from src.bidmath import summarize
    d = Decision(
        lot_id="BT-006", category="other", priority=Priority.B,
        max_bid=None, all_in=None, bid_fraction=None,
        reason="search disagreed", needs_human_pricing=True,
        coverage_gap=CoverageGap.SPREAD,
    )
    v = CycleView(
        cycle_id="x", auction_date="x", photos_ingested=1,
        queue=build_queue([], []), decisions=[d], summary=summarize([d]),
        budget_cap=1000, auto_send_threshold=35,
        captions={"BT-006": "signed cap"},
    )
    h = render_console(v)
    assert "no external comp" not in h.lower()
    assert "disagreed" in h.lower()
```

Stamp helper: in `get_aug22_state`, after `price_lot`, if `needs_human_pricing` and lot_id not in `load_grounded_prices()` → `CoverageGap.NOT_SEARCHED`. If grounded row exists and `not usable`: if samples’ highs spread > 1.6 → `SPREAD`; else if `sold_comp_count` median < 2 → `NO_SOLD_COMPS`; else `SPREAD` (dominant live failure). Do not read the sidecar.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_bid_mechanics.py::TestDefaultsPreserveEveryExistingSheet tests/test_gate.py tests/test_puzzle.py -q --tb=line` plus the new tests by node id once named.

Expected: FAIL — no `CoverageGap`, sidecar currently loads if pointed at the file

- [ ] **Step 3: Write minimal implementation**

Append `CoverageGap` next to `LaborAspect`. Append field on `Decision`. Carry `coverage_gap` through `price_lot` default NONE; server `replace`s it after.

`load_grounded_prices`:

```python
    path = Path(path or "data/aug22_gallery_4160518/grounded_prices.json")
    if path.name == "grounded_search_remaining.json":
        return {}
```

Render: branch the refuse `div` on `d.coverage_gap`.

`/api/lots`: `"coverage_gap": (d.coverage_gap.value if d else "")`.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_bid_mechanics.py tests/test_elective_quantity.py tests/test_labor.py tests/test_gate.py tests/test_server.py tests/test_docs_match_the_sheet.py -q --tb=short`

Expected: PASS. Update README/DEVPOST collected count if the suite grew (badge `Unit%20Tests-N` and `{N} collected`).

- [ ] **Step 5: Commit** (skip if no-commit policy)

```bash
git add src/bidmath/__init__.py src/gate/render.py src/server.py src/assemble/grounded.py tests
git commit -m "feat: empty-dollar coverage reasons; sidecar cannot overlay"
```

---

### Task 8: `worth_appraising` is not a gate

**Files:**
- Modify: `scripts/run_vertex_pipeline.py` (`select_appraisal_candidates`)
- Modify: `scripts/dry_run_single_photo.py`
- Modify: `tests/test_corpus.py`

**Interfaces:**
- Consumes: existing `select_appraisal_candidates(triage_results, photos, always_include)`
- Produces: a photo with `worth_appraising=false` is still a candidate; `always_include` becomes unnecessary for this purpose but may remain as a no-op override

- [ ] **Step 1: Write the failing test**

Change `tests/test_corpus.py`:

```python
    def test_a_photo_triage_rejected_is_still_appraised(self):
        got = select_appraisal_candidates(
            [triaged("p1", worth=False)], [photo(1, "p1")], always_include=set())
        assert [c["lot_id"] for c in got] == ["BT-001"]
```

Delete or rewrite `test_a_photo_triage_rejected_is_skipped` — it is the funnel this spec kills. Keep `test_an_owner_selected_lot_is_appraised_even_if_triage_rejected_it` (still true, now redundant).

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_corpus.py::TestSelection::test_a_photo_triage_rejected_is_still_appraised -q --tb=short`

Expected: FAIL — `got == []`

- [ ] **Step 3: Write minimal implementation**

In `select_appraisal_candidates`, remove:

```python
        if verdict is not None and not verdict.get("worth_appraising", True):
            if lot_id not in always_include:
                continue
```

Leave the field on `TRIAGE_SCHEMA` (the model may still emit it). It must not decide coverage.

In `scripts/dry_run_single_photo.py`, remove the `[STOP] worth_appraising=false` production-behaviour exit. Log a note and continue.

- [ ] **Step 4: Run tests**

Run: `.venv/bin/python -m pytest tests/test_corpus.py tests/test_engine.py -q --tb=short`

Expected: PASS

- [ ] **Step 5: Commit** (skip if no-commit policy)

```bash
git add scripts/run_vertex_pipeline.py scripts/dry_run_single_photo.py tests/test_corpus.py
git commit -m "feat: worth_appraising no longer drops photos from appraisal"
```

---

### Task 9: Full suite + docs count

**Files:**
- Modify: `README.md`, `docs/DEVPOST.md` only if `test_docs_match_the_sheet.py` requires the collected count

- [ ] **Step 1: Run the full suite**

Run: `.venv/bin/python -m pytest tests/ -q --tb=line`

Expected: 0 failures. Sent-sheet tests still 9 / $275. `committed_all_in <= 600`. Sidecar not in `load_grounded_prices()`.

- [ ] **Step 2: If docs tests fail on collected count, update badge and DEVPOST `{N} collected` only**

- [ ] **Step 3: Re-run docs tests**

Run: `.venv/bin/python -m pytest tests/test_docs_match_the_sheet.py tests/test_sheet_matches_what_was_sent.py -q --tb=short`

Expected: PASS

- [ ] **Step 4: Commit docs count if it changed** (skip if no-commit policy)

---

## Spec coverage

| Spec § | Task |
|---|---|
| No photo drop, unmatched singleton | 1 |
| Must-link / cannot-link = caption numbers | 2 |
| Walk + reshoot are proposals | 3 |
| Split mixed except must-link | 3 |
| Membership stop, cap 3, not identity text | 3 |
| Re-identify from cached views, no GET / embed | 4 |
| Assemble one lot per cluster | 4 |
| Valuation B, no invented price | 5 (keeps empty dollar) |
| Fit last; number on SKIP | 5–6 |
| allocate SKIP guard | 6 |
| Empty-dollar copy / API coverage_gap | 7 |
| Sidecar hold | 7 |
| No worth_appraising gate | 8 |
| Sent email closed | 4, 9 |
| No overlay this slice | 7, 9 (explicit) |
| No agents, no COLMAP | Global; no task adds them |
| Labor tags, $600 cap | Untouched; 9 verifies |

Out of spec on purpose: sidecar overlay, `MAX_SPREAD_RATIO` change, 14-day velocity, fourth 3.6 synthesis call.
