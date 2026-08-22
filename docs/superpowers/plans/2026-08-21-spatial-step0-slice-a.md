# Spatial Step 0 Slice A Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge return-pass close-ups (seq 2 + seq 181) into one lot/one seat with 1–n thumbs before appraisal, put unplaced lots on a holding strip, and never invent barn-zone inventory.

**Architecture:** Pure functions in `src/intake/spatial.py` (cosine, scoped `nearest_neighbor`, `reshoot_edges`, `merge_reshoots`, `Seat`). Optional JSON embedding cache is read-only on `GET /`. Walk grouping stays `apply_trajectory` / `group_into_lots`. Console renders ordered seat rows; `Zone.UNKNOWN` is the holding strip. Bidmath is not touched; `len(photo_ids)` is not `unit_count`.

**Tech Stack:** Python 3.14, pytest, existing FastAPI console, no new dependencies. Vertex embed is a developer script only.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-21-spatial-step0-slice-a-design.md`
- Do not modify `src/bidmath/`
- Cloud Run `GET /` never calls `embed_content`
- `SANITY_FLOOR = 0.80` is a veto, not a 180-vs-181 discriminator
- Walk-adjacent means `|Δsequence| == 1`; exclude those **before** argmax
- CI uses small fixture vectors, not Vertex, not a 462-vector dump
- Console stays self-contained: no `src=` / `href=` (existing `test_is_self_contained`). Seat “thumbs” are seq chips, not `<img>`
- Gallery ids: seq 2 = `838421481`, seq 180 = `838424264`, seq 181 = `838424282`, seq 87 = `838422448`

## File map

- Modify: `src/intake/spatial.py` — nn, edges, merge, Seat
- Modify: `src/intake/__init__.py` — exports
- Create: `src/intake/embed.py` — read-only cache load (seq keys → photo_id)
- Modify: `src/assemble/__init__.py` — `merge_reshoots` after `group_into_lots`
- Modify: `src/gate/render.py` — seats, holding strip, strip fake island copy
- Modify: `src/server.py` — load cache, pass edges, pass seats
- Modify: `scripts/run_vertex_pipeline.py` — merge groups before pricing
- Create: `scripts/list_reshoot_edges.py` — eyeball dump, not CI
- Create: `tests/test_reshoot.py`
- Modify: `tests/test_gate.py` — occupancy / fake inventory
- Modify: `tests/test_assemble.py` — merge + unit_count unchanged

---

### Task 1: Scoped nearest neighbor and reshoot edges

**Files:**
- Modify: `src/intake/spatial.py`
- Modify: `src/intake/__init__.py`
- Test: `tests/test_reshoot.py`

**Interfaces:**
- Produces: `SANITY_FLOOR: float`, `cosine(a, b) -> float`, `nearest_neighbor(photo_id, vectors, sequences, *, exclude_walk_adjacent=True) -> str | None`, `reshoot_edges(vectors, sequences) -> set[frozenset[str, str]]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_reshoot.py`:

```python
from src.intake.spatial import nearest_neighbor, reshoot_edges, SANITY_FLOOR

P2, P180, P181, P87 = "838421481", "838424264", "838424282", "838422448"
SEQ = {P2: 2, P180: 180, P181: 181, P87: 87}


def _vectors():
    """181 is closer to walk-adjacent 180 than to 2; 2 is still 181's
    non-adjacent best; 87 is far. Cosine is dot of these raw tuples
    after the implementation L2-normalizes (or equivalent)."""
    return {
        P181: (1.0, 0.0, 0.0),
        P180: (0.999, 0.0448, 0.0),   # ~0.999 with 181
        P2:   (0.906, 0.4232, 0.0),   # ~0.906 with 181; less than 180
        P87:  (0.0, 0.0, 1.0),
    }


