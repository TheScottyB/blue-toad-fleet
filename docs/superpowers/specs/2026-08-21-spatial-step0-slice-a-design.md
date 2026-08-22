# Spatial Step 0, Slice A — design

**Date:** 2026-08-21
**Branch:** `feat/gemma-curator-voice`
**Status:** draft for operator review; not an implementation plan

Approach **C** from the Step 0 design talk: ship Slice A on the live Aug 22
gallery, then Slice B (listing-window adjacency) as a later commit. This spec
is Slice A only. Slice B is named so we do not build the wrong shape now.

Lane: `src/intake/`, `src/spatial/`, `src/gate/render.py`, server/pipeline
wiring. Do not change `src/bidmath/`. BT-002 times-the-money (labelled trays
12/14/16, Bill’s “x3 bid”) stays Claude’s mechanic. BT-181 as a *second bid*
is this lane: it is a close-up of the same trays, not another table.

---

## 1. Goal

The console is a **virtual setup of the pole barn**, not a decorative floor
plan. Lots sit **in relation to each other**. A photo pins to a putative
place; a reshoot does not get a second place.

On Aug 22, seq 2 (`fpx2`, wide trays 12/14/16) and seq 181 (`fpx181`,
close-up of 12 and 14) are **one physical lot**. Sequence distance is 179
frames — a return pass, not a stutter at the table. Trajectory alone attached
181 to uncaptioned seq 180. Slice A must merge them **before appraisal**.

The first two-thirds of a drop are mostly a linear walk; returns, close-ups,
and late adds land far from the original. Sequence is the walk, not the whole
file.

---

## 2. What Slice A is / is not

**Is**

- Embed each photo once (`gemini-embedding-2`). Cache vectors on disk.
- Walk groups via existing `apply_trajectory`.
- Reshoot edges via embeddings (same objects, different crop/seq).
- One `LotGroup` per physical lot; `photo_ids` is 1–n.
- Appraise that group once. The close-up enriches the wide shot
  (`assemble_lots` already takes best identification / worst condition).
- Console: known barn topology; each zone is a **row of seats** in walk
  order; each seat shows **1–n thumbnails** of that lot.
- Lots with no zone go to an **unplaced holding strip**. They never vanish.

**Is not**

- Overlapping Gemini listing windows, “right edge is photo 47,” surface
  named from pixels. That is Slice B.
