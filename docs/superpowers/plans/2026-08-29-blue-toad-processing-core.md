# Blue Toad processing core (`src/blue_toad`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land a provider-independent processing core under `src/blue_toad/` whose puzzle loop assigns every photo exactly once, imports none of the live runners/UI/money stack, and leaves tomorrow's judged surfaces unchanged.

**Architecture:** New package `src/blue_toad/processing/` owns the spec types and the puzzle loop. `src/intake/puzzle.py` becomes a thin adapter so `tests/test_puzzle.py`, `src/server.py`, and the F21 runner keep their current imports and behavior. Old paths are not deleted. D2 acquisition, D4 sold-comp valuation, D1 binary eviction, and D7 history rewrite are out of this plan.

**Tech Stack:** Python 3.14, pytest, stdlib dataclasses only. No new dependencies. No Vertex, COLMAP, FAISS, OpenCV, Firestore, FastAPI, or OpenPyXL inside `src/blue_toad/`.

**Spec:** `docs/DISTILLATION_SPEC.md` sections 3 (target runtime), 3.2 (puzzle contracts), 5 (keep/move/remove), D3 (uniform puzzle engine). Puzzle behavior already proven in `src/intake/puzzle.py` and `tests/test_puzzle.py`; this plan relocates that contract into the distilled core.

## Global Constraints

- Do not modify `src/bidmath/`, `mechanic_from_ruling`, `clerk_directive`, or greedy `allocate`.
- Do not modify `scripts/run_vertex_pipeline.py` (F21 just landed on origin; captain/pipeline lane owns it).
- Do not modify `src/gate/walkstrip.py`.
- Sent sheet stays 9 / $275.00 / $316.25: `tests/test_sheet_matches_what_was_sent.py` must stay green.
- `get_aug22_state(sheet="sent")` and `sheet="full"` money must not change.
- Budget cap stays `$600.00` all-in; do not introduce 1000.
- Cloud Run `GET /` never calls Vertex embed or Google Search from this package.
- `src/blue_toad/` MUST NOT import `scripts`, `src.server`, `src.gate`, `src.memory`, or `src.bidmath`.
- Processing MUST NOT contain a `worth_appraising` gate or drop unmatched photos; unmatched → singleton.
- Caption lot numbers are must/cannot-link; walk/reshoot edges are proposals.
- `_merge_clusters` iterates `sorted(edges, key=lambda e: tuple(sorted(e)))`.
- Loop cap is 3 rounds (`max_rounds=3`).
- TDD: failing test first on every task. Watch it fail before writing production code.
- Work on branch `feat/blue-toad-core` forked from current `origin/master`. Do not merge or push unless the operator asks.
- Do not delete `src/intake/puzzle.py`; replace its body with an adapter only in Task 6.
- No package rename of the rest of the repo.

## File map

- Create: `src/blue_toad/__init__.py`
- Create: `src/blue_toad/processing/__init__.py`
- Create: `src/blue_toad/processing/models.py` — `PhotoPiece`, `Observation`, `MatchEdge`, `ItemCluster`, `PuzzleState`
- Create: `src/blue_toad/processing/constraints.py` — `lot_number_from`, `cannot_link`, `seed_clusters`, caption must-pairs
- Create: `src/blue_toad/processing/puzzle.py` — `puzzle_loop`, merge/split, 100% assignment
- Create: `src/blue_toad/processing/image.py` — decode-free SHA-256 + size/MIME guards
- Create: `src/blue_toad/processing/pipeline.py` — pieces + proposal edges → `PuzzleState`
- Create: `tests/core/__init__.py`
- Create: `tests/core/test_import_boundary.py`
- Create: `tests/core/test_models.py`
- Create: `tests/core/test_constraints.py`
- Create: `tests/core/test_puzzle.py`
- Create: `tests/core/test_image.py`
- Create: `tests/core/test_pipeline.py`
- Modify: `src/intake/puzzle.py` — adapter only (Task 6)
- Do not modify: `tests/test_puzzle.py` (it must keep passing via the adapter)

---

### Task 1: Package and import fence

**Files:**
- Create: `src/blue_toad/__init__.py`
- Create: `src/blue_toad/processing/__init__.py`
- Create: `tests/core/__init__.py`
- Create: `tests/core/test_import_boundary.py`