class TestScopedNn:
    def test_over_all_photos_181_nearest_is_walk_adjacent_180(self):
        assert nearest_neighbor(
            P181, _vectors(), SEQ, exclude_walk_adjacent=False) == P180

    def test_scoped_nn_181_is_2(self):
        assert nearest_neighbor(P181, _vectors(), SEQ) == P2

    def test_scoped_nn_2_is_181(self):
        assert nearest_neighbor(P2, _vectors(), SEQ) == P181


class TestReshootEdges:
    def test_2_and_181_are_an_edge(self):
        assert frozenset({P2, P181}) in reshoot_edges(_vectors(), SEQ)

    def test_2_and_180_are_not_an_edge(self):
        assert frozenset({P2, P180}) not in reshoot_edges(_vectors(), SEQ)

    def test_2_and_87_are_not_an_edge(self):
        assert frozenset({P2, P87}) not in reshoot_edges(_vectors(), SEQ)

    def test_walk_adjacent_never_an_edge_even_if_closest(self):
        assert frozenset({P180, P181}) not in reshoot_edges(_vectors(), SEQ)

    def test_sanity_floor_vetoes_weak_mutual_pair(self):
        from src.intake.spatial import cosine
        weak = {"a": (1.0, 0.0), "b": (0.70, 0.71414)}
        seq = {"a": 1, "b": 50}
        assert cosine(weak["a"], weak["b"]) < SANITY_FLOOR
        assert reshoot_edges(weak, seq) == set()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_reshoot.py -v`
Expected: FAIL with `ImportError` or `nearest_neighbor` not defined.

- [ ] **Step 3: Minimal implementation**

Append to `src/intake/spatial.py` (keep existing types). `SANITY_FLOOR = 0.80`.

```python
SANITY_FLOOR = 0.80


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _walk_adjacent(i: str, j: str, sequences: dict[str, int]) -> bool:
    return abs(sequences[i] - sequences[j]) == 1


def nearest_neighbor(
    photo_id: str,
    vectors: dict[str, tuple | list],
    sequences: dict[str, int],
    *,
    exclude_walk_adjacent: bool = True,
) -> str | None:
    best_id, best, tied = None, None, False
    for other, vec in vectors.items():
        if other == photo_id:
            continue
        if exclude_walk_adjacent and _walk_adjacent(photo_id, other, sequences):
            continue
        c = cosine(vectors[photo_id], vec)
        if best is None or c > best:
            best_id, best, tied = other, c, False
        elif c == best:
            tied = True
    if tied or best is None:
        return None
    return best_id


def reshoot_edges(
    vectors: dict[str, tuple | list],
    sequences: dict[str, int],
) -> set[frozenset[str]]:
    edges: set[frozenset[str]] = set()
    for i in vectors:
        j = nearest_neighbor(i, vectors, sequences)
        if j is None:
            continue
        if nearest_neighbor(j, vectors, sequences) != i:
            continue
        if cosine(vectors[i], vectors[j]) < SANITY_FLOOR:
            continue
        edges.add(frozenset({i, j}))
    return edges
```

Export the new names from `src/intake/__init__.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_reshoot.py -v`
Expected: PASS. If `cosine(P181, P2)` fixture is too low, nudge P2 until scoped tests pass without making `nn(181)` over-all equal 2.

- [ ] **Step 5: Commit**

```bash
git add src/intake/spatial.py src/intake/__init__.py tests/test_reshoot.py
git commit -m "feat(intake): mutual top-1 reshoot edges, walk-adjacent excluded first"
```

---

### Task 2: merge_reshoots

**Files:**
- Modify: `src/intake/spatial.py`
- Modify: `src/intake/__init__.py`
- Test: `tests/test_reshoot.py`

**Interfaces:**
- Consumes: `LotGroup` from `src.intake.manifest`, edges from Task 1
- Produces: `merge_reshoots(groups: list[LotGroup], edges) -> list[LotGroup]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_reshoot.py`:

```python
from src.intake.manifest import LotGroup
from src.intake.spatial import merge_reshoots
from src.bidmath import BidMechanic, CompEstimate, Confidence, Lot


