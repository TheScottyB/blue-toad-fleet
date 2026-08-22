# Spatial Step 0, Slice A — design

**Date:** 2026-08-21
**Branch:** `feat/gemma-curator-voice`
**Status:** revised after master-lane probe of the live vectors; not an
implementation plan

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
  API keys are `photo_id`. A seq-keyed dump (the capability probe) is
  translated through `manifest.sequence` on ingest; we do not keep two
  key spaces.
- **Depends:** Vertex client, local image bytes. **Does not** run on Cloud
  Run `GET /`. If the cache file is missing at request time, skip reshoot
  edges; do not embed 462 photos inline.

### 3.2 Reshoot edges

- **Does:** undirected edges between photos that are the **same objects**
  (close-up / return), not merely the same table.
- **Rule: mutual top-1.** For each photo `i`, `nn(i)` is the other photo
  with the highest cosine (self excluded). Draw an edge `{i,j}` iff
  `nn(i)=j` **and** `nn(j)=i`. A tie for highest cosine is not an edge
  (refuse). One-sided rank-1 is not an edge.
- **Why not a cosine floor.** Live vectors (probe, seq-keyed) put the
  true reshoot and the same-table neighbors in a 0.012 band:

  | pair | cos | 2→s | s→2 | mutual #1 |
  |---|---|---|---|---|
  | **2↔181** | 0.9061 | **1** | **1** | **yes** |
  | 2↔180 | 0.8941 | 2 | 1 | no |
  | 2↔182 | 0.8919 | 3 | 2 | no |
  | 2↔179 | 0.8814 | 4 | 1 | no |
  | 2↔183 | 0.8595 | — | — | no |
  | 2↔87 | 0.8082 | 9 | 3 | no |

  A floor in (0.8082, 0.9061) — which is what “above 87, below 181”
  required — admits six same-table neighbors. Floor plus “top-3”
  still takes 180 (rank 2) and 182 (rank 3). One-sided rank-1 is the
  bug: 179 and 180 rank #1 *toward* 2. **The asymmetry is the signal.**
  Seq 87 is an easy negative (different bin). Seq 180 is the hard one
  (same table, 0.012 under the true reshoot).
- **Contract:**

  | Pair | Edge? | Why |
  |---|---|---|
  | seq 2 ↔ seq 181 | yes | only mutual #1; close-up of trays 12/14 |
  | seq 2 ↔ seq 180 | no | same table, different lot; one-sided #1 |
  | seq 2 ↔ seq 87 | no | different bin; easy negative |
  | consecutive uncaptioned under-table boxes | n/a | walk / trajectory, not this unit |

- **Recall trade:** mutual-#1 is strict (a minority of same-caption
  recaptions). A false merge destroys a bid. A missed merge leaves two
  seats on the holding strip, which is visible. Slice A takes that
  trade. Do not loosen to top-3 or a cosine floor to chase recall.
- **Use:** `reshoot_edges(ids, vectors) -> set[frozenset[photo_id, photo_id]]`.
- **Depends:** embedding cache only. The graph of these edges is a
  **matching** (disjoint pairs): each photo has at most one nearest
  neighbor, so A↔B and B↔C cannot both be mutual.

### 3.3 Walk groups

Existing `spatial_same_lot` + `apply_trajectory` + `group_into_lots`.
Unchanged rules: same zone, uncaptioned run, model `same_lot_as_previous`
in-zone, zone change breaks the run. Two captioned lots on the same table
stay two groups.

### 3.4 Union reshoots into seats

`same_lot_as_previous` only chains to the immediately previous photo, so it
cannot attach 181 to 2. After walk grouping:

`merge_reshoots(groups, edges) -> groups`

If an edge links a photo in group A to a photo in group B, A and B
become one `LotGroup`. `photo_ids` is file order (establishing shot
first). `lot_key` of the surviving group is the earlier key (seq 2
wins over seq 181).

Under mutual-#1 the edge set is a matching, so this unions **at most
two walk-groups per edge**. No A–B–C chain. Do not add a cosine-floor
edge rule later without revisiting that; a size cap is the wrong fix
for a matching that already cannot chain. A group-size cap is not
required in Slice A.

**`len(photo_ids)` is not `unit_count`.** After the merge, BT-002 has
two photos and three trays: `photo_ids == (seq2, seq181)`,
`unit_count == 3` from Bill’s x3 ruling. Both are 1–n collections on
the same lot. Setting `unit_count` from thumb count would price two
hammers on a three-tray times-the-money lot (or three hammers on a
two-angle crock). Assemble/pipeline must not infer k from
`len(photo_ids)`. Bidmath still owns `unit_count`.

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
| Live cache makes 2↔180 mutual #1 | Do not ship. That is a failed contract (same-table merge), not a knob to turn. |
| Image bytes missing | Skip embed for that id; same as missing vector. |
| Vertex embed 429 | Cache builder backs off; request path never embeds. |

Cloud Run `GET /` never calls `embed_content` over the gallery.

---

## 6. Tests (Slice A contract)

Use Aug 22 ids (seq 2 = `838421481`, seq 181 = `838424282`, seq 180 =
`838424264`, seq 87 = `838422448`). CI uses **small fixture vectors**
that reproduce the rank pattern, not the 462-vector dump, and not
Vertex: 2 and 181 are each other’s #1; 180’s #1 is 2 but 2’s #1 is
181 (one-sided); 87 is neither. A live cache rebuild is a developer
script, not CI.

1. `reshoot_edges`: 2–181 present; **2–180 absent** (hard negative);
   2–87 absent (easy negative).
2. `merge_reshoots`: groups that contained 2 and 181 become one group;
   `photo_ids` includes both, earlier seq first; 180 and 87 stay out.
   Merged `photo_ids` length is 2; a test may construct a Lot with
   `unit_count=3` and must not copy length onto `unit_count`.
3. Walk still merges ten under-table boxes (existing `test_spatial` cases).
4. Two captioned lots on the same table stay two seats.
5. Console HTML: one seat contains both 2 and 181 thumbs; 180’s and
   87’s thumbs are not in that seat; holding strip contains unplaced
   seats; no “Topps Baseball Cards & Costume Jewelry” hardcoded in the
   island cell.
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
   pricing. `unit_count` on that lot is still 3, not 2.
2. Seq 180 and seq 87 are not on that seat.
3. The console shows that seat (on the holding strip until Slice B) and
   does not drop any lot from the map.
4. The island cell does not claim Topps/jewelry unless those seats have a
   real zone.

Named barn pins from pixels wait for Slice B. That is a smaller “working”
than the four-point live bar discussed earlier, and it is the bar for
**this** commit.