- Mirror / `reflection_validates` on a live photo. Slice B or later.
- dHash for this merge (rank #94 on 2↔181). dHash stays for
  AuctionZip ↔ estatesales near-dups only.
- Upscaling. Do not add an upscale stage.
- Caption-only “jewelry → island” pins. That is the fake Topps-on-island-1
  map. Named-zone pins without a pixel or walk-zone signal are out of scope.
- Bidmath, clerk email arithmetic, `mechanic_from_ruling`.
- Embedding-merge of an entire **place cluster**. Embeddings group place;
  seq 2’s nearest neighbors include the whole 176–183 pass at that case.
  Merging every neighbor swallows the rest of the table.

---

## 3. Units

### 3.1 Embedding cache

- **Does:** one 3072-d vector per photo; persist JSON keyed by `photo_id`
  plus model name. Bytes are the same local files the rest of the pipeline
  already reads (`manifest.local_path`). Do not mix AuctionZip thumbs and
  estatesales 1200×900 in one cache — that would move cosines relative to
  the 0.906 measurement. One image per `embed_content` call (a list of
  images fuses to one vector).
- **Use:** `load_or_embed(photos, cache_path) -> dict[photo_id, vector]`.
- **Depends:** Vertex client, local image bytes. **Does not** run on Cloud
  Run `GET /`. If the cache file is missing at request time, skip reshoot
  edges; do not embed 462 photos inline.

### 3.2 Reshoot edges

- **Does:** undirected edges between **non-adjacent** photos that are the
  same objects (close-up / return), not merely the same table.
- **Contract (outcomes, not a vibe):**

  | Pair | Edge? | Why |
  |---|---|---|
  | seq 2 ↔ seq 181 | yes | close-up of trays 12/14; cos 0.906; rank #1 |
  | seq 2 ↔ seq 87 | no | different jewelry bin; rank #9 |
  | consecutive uncaptioned under-table boxes | n/a | walk / trajectory, not this unit |

- **Floor:** cosine threshold **strictly below** cos(2,181) and **strictly
  above** cos(2,87), measured from the cached vectors. Record the two
  cosines and the chosen floor in the cache sidecar or a constant next to
  the tests. If a later corpus moves the numbers, the **pair outcomes**
  still hold; adjust the floor, do not weaken the tests.
- **Also require** rank: 181 is among 2’s top-3 neighbors (and vice versa
  is allowed but not required). Rank #9 (87) never qualifies.
- **Use:** `reshoot_edges(ids, vectors) -> set[frozenset[photo_id, photo_id]]`.
- **Depends:** embedding cache only.

### 3.3 Walk groups

Existing `spatial_same_lot` + `apply_trajectory` + `group_into_lots`.
Unchanged rules: same zone, uncaptioned run, model `same_lot_as_previous`
in-zone, zone change breaks the run. Two captioned lots on the same table
stay two groups.

### 3.4 Union reshoots into seats

`same_lot_as_previous` only chains to the immediately previous photo, so it
cannot attach 181 to 2. After walk grouping:

`merge_reshoots(groups, edges) -> groups`

Union-find: if an edge links a photo in group A to a photo in group B,
A and B become one `LotGroup`. `photo_ids` is walk order of the earliest
member, then remaining ids in file order. `lot_key` of the surviving group
is the earlier key (seq 2 wins over seq 181).

### 3.5 Seat

One seat is one physical lot, one place on the UI.

```
Seat
  lot_id: str
  zone: Zone | UNPLACED
  walk_index: int          # min sequence among member photos
  photo_ids: tuple[str, ...]   # 1–n, file order; first is establishing shot
```

Slice A: `zone` is `UNPLACED` unless a `SpatiallyTaggedPhoto` already has a
non-`UNKNOWN` zone (none will, until Slice B). All current Aug 22 lots
therefore land on the holding strip. That is correct: we refuse to invent
“island 1.” Relation is still visible: the strip is a **row in walk order**,
and 2+181 share **one seat with two thumbs**.

Slice B writes real `Zone` values onto the same `Seat`. Seats move from the
strip onto the named table; thumbs do not change.

### 3.6 Console

Replace `CycleView.zone_occupancy: dict[str, list[str]]` with:

```
seats: list[Seat]   # all lots, including unplaced
```

Render:

- Barn topology stays (north wall, west tables, islands, east tables, south
  under-table / concrete).
- Each named zone: a **horizontal row of seats** for that zone, ordered by
  `walk_index`. Each seat: 1–n thumbnails (`photo_ids` order). Empty zone:
  empty row, no decorative copy that names lots.
- **Holding strip** (“not yet placed”): every `UNPLACED` seat, same row
  treatment, walk order. Never omit a lot that has a seat.
- Hardcoded “Island Table 1: Topps Baseball Cards & Costume Jewelry” comes
  **off**. Zone labels are the architecture (NORTH BACK WALL, …), not a
  fake inventory.

Thumbnails are the cached gallery JPEGs (or estatesales bytes if that is
what we already serve). No live AuctionZip fetch on render.

---

## 4. Data flow

```
462 photos, file order
  → load_or_embed (cache hit on Cloud Run)
  → apply_trajectory → group_into_lots          # walk
  → merge_reshoots(groups, reshoot_edges(...))  # returns / close-ups
  → one LotGroup per seat (photo_ids 1–n)
  → assemble + price as today (one bid per group)
  → Seat list (zone UNPLACED in Slice A)
  → render_console: barn rows + holding strip
```

Triage stays per-photo **after** grouping for category/summary, or keeps
today’s cached triage for the Aug 22 console. Slice A does not require a
new triage run. It **does** require grouping to stop using only sequential
`same_lot_as_previous` from the cached triage file (that flag on seq 181
points at seq 180).

Pipeline (`run_vertex_pipeline`) and `get_aug22_state` both call
`merge_reshoots` so the sheet and the console agree: one lot, not BT-002
and BT-181 as two bids.

OPERATOR_APPROVED `BT-181: fit None` (duplicate decline) remains a valid
belt: if merge fails, the cap still drops 181. If merge succeeds, there is
no BT-181 lot id to decline. Tests must not require both a merged group
*and* a declined BT-181 row.

---

## 5. Errors

| Failure | Behavior |
|---|---|
| Embedding cache missing on `GET /` | Walk-only groups. 181 may be its own unplaced seat. Map does not fake a merge. Log it. |
| Vector missing for one photo | That photo gets no reshoot edges. Walk still groups it. |
| cos(2,87) ≥ chosen floor | Raise the floor until 2-87 fails and 2-181 still passes. Do not ship a floor that merges 87 into 2. |
| Image bytes missing | Skip embed for that id; same as missing vector. |
| Vertex embed 429 | Cache builder backs off; request path never embeds. |

Cloud Run `GET /` never calls `embed_content` over the gallery.

---

## 6. Tests (Slice A contract)

Use Aug 22 ids (seq 2 = `838421481`, seq 181 = `838424282`, seq 87 =
`838422448`). CI uses **small fixture vectors** built so 2–181 is above
the floor and 2–87 is below — not a 462-vector dump, and not Vertex.
A live cache rebuild is a developer script, not CI.

1. `reshoot_edges`: 2–181 present; 2–87 absent.
2. `merge_reshoots`: groups that contained 2 and 181 become one group;
   `photo_ids` includes both, earlier seq first; 87 stays out.
3. Walk still merges ten under-table boxes (existing `test_spatial` cases).
4. Two captioned lots on the same table stay two seats.
5. Console HTML: one seat contains both 2 and 181 thumbs; 87’s thumb is not
   in that seat; holding strip contains unplaced seats; no “Topps Baseball
   Cards & Costume Jewelry” hardcoded in the island cell.
6. Missing embedding cache: no 2–181 merge; both lots still appear
   (holding strip or separate seats); no crash.

Do not assert a named zone for 2/181 in Slice A.

---

## 7. Slice B (out of this spec, shape only)

Overlapping listing windows → `LISTING_GRAPH_SCHEMA` (zone, surface,
margin neighbors, adjacency claims). Seats gain real `Zone` values and
move from the holding strip onto the matching barn row. Mirror validation
may run. Same `Seat`, same 1–n thumbs. Bidmath still untouched.

---

## 8. Working (Slice A)

Slice A is working when, on the Aug 22 gallery, **without** listing-window
Gemini:

1. Seq 2 and seq 181 are one lot / one seat / two thumbs **before**
   pricing.
2. Seq 87 is not on that seat.
3. The console shows that seat (on the holding strip until Slice B) and
   does not drop any lot from the map.
4. The island cell does not claim Topps/jewelry unless those seats have a
   real zone.

Named barn pins from pixels wait for Slice B. That is a smaller “working”
than the four-point live bar discussed earlier, and it is the bar for
**this** commit.