class TestMergeReshoots:
    def test_unions_2_and_181_keeps_180_and_87_out(self):
        g2 = LotGroup(lot_key="BT-002", photo_ids=(P2,))
        g180 = LotGroup(lot_key="BT-180", photo_ids=(P180,))
        g181 = LotGroup(lot_key="BT-181", photo_ids=(P181,))
        g87 = LotGroup(lot_key="BT-087", photo_ids=(P87,))
        edges = {frozenset({P2, P181})}
        out = merge_reshoots([g2, g180, g181, g87], edges)
        merged = next(g for g in out if P2 in g.photo_ids)
        assert P181 in merged.photo_ids
        assert merged.photo_ids[0] == P2
        assert merged.lot_key == "BT-002"
        assert len(merged.photo_ids) == 2
        assert all(P180 not in g.photo_ids or g is merged for g in out)
        keys = {g.lot_key for g in out}
        assert "BT-180" in keys and "BT-087" in keys
        assert "BT-181" not in keys

    def test_photo_id_count_is_not_unit_count(self):
        lot = Lot(
            lot_id="BT-002", caption="trays", category="jewelry",
            fit_score=0.9, condition_penalty=0.0,
            comp=CompEstimate(65, 75, 3, Confidence.HIGH),
            mechanic=BidMechanic.TIMES_THE_MONEY,
            unit_count=3, units_wanted=3,
        )
        photo_ids = (P2, P181)
        assert len(photo_ids) == 2
        assert lot.unit_count == 3
        assert lot.unit_count != len(photo_ids)
```

- [ ] **Step 2: Run to verify fail**

Run: `.venv/bin/python -m pytest tests/test_reshoot.py::TestMergeReshoots -v`
Expected: FAIL `merge_reshoots` not defined.

- [ ] **Step 3: Minimal implementation**

In `src/intake/spatial.py`:

```python
from src.intake.manifest import LotGroup


def merge_reshoots(
    groups: list[LotGroup],
    edges: set[frozenset[str]],
) -> list[LotGroup]:
    parent = {id(g): g for g in groups}

    def group_of(photo_id: str) -> LotGroup | None:
        for g in groups:
            if photo_id in g.photo_ids:
                return g
        return None

    unions: dict[LotGroup, LotGroup] = {g: g for g in groups}

    def find(g: LotGroup) -> LotGroup:
        while unions[g] is not g:
            unions[g] = unions[unions[g]]
            g = unions[g]
        return g

    for edge in edges:
        a, b = tuple(edge)
        ga, gb = group_of(a), group_of(b)
        if ga is None or gb is None:
            continue
        ra, rb = find(ga), find(gb)
        if ra is rb:
            continue
        earlier, later = (ra, rb) if ra.lot_key <= rb.lot_key else (rb, ra)
        unions[later] = earlier

    buckets: dict[LotGroup, list[str]] = {}
    order: list[LotGroup] = []
    for g in groups:
        root = find(g)
        if root not in buckets:
            buckets[root] = []
            order.append(root)
        for pid in g.photo_ids:
            if pid not in buckets[root]:
                buckets[root].append(pid)
    return [
        LotGroup(lot_key=root.lot_key, photo_ids=tuple(buckets[root]))
        for root in order
    ]
```

Prefer `ra.lot_key` of the **earlier sequence** if keys are `BT-002` vs `BT-181` (string compare works: `"BT-002" < "BT-181"`). Photo order: keep first group’s ids then append new ones in encounter order (P2 first).

- [ ] **Step 4: Tests pass**

Run: `.venv/bin/python -m pytest tests/test_reshoot.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/intake/spatial.py src/intake/__init__.py tests/test_reshoot.py
git commit -m "feat(intake): merge reshoot pairs into one LotGroup"
```

---

### Task 3: Seat rows

**Files:**
- Modify: `src/intake/spatial.py`
- Test: `tests/test_reshoot.py`

**Interfaces:**
- Produces: `@dataclass Seat` with `lot_id`, `zone: Zone`, `walk_index: int`, `photo_ids: tuple[str, ...]`. `seats_from_groups(groups, sequences, zones=None) -> list[Seat]`. Unplaced zone is `Zone.UNKNOWN`.

- [ ] **Step 1: Failing tests**

```python
from src.intake.spatial import Seat, Zone, seats_from_groups