**Interfaces:**
- Consumes: nothing
- Produces: package `src.blue_toad.processing` importable; a pytest that fails if any file under `src/blue_toad/` contains an import of `scripts`, `src.server`, `src.gate`, `src.memory`, or `src.bidmath`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_import_boundary.py
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "src" / "blue_toad"
FORBIDDEN_PREFIXES = (
    "scripts",
    "src.server",
    "src.gate",
    "src.memory",
    "src.bidmath",
)


def _imported_modules(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    return names


def test_processing_core_does_not_import_runners_ui_memory_or_bidmath():
    py_files = sorted(CORE.rglob("*.py"))
    assert py_files, f"expected a src/blue_toad package at {CORE}"
    violations: list[str] = []
    for path in py_files:
        for name in _imported_modules(path):
            if name == "scripts" or name.startswith("scripts."):
                violations.append(f"{path.relative_to(ROOT)} imports {name}")
            for prefix in FORBIDDEN_PREFIXES:
                if name == prefix or name.startswith(prefix + "."):
                    violations.append(f"{path.relative_to(ROOT)} imports {name}")
    assert violations == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_import_boundary.py -q --tb=short`

Expected: FAIL with `expected a src/blue_toad package` (directory missing) or collection error because `tests/core` has no package yet — the assertion `assert py_files` is the intended failure once the test file collects.

- [ ] **Step 3: Write minimal implementation**

```python
# src/blue_toad/__init__.py
"""Provider-independent Blue Toad processing core. Optional adapters live outside this package."""

# src/blue_toad/processing/__init__.py
"""Puzzle / observation / valuation core. No runner, Gate, memory, or bidmath imports."""

# tests/core/__init__.py
# empty
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_import_boundary.py -q --tb=short`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/blue_toad/__init__.py src/blue_toad/processing/__init__.py tests/core/__init__.py tests/core/test_import_boundary.py
git commit -m "feat(core): import fence for src/blue_toad processing package"
```

---

### Task 2: Spec models

**Files:**
- Create: `src/blue_toad/processing/models.py`
- Modify: `src/blue_toad/processing/__init__.py` — export the five types
- Create: `tests/core/test_models.py`

**Interfaces:**
- Consumes: Task 1 package
- Produces: frozen dataclasses `PhotoPiece`, `Observation`, `MatchEdge`, `ItemCluster`, `PuzzleState` with the spec field names in `docs/DISTILLATION_SPEC.md` §3.2

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_models.py
from src.blue_toad.processing.models import (
    ItemCluster,
    MatchEdge,
    Observation,
    PhotoPiece,
    PuzzleState,
)


def test_photo_piece_is_frozen_and_carries_source_identity():
    piece = PhotoPiece(
        photo_id="p1",
        cycle_id="2026-08-22",
        sequence=1,
        caption="Lot 47 truck",
        source_object="input/images/p1.jpg",
        source_generation="1",
        image_sha256="abc",
    )
    assert piece.photo_id == "p1"
    try:
        piece.caption = "nope"
    except Exception:
        return
    raise AssertionError("PhotoPiece must be frozen")


def test_match_edge_relations_are_the_spec_set():
    edge = MatchEdge(
        photo_a="a",
        photo_b="b",
        relation="same_lot",
        score=0.9,
        evidence=("walk",),
        iteration=1,
    )
    assert edge.relation in {"same_item", "same_lot", "spatial_neighbor", "incompatible"}


def test_puzzle_state_complete_requires_full_assignment_fields():
    cluster = ItemCluster(
        cluster_id="seq:a",
        member_photo_ids=("a",),
        identity="",
        sale_unit="unknown",
        conflicts=(),
        confidence=0.0,
        revision=1,
    )
    state = PuzzleState(
        cycle_id="c1",
        iteration=1,
        assigned_photo_count=1,
        total_photo_count=1,
        clusters=(cluster,),
        changed_edges=0,
        merges=0,
        splits=0,
        identity_changes=0,
        stable_passes=1,
        complete=True,
    )
    assert state.complete is True
    assert state.assigned_photo_count == state.total_photo_count
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_models.py -q --tb=short`

Expected: FAIL — `ModuleNotFoundError` / `ImportError` for `src.blue_toad.processing.models`

- [ ] **Step 3: Write minimal implementation**

```python
# src/blue_toad/processing/models.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Relation = Literal["same_item", "same_lot", "spatial_neighbor", "incompatible"]


@dataclass(frozen=True)
class PhotoPiece:
    photo_id: str
    cycle_id: str
    sequence: int
    caption: str
    source_object: str
    source_generation: str
    image_sha256: str


@dataclass(frozen=True)
class Observation:
    photo_id: str
    detected_objects: tuple[str, ...]
    visible_text: tuple[str, ...]
    visual_embedding: tuple[float, ...]
    scene_features: tuple[str, ...]
    viewpoint: str
    visible_marks: tuple[str, ...]
    visible_condition: tuple[str, ...]


@dataclass(frozen=True)
class MatchEdge:
    photo_a: str
    photo_b: str
    relation: Relation
    score: float
    evidence: tuple[str, ...]
    iteration: int


@dataclass(frozen=True)
class ItemCluster:
    cluster_id: str
    member_photo_ids: tuple[str, ...]
    identity: str
    sale_unit: str
    conflicts: tuple[str, ...]
    confidence: float
    revision: int


@dataclass(frozen=True)
class PuzzleState:
    cycle_id: str
    iteration: int
    assigned_photo_count: int
    total_photo_count: int
    clusters: tuple[ItemCluster, ...]
    changed_edges: int
    merges: int
    splits: int
    identity_changes: int
    stable_passes: int
    complete: bool
```

Export the five names from `src/blue_toad/processing/__init__.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_models.py tests/core/test_import_boundary.py -q --tb=short`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/blue_toad/processing/models.py src/blue_toad/processing/__init__.py tests/core/test_models.py
git commit -m "feat(core): PhotoPiece, Observation, MatchEdge, ItemCluster, PuzzleState"
```

---

### Task 3: Caption constraints

**Files:**
- Create: `src/blue_toad/processing/constraints.py`
- Create: `tests/core/test_constraints.py`

**Interfaces:**
- Consumes: `PhotoPiece` from Task 2
- Produces:
  - `lot_number_from(caption: str) -> str | None` using regex `(?:^|\b)(?:lot\s*#?\s*|#)(\d{1,4})\b` (same as `src/intake/manifest.py`)
  - `cannot_link(pieces: list[PhotoPiece]) -> set[frozenset[str]]`
  - `seed_clusters(pieces: list[PhotoPiece]) -> list[ItemCluster]`
  - `must_link_pairs(pieces: list[PhotoPiece]) -> set[frozenset[str]]`
- Seed rules: same caption lot number → one cluster; uncaptioned → singleton; walk flags are NOT on `PhotoPiece` and MUST NOT seed a merge.

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_constraints.py
from src.blue_toad.processing.constraints import (
    cannot_link,
    lot_number_from,
    must_link_pairs,
    seed_clusters,
)
from src.blue_toad.processing.models import PhotoPiece


def P(pid, caption="", seq=0):
    return PhotoPiece(
        photo_id=pid,
        cycle_id="c",
        sequence=seq,
        caption=caption,
        source_object=pid,
        source_generation="1",
        image_sha256=pid,
    )


def test_lot_number_from_matches_blue_toad_captions():
    assert lot_number_from("Lot 47 truck") == "47"
    assert lot_number_from("#12 glass") == "12"
    assert lot_number_from("uncaptioned extra") is None


def test_uncaptioned_photos_start_as_singletons():
    cs = seed_clusters([P("a"), P("b")])
    assert sorted(c.member_photo_ids for c in cs) == [("a",), ("b",)]


def test_same_caption_lot_number_is_must_link():
    cs = seed_clusters([
        P("a", "Lot 47 truck"),
        P("b", "Lot 12 glass"),
        P("c", "Lot 47 reverse"),
    ])
    by = {frozenset(c.member_photo_ids): c for c in cs}
    assert frozenset({"a", "c"}) in by
    assert frozenset({"b"}) in by
    assert frozenset({"a", "c"}) in must_link_pairs([
        P("a", "Lot 47 truck"),
        P("c", "Lot 47 reverse"),
    ])


def test_different_lot_numbers_are_cannot_link():
    pieces = [P("a", "Lot 47 truck"), P("b", "Lot 48 trumpet")]
    assert frozenset({"a", "b"}) in cannot_link(pieces)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_constraints.py -q --tb=short`

Expected: FAIL — `ImportError` for `src.blue_toad.processing.constraints`

- [ ] **Step 3: Write minimal implementation**

Port the seed/cannot/must logic from `src/intake/puzzle.py` onto `PhotoPiece` / `ItemCluster`. Copy the `_LOT_NO` regex verbatim. `ItemCluster` fields not yet known stay `identity=""`, `sale_unit="unknown"`, `conflicts=()`, `confidence=0.0`, `revision=1`. Uncaptioned cluster_id is `f"seq:{pid}"`. Numbered cluster_id is the lot number string.

Do **not** import `src.intake`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_constraints.py tests/core/test_import_boundary.py -q --tb=short`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/blue_toad/processing/constraints.py tests/core/test_constraints.py
git commit -m "feat(core): caption must-link and cannot-link constraints"
```

---

### Task 4: Puzzle loop

**Files:**
- Create: `src/blue_toad/processing/puzzle.py`
- Create: `tests/core/test_puzzle.py`

**Interfaces:**
- Consumes: `PhotoPiece`, `ItemCluster`, `PuzzleState`, `cannot_link`, `seed_clusters`, `must_link_pairs`
- Produces:
  - `GENERIC_CATEGORIES = frozenset({"other", "unsorted", "general estate", ""})`
  - `identities_mixed(members: list[tuple[str, str]]) -> bool`
  - `puzzle_loop(pieces: list[PhotoPiece], *, proposal_edges: set[frozenset[str]], identify: Callable[[tuple[str, ...]], dict[str, tuple[str, str]]], max_rounds: int = 3) -> PuzzleState`
- Loop rules (must match live `src/intake/puzzle.py`):
  - every piece assigned exactly once; unmatched is a singleton cluster
  - proposal edges merge unless cannot-link
  - mixed non-generic categories split unless must-link covers all members
  - merge iterates `sorted(edges, key=lambda e: tuple(sorted(e)))`
  - `complete` is True iff `assigned_photo_count == total_photo_count` and membership is a partition of the input photo ids
  - identify is called at most `max_rounds` membership-change cycles; cap 3

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_puzzle.py
from src.blue_toad.processing.constraints import seed_clusters
from src.blue_toad.processing.models import PhotoPiece
from src.blue_toad.processing.puzzle import identities_mixed, puzzle_loop


def P(pid, caption="", seq=0):
    return PhotoPiece(
        photo_id=pid, cycle_id="c", sequence=seq, caption=caption,
        source_object=pid, source_generation="1", image_sha256=pid,
    )


def test_unmatched_photo_is_a_singleton_and_complete():
    state = puzzle_loop(
        [P("a"), P("b")],
        proposal_edges=set(),
        identify=lambda ids: {pid: ("x", "other") for pid in ids},
    )
    assert state.complete is True
    assert state.assigned_photo_count == 2
    assert state.total_photo_count == 2
    assert sorted(c.member_photo_ids for c in state.clusters) == [("a",), ("b",)]


def test_proposal_merges_then_stops():
    calls = []

    def identify(ids):
        calls.append(ids)
        return {pid: ("truck", "vintage toys") for pid in ids}

    state = puzzle_loop(
        [P("a", seq=1), P("b", seq=2)],
        proposal_edges={frozenset({"a", "b"})},
        identify=identify,
    )
    assert [c.member_photo_ids for c in state.clusters] == [("a", "b")]
    assert len(calls) <= 3


def test_mixed_unconstrained_photos_split():
    ids = {
        "a": ("costume jewelry", "jewelry"),
        "b": ("Edison cylinders", "phonograph / records"),
    }
    state = puzzle_loop(
        [P("a"), P("b")],
        proposal_edges={frozenset({"a", "b"})},
        identify=lambda pids: {p: ids[p] for p in pids},
    )
    assert sorted(c.member_photo_ids for c in state.clusters) == [("a",), ("b",)]


def test_cannot_link_blocks_a_proposal():
    state = puzzle_loop(
        [P("a", "Lot 47 truck"), P("b", "Lot 48 trumpet")],
        proposal_edges={frozenset({"a", "b"})},
        identify=lambda ids: {pid: ("x", "other") for pid in ids},
    )
    assert sorted(c.member_photo_ids for c in state.clusters) == [("a",), ("b",)]


def test_sorted_edges_make_the_uncaptioned_bridge_deterministic():
    """Uncaptioned B between Lot 1 and Lot 2: first sorted edge wins."""
    pieces = [
        P("A", "Lot 1 glass", seq=1),
        P("B", "", seq=2),
        P("C", "Lot 2 tray", seq=3),
    ]
    state = puzzle_loop(
        pieces,
        proposal_edges={frozenset({"A", "B"}), frozenset({"B", "C"})},
        identify=lambda ids: {pid: ("x", "other") for pid in ids},
    )
    groups = sorted(tuple(sorted(c.member_photo_ids)) for c in state.clusters)
    assert groups == [("A", "B"), ("C",)]


def test_jewelry_vs_edison_is_mixed():
    assert identities_mixed([
        ("costume jewelry tray", "jewelry"),
        ("Edison cylinder records", "phonograph / records"),
    ]) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_puzzle.py -q --tb=short`

Expected: FAIL — `ImportError` for `src.blue_toad.processing.puzzle`

- [ ] **Step 3: Write minimal implementation**

Port `identities_mixed`, `split_cluster`, `_merge_clusters` (sorted edges), and `puzzle_loop` from `src/intake/puzzle.py` onto `PhotoPiece` / `ItemCluster` / `PuzzleState`. Return `PuzzleState` with `complete=(assigned==total)` and clusters covering every input photo_id exactly once. `cycle_id` comes from `pieces[0].cycle_id` if pieces else `""`.

Do **not** import `src.intake` or `LotGroup`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_puzzle.py tests/core/test_constraints.py tests/core/test_import_boundary.py -q --tb=short`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/blue_toad/processing/puzzle.py tests/core/test_puzzle.py
git commit -m "feat(core): puzzle loop assigns every photo exactly once"
```

---

### Task 5: Image identity helper

**Files:**
- Create: `src/blue_toad/processing/image.py`
- Create: `tests/core/test_image.py`

**Interfaces:**
- Consumes: nothing outside stdlib
- Produces: `sha256_bytes(data: bytes) -> str` (hex); `validate_image_bytes(data: bytes, *, min_bytes: int = 32, max_bytes: int = 40_000_000) -> str` returns the sha256 if `min_bytes <= len(data) <= max_bytes`, else raises `ValueError`. No PIL/OpenCV decode in this task (byte identity only, per spec `image.py` comment "byte validation and hashing only").

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_image.py
import pytest
from src.blue_toad.processing.image import sha256_bytes, validate_image_bytes


def test_sha256_bytes_is_stable():
    assert sha256_bytes(b"hello") == sha256_bytes(b"hello")
    assert sha256_bytes(b"hello") != sha256_bytes(b"world")
    assert len(sha256_bytes(b"hello")) == 64


def test_validate_image_bytes_rejects_empty_and_returns_hash():
    with pytest.raises(ValueError):
        validate_image_bytes(b"")
    digest = validate_image_bytes(b"x" * 32)
    assert digest == sha256_bytes(b"x" * 32)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_image.py -q --tb=short`

Expected: FAIL — `ImportError` for `src.blue_toad.processing.image`

- [ ] **Step 3: Write minimal implementation**

```python
import hashlib

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def validate_image_bytes(data: bytes, *, min_bytes: int = 32, max_bytes: int = 40_000_000) -> str:
    if not min_bytes <= len(data) <= max_bytes:
        raise ValueError(f"image byte length {len(data)} outside {min_bytes}..{max_bytes}")
    return sha256_bytes(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/core/test_image.py tests/core/test_import_boundary.py -q --tb=short`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/blue_toad/processing/image.py tests/core/test_image.py
git commit -m "feat(core): image byte hashing and size guard"
```

---

### Task 6: Pipeline entry + live adapter

**Files:**
- Create: `src/blue_toad/processing/pipeline.py`
- Create: `tests/core/test_pipeline.py`
- Modify: `src/intake/puzzle.py` — keep the public functions (`cannot_link`, `seed_clusters`, `walk_proposal_edges`, `identities_mixed`, `split_cluster`, `puzzle_loop`, `as_lot_groups`, `Cluster`, `GENERIC_CATEGORIES`) with the same signatures; implement them by converting `TriagedPhoto` → `PhotoPiece` and mapping `PuzzleState.clusters` back to `Cluster(photo_ids=member_photo_ids)`
- Do not edit `tests/test_puzzle.py`

**Interfaces:**
- Consumes: `puzzle_loop` from Task 4
- Produces:
  - `run_puzzle(pieces: list[PhotoPiece], *, proposal_edges: set[frozenset[str]], identify, max_rounds: int = 3) -> PuzzleState` (thin wrapper around `puzzle_loop`)
  - live adapter so existing `from src.intake.puzzle import puzzle_loop` still returns `list[Cluster]`

- [ ] **Step 1: Write the failing test**

```python
# tests/core/test_pipeline.py
from src.blue_toad.processing.models import PhotoPiece
from src.blue_toad.processing.pipeline import run_puzzle


def P(pid, caption=""):
    return PhotoPiece(
        photo_id=pid, cycle_id="c", sequence=0, caption=caption,
        source_object=pid, source_generation="1", image_sha256=pid,
    )


def test_run_puzzle_partitions_every_piece():
    state = run_puzzle(
        [P("a"), P("b"), P("c")],
        proposal_edges={frozenset({"a", "b"})},
        identify=lambda ids: {pid: ("x", "other") for pid in ids},
    )
    assigned = [pid for c in state.clusters for pid in c.member_photo_ids]
    assert sorted(assigned) == ["a", "b", "c"]
    assert state.complete is True
```

Also add to the same file (or keep using `tests/test_puzzle.py` after the adapter):

After the adapter is written, run the existing suite file:

`.venv/bin/python -m pytest tests/test_puzzle.py tests/test_sheet_matches_what_was_sent.py tests/core/ -q --tb=short`

The failing-first part of this task is `test_run_puzzle_partitions_every_piece` (pipeline missing). The adapter is green-checked by `tests/test_puzzle.py` which must not be rewritten.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/core/test_pipeline.py -q --tb=short`

Expected: FAIL — `ImportError` for `src.blue_toad.processing.pipeline`

- [ ] **Step 3: Write minimal implementation**

`run_puzzle` calls `puzzle_loop` and returns the `PuzzleState`.

Then rewrite `src/intake/puzzle.py` as an adapter:

- Keep `Cluster` as `cluster_id` + `photo_ids` (live type).
- `walk_proposal_edges` stays on `TriagedPhoto` (that flag is not on `PhotoPiece`).
- `puzzle_loop(photos, *, proposal_edges, identify, max_rounds=3)` converts each `TriagedPhoto` to `PhotoPiece(photo_id, cycle_id="aug22", sequence=0, caption=photo.caption, source_object=photo.photo_id, source_generation="0", image_sha256="")`, unions `proposal_edges` with `walk_proposal_edges(photos)`, calls `src.blue_toad.processing.puzzle.puzzle_loop`, maps each `ItemCluster` to `Cluster(cluster_id, photo_ids=member_photo_ids)`.
- `as_lot_groups` unchanged in behavior.
- `cannot_link` / `seed_clusters` may call the core after conversion, or keep a local thin wrapper; public return types stay `set[frozenset[str]]` and `list[Cluster]`.

Do not change `src/server.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/core/ tests/test_puzzle.py tests/test_sheet_matches_what_was_sent.py tests/test_walkstrip.py -q --tb=short`

Expected: PASS. Then run full suite: `.venv/bin/python -m pytest -q`

Expected: same skip count as origin baseline, 0 failures.

- [ ] **Step 5: Commit**

```bash
git add src/blue_toad/processing/pipeline.py tests/core/test_pipeline.py src/intake/puzzle.py
git commit -m "feat(core): puzzle pipeline plus live intake adapter"
```

---

## Spec coverage (self-review)

| Spec item | Task |
|---|---|
| `src/blue_toad/processing/` layout (models, image, puzzle, pipeline) | 1–6 |
| PhotoPiece / Observation / MatchEdge / ItemCluster / PuzzleState fields | 2 |
| Every photo assigned exactly once; singleton unmatched | 4 |
| Caption must/cannot; walk is proposal | 3, 4, 6 |
| Sorted merge determinism | 4 |
| Cap 3 rounds | 4 |
| Processing imports no runner/server/Gate/memory/bidmath | 1 (fence) |
| `image.py` hashing only | 5 |
| Do not delete old paths | 6 adapter |
| D2 acquisition / cloud READY | **out of plan** (follow-on) |
| D4 SoldComp valuation | **out of plan** (follow-on) |
| D1 binary eviction / D7 filter-repo | **out of plan** |
| `observe.py` / `match.py` / `identify.py` / `research.py` / `value.py` | **out of plan** — pipeline currently takes an injected `identify` callable, which is the seam those modules will fill |

## Follow-on plans (do not start in this file)

1. D2 — listing acquisition writes cloud `READY` without a permanent local gallery.
2. D4 — `SoldComp` + `value.py` with explicit evidence basis; no model-authored prices.
3. D6 — F21 runner calls `src.blue_toad.processing.pipeline.run_puzzle` instead of inlined grouping (captain/pipeline lane; not grok tonight).