class TestSeats:
    def test_merged_group_is_one_seat_two_thumbs(self):
        g = LotGroup(lot_key="BT-002", photo_ids=(P2, P181))
        seats = seats_from_groups([g], {P2: 2, P181: 181})
        assert len(seats) == 1
        assert seats[0].photo_ids == (P2, P181)
        assert seats[0].walk_index == 2
        assert seats[0].zone is Zone.UNKNOWN

    def test_unplaced_seats_sorted_by_walk_index(self):
        groups = [
            LotGroup(lot_key="BT-087", photo_ids=(P87,)),
            LotGroup(lot_key="BT-002", photo_ids=(P2,)),
        ]
        seats = seats_from_groups(groups, {P2: 2, P87: 87})
        assert [s.lot_id for s in seats] == ["BT-002", "BT-087"]
```

- [ ] **Step 2: Run — expect fail**

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True)
class Seat:
    lot_id: str
    zone: Zone
    walk_index: int
    photo_ids: tuple[str, ...]


def seats_from_groups(
    groups: list[LotGroup],
    sequences: dict[str, int],
    zones: dict[str, Zone] | None = None,
) -> list[Seat]:
    zones = zones or {}
    seats = []
    for g in groups:
        walk = min(sequences.get(pid, 10**9) for pid in g.photo_ids)
        zone = zones.get(g.lot_key, Zone.UNKNOWN)
        seats.append(Seat(
            lot_id=g.lot_key, zone=zone, walk_index=walk,
            photo_ids=g.photo_ids,
        ))
    seats.sort(key=lambda s: s.walk_index)
    return seats
```

- [ ] **Step 4: Tests pass**

- [ ] **Step 5: Commit** `feat(intake): Seat is one lot, 1-n photo_ids, UNKNOWN is unplaced`

---

### Task 4: Console — rows, holding strip, no fake inventory

**Files:**
- Modify: `src/gate/render.py`
- Test: `tests/test_gate.py`

**Interfaces:**
- Consumes: `Seat`, `Zone` from spatial
- Produces: `CycleView.seats: list[Seat]`; `_map_block` renders per-zone rows + `#unplaced` strip; island cell must not contain the string `Topps Baseball Cards & Costume Jewelry`

- [ ] **Step 1: Failing tests** (add to `tests/test_gate.py`)

```python
from src.intake.spatial import Seat, Zone


class TestShowroomMap:
    def test_topology_title_always_renders(self):
        assert "Pole Barn Showroom Topology" in render_console(_view())

    def test_fake_island_inventory_is_gone(self):
        h = render_console(_view())
        assert "Topps Baseball Cards & Costume Jewelry" not in h

    def test_holding_strip_lists_unplaced_seats(self):
        v = _view()
        v.seats = [
            Seat(lot_id="BT-002", zone=Zone.UNKNOWN, walk_index=2,
                 photo_ids=("838421481", "838424282")),
            Seat(lot_id="BT-087", zone=Zone.UNKNOWN, walk_index=87,
                 photo_ids=("838422448",)),
        ]
        h = render_console(v)
        assert "not yet placed" in h.lower() or "unplaced" in h.lower()
        assert "BT-002" in h and "BT-087" in h
        # one seat, two thumbs
        idx = h.find("BT-002")
        chunk = h[idx:idx + 800]
        assert "838421481" in chunk and "838424282" in chunk
        assert "838422448" not in chunk

    def test_zoned_seat_sits_on_its_row_not_only_the_strip(self):
        v = _view()
        v.seats = [
            Seat(lot_id="BT-001", zone=Zone.CENTER_ISLAND_1, walk_index=1,
                 photo_ids=("p1",)),
        ]
        h = render_console(v)
        assert "BT-001" in h
```

Remove or replace the old `test_occupancy_tags_named_lots_on_the_map` that sets `zone_occupancy`.

- [ ] **Step 2: Run — expect fail** on fake inventory still in `_map_block` and missing `seats`.

- [ ] **Step 3: Implement**

In `CycleView` add `seats: list = field(default_factory=list)` (type `list[Seat]`). Keep `zone_occupancy` unused or delete if tests allow.

Replace `_zone_lots` / island copy with row renderer:

```python
def _seq_chip(photo_id: str) -> str:
    return f'<span class="thumb">{escape(photo_id[-7:])}</span>'


def _seat_html(s) -> str:
    thumbs = "".join(_seq_chip(p) for p in s.photo_ids)
    return (
        f'<div class="seat"><b>{escape(s.lot_id)}</b>{thumbs}</div>'
    )


def _row_for(v, zone) -> str:
    if not v:
        return ""
    seats = [s for s in v.seats if s.zone == zone]
    seats.sort(key=lambda s: s.walk_index)
    if not seats:
        return ""
    return '<div class="seat-row">' + "".join(_seat_html(s) for s in seats) + "</div>"
```

Island cell: drop the Topps/jewelry sentence; call `_row_for(v, Zone.CENTER_ISLAND_1)` etc.

After the grid, holding strip:

```python
def _holding_strip(v) -> str:
    if not v:
        return ""
    unplaced = [s for s in v.seats if s.zone is Zone.UNKNOWN]
    if not unplaced:
        return ""
    unplaced.sort(key=lambda s: s.walk_index)
    body = "".join(_seat_html(s) for s in unplaced)
    return (
        '<div class="holding" id="unplaced">'
        '<div class="map-title">Not yet placed</div>'
        f'<div class="seat-row">{body}</div></div>'
    )
```

Include `_holding_strip(v)` inside `_map_block` after the grid. Add CSS for `.seat-row`, `.seat`, `.thumb`, `.holding`. Do not add `<img src=`.

- [ ] **Step 4: `pytest tests/test_gate.py -v` PASS** (including `test_is_self_contained`)

- [ ] **Step 5: Commit** `feat(gate): barn rows and unplaced strip; drop fake island inventory`

---

### Task 5: assemble_lots applies reshoot merge

**Files:**
- Modify: `src/assemble/__init__.py`
- Test: `tests/test_assemble.py`

**Interfaces:**
- Consumes: `merge_reshoots`, `reshoot_edges` (edges passed in; assemble does not load vectors)
- Produces: `assemble_lots(..., reshoot_edges: set | None = None)`

- [ ] **Step 1: Failing test**

In `tests/test_assemble.py` add a test that two `AppraisedPhoto`s with ids P2 and P181, `same_lot_as_previous=False`, become **one** `Lot` with `lot_id` of the first key when `reshoot_edges={frozenset({P2,P181})}`. A third photo P87 stays its own lot. If you set `Lot.unit_count` in the test via comps path, it stays default 1 unless you pass mechanic — the assertion is `len(lots)==2` not `unit_count`.

Do **not** set `unit_count=len(photo_ids)` anywhere in assemble.

- [ ] **Step 2: Run — fail** (extra kwarg or still two lots)

- [ ] **Step 3: After `group_into_lots`, if edges: `groups = merge_reshoots(groups, reshoot_edges)`**

- [ ] **Step 4: Tests pass** (`tests/test_assemble.py tests/test_reshoot.py`)

- [ ] **Step 5: Commit** `feat(assemble): union reshoot pairs before Lot construction`

---

### Task 6: Wire console and pipeline (read-only cache)

**Files:**
- Create: `src/intake/embed.py`
- Modify: `src/server.py`
- Modify: `scripts/run_vertex_pipeline.py`
- Test: `tests/test_embed_cache.py` (cache missing + seq-key ingest)

**Interfaces:**
- Produces: `load_vectors(cache_path, photo_by_seq: dict[int, str]) -> dict[str, list[float]]`. Missing file → `{}`. Seq-keyed JSON `{ "2": [..], "181": [..] }` maps through `photo_by_seq`. Photo-id-keyed JSON used as-is.

- [ ] **Step 1: Tests for load_vectors**

```python
def test_missing_cache_is_empty(tmp_path):
    from src.intake.embed import load_vectors
    assert load_vectors(tmp_path / "nope.json", {2: P2}) == {}

def test_seq_keys_translate_to_photo_ids(tmp_path):
    from src.intake.embed import load_vectors
    p = tmp_path / "e.json"
    p.write_text('{"2": [1,0], "181": [0,1]}')
    v = load_vectors(p, {2: P2, 181: P181})
    assert set(v) == {P2, P181}
```

- [ ] **Step 2: Fail then implement `load_vectors`** — `json.loads`, if a key.isdigit() use `photo_by_seq[int(k)]`. Never call Vertex.

- [ ] **Step 3: Pipeline** — after `lot_groups = group_into_lots(...)`:

```python
cache = Path(data_dir) / "embeddings.json"
photo_by_seq = {p["sequence"]: p["photo_id"] for p in photos}
sequences = {p["photo_id"]: p["sequence"] for p in photos}
vectors = load_vectors(cache, photo_by_seq)
edges = reshoot_edges(vectors, sequences) if vectors else set()
lot_groups = merge_reshoots(lot_groups, edges)
```

Do not change `unit_count` assignment. Existing `BT-181` operator decline stays as belt.

- [ ] **Step 4: Server `get_aug22_state`** — build `sequences` from manifest; `load_vectors`; `reshoot_edges`; pass edges into `assemble_lots`. Build `seats_from_groups` from the merged groups (map lot_key / photo_ids). Pass `seats=` into `CycleView`. If server still uses `BT-00N` as `AppraisedPhoto.photo_id`, key vectors and sequences with those same strings (`f"BT-{seq:03d}"`) so merge keys match. **One key space per process.** Prefer gallery `photo_id` if you change the server to carry it; do not mix.

- [ ] **Step 5: `pytest tests/test_embed_cache.py tests/test_server.py tests/test_gate.py tests/test_assemble.py tests/test_reshoot.py -q` PASS**

- [ ] **Step 6: Commit** `feat(intake): load embedding cache without Vertex; wire merge on console and pipeline`

---

### Task 7: Eyeball script (not CI)

**Files:**
- Create: `scripts/list_reshoot_edges.py`

**Interfaces:**
- Consumes: `load_vectors`, `reshoot_edges`, manifest
- Produces: stdout lines `seq_a seq_b gap cosine photo_a photo_b` sorted by gap descending

- [ ] **Step 1: Script** that exits 0 on missing cache with a one-line message. No pytest. Does not write a sheet.

```python
"""Dump every Slice A reshoot edge. Not CI. Eyeball before a live sheet."""
# load manifest + embeddings.json from data/aug22_gallery_4160518/
# print edges; mention SANITY_FLOOR and scoped nn in the header
```

- [ ] **Step 2: Run against missing cache — expect the one-line miss, exit 0**

- [ ] **Step 3: Commit** `chore(intake): list_reshoot_edges for one human pass over the 76`

---

## Spec coverage

| Spec | Task |
|---|---|
| scoped nn, mutual #1, sanity 0.80 | 1 |
| 2↔181 yes, 2↔180 no, 2↔87 no, nn(181)==2 | 1 |
| merge_reshoots matching, lot_key earlier, photo_ids 1–n | 2 |
| len(photo_ids) ≠ unit_count | 2 |
| Seat, UNKNOWN = unplaced, walk_index | 3 |
| barn rows, holding strip, no fake Topps | 4 |
| assemble merge before Lot | 5 |
| GET / never embeds; missing cache walk-only | 6 |
| seq-keyed cache ingest | 6 |
| eyeball dump of all edges | 7 |
| Slice B listing windows | **out of plan** |
| bidmath | **out of plan** |
