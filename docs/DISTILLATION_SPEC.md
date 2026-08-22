# Blue Toad Fleet distillation specification

Status: proposed after repository review on 2026-08-22. This document authorizes
no deletion by itself. Each destructive step needs a reviewed inventory and a
recoverable archive or release artifact first.

## 1. Product boundary

The smallest **operational** product begins with an auction listing, not a local
image. It must:

1. accept an auction listing URL/id and immutable cycle metadata;
2. discover the listing's complete photo set and captions;
3. fetch and validate the full appraisal-grade image for every manifest row;
4. upload the source manifest and images into the cycle's private cloud prefix;
5. write a completion marker only after exact cloud coverage is verified;
6. launch an idempotent cloud processor from that marker;
7. turn every photo into a puzzle piece, compare it with the other pieces,
   repeatedly merge/split item and lot hypotheses until the puzzle converges;
8. identify and value every completed item/lot hypothesis, carrying uncertainty
   and evidence grade instead of dropping or refusing one;
9. seal derived results and make the cycle visible only after validation.

```text
auction listing
  -> acquisition job
  -> immutable Cloud Storage input (manifest + full-size photos)
  -> READY marker written last
  -> processing job
  -> observe every photo as a puzzle piece
  -> match pieces -> rebuild clusters -> repeat until stable
  -> identification + sold evidence + valuation for every cluster
  -> sealed result manifest / ACTIVE pointer
```

Cloud Storage is therefore both the durable source boundary and the work handoff.
The processor must not depend on the machine that fetched the listing. A local
filesystem remains a development adapter, not a production stage.

Within that operational flow, the puzzle solver, identification, and pricing are
one provider-independent processing core. There is no triage gate and no
`worth_appraising` gate: cost may be optimized with batching, caching, indexes,
and model routing, but not by giving some photos a lesser semantic path. Auction
bid mechanics, budget allocation, spreadsheets, email, the Gate console, memory,
and demo media are consumers or optional extensions.

## 2. Review findings

### 2.1 Repository weight is mostly artifacts and history

The working checkout is about 1.3 GB, but `src/` is under 1 MB. The large areas
observed during review were:

- `.git`: about 472 MB, dominated by repeated versions of MP4 files;
- `media`: about 548 MB locally, including about 450 MB of ignored raw captures;
- `.venv`: about 189 MB and `node_modules`: about 18 MB;
- tracked `media`: about 103 MB;
- tracked `artifacts`: about 28 MB;
- tracked `data`: about 18 MB.

Deleting current media files will not shrink existing clones because the large
blobs remain in Git history. History cleanup is therefore a separate, coordinated
distillation.

### 2.2 The application is small in bytes but broad in responsibility

The Python code is about 7,600 lines in `src/`, 5,400 lines in `scripts/`, and
7,000 lines in tests. The main concentration points are:

- `src/appraiser/engine.py`: model client, identification, container location,
  container decomposition, curator writing, grounded pricing, batch execution,
  caching, and domain conversion;
- `scripts/run_vertex_pipeline.py`: intake, grouping, model execution, pricing,
  allocation, question handling, workbook/email creation, and publication;
- `src/server.py`: reconstructs Aug-22 state and imports business functions from
  `scripts/run_vertex_pipeline.py`;
- `scripts/dry_run_single_photo.py`: a separate end-to-end implementation that
  imports historic Aug-22 constants from the corpus runner;
- `scripts/run_grounded_pricing.py`, `GroundedPricingPipeline`, and the batch
  functions: overlapping pricing orchestration paths;
- `scripts/run_aug22_cycle.py`: a second authoritative-looking money path with a
  superseded schedule.

Tests currently import runner scripts as libraries, reinforcing these accidental
boundaries.

Review verification also showed a false sense of coverage: the 59 focused
pricing/engine/single-photo tests passed, while the checked-in grounded artifact
is incompatible with the current comp seam. The full working-tree suite had six
failures in question-memory/Gate behavior and seven opt-in network tests skipped.
This is a dirty working tree with substantial pre-existing edits, so those
unrelated failures were recorded rather than repaired during this review.

The current in-progress cloud-cycle code already contains the right durable
handoff idea: `CycleRepository.stage_directory` uploads the manifest and source
images, `READY.json` is written last, Eventarc launches a Cloud Run Job, and
derived artifacts are sealed before `ACTIVE.json` changes. The unnecessary
operational step is that `cache_gallery.py` first builds a permanent local drop
and `stage_cycle.py` later uploads it. Those should become one resumable
acquisition job whose destination is the cloud prefix. A local snapshot may be
exported for debugging, but it should not be required to process a sale.

### 2.3 The current pipeline violates the puzzle invariant

The current system triages all 462 photos, deeply appraises only 228, and attempts
grounded pricing on only 46 stored rows. That funnel is the wrong topology for
this product. Every source photo must produce the same kind of observation, enter
the same match graph, and contribute to the final identity of its cluster. A low
shop-fit score can affect buying policy later; it cannot prevent reconstruction,
identification, or valuation.

The correct processing invariant is:

```text
for every photo:
  extract the same observation schema

repeat:
  retrieve likely matches from the entire cycle
  score same-item / same-lot / incompatible relationships
  rebuild item and lot clusters
  re-identify each cluster using all of its views
  propagate the cluster identity back into match retrieval
until every photo is assigned exactly once and the graph is stable

value every stable item/lot cluster
```

An unmatched photo is not refused; it becomes a valid singleton cluster. An
uncertain cluster is not discarded; it carries its conflicts and confidence into
valuation and review. Completion means 100% photo assignment, no contradictory
membership, and no merge/split/identity changes across the configured stability
passes.

### 2.4 Grounded pricing fails for several independent reasons

The stored Aug-22 evidence contains only 46 grounded-pricing rows for a 462-photo
cycle that currently resolves to roughly 415 lot hypotheses. Of those 46, 25 are
marked unusable. The 21 marked usable are not all trustworthy: 11 have a final
high/low ratio above 3, seven above 5, and four above 10. Examples include
`$79-$5,102.22` and `$105.01-$1,850`.

The causes are:

1. **Grounding is off on the ordinary local pipeline.** `run_pipeline` defaults
   `enable_grounded_pricing=False`, and the script's Aug-22 `__main__` call does
   not enable it. Only the newer cloud worker opts in. The stored
   `pipeline_state.json` contains no grounded-pricing run summary.
2. **The checked-in run is partial by design.** `grounded_prices.json` contains
   only 46 rows because fit/appraisal gates decide which pieces deserve research.
   The standalone script also explicitly excludes hand-entered `REFERENCE_COMPS`
   lots. Neither behavior treats every completed cluster uniformly.
3. **The checked-in cache uses an obsolete schema.** Its rows have neither
   `attempt_complete` nor `input_sha256`. Current `grounded_reference_comps`
   requires `attempt_complete is True`, so it converts zero checked-in grounded
   rows into current `CompEstimate` records. Synthetic tests pass but do not
   validate the shipped artifact.
4. **Search receives a prose identification, not a pricing identity.** Quantity,
   sale unit, exact variant, grade, tested state, completeness, and unresolved
   scope questions are not enforced search constraints. A card search therefore
   mixes raw and graded examples; a camera search mixes tested and untested
   bodies; a group lot mixes individual items and collections.
5. **The model reports aggregate ranges instead of evidence rows.** The system
   stores a model-produced low, high, and count. It does not store one normalized
   price, date, quantity, condition, and direct sold URL per comparable. The
   claimed count cannot be reconciled to cited sales.
6. **Grounding citations prove retrieval, not comparability.** The stored sources
   are opaque Vertex redirect URLs. No deterministic record binds a quoted price
   to a specific sold item or proves that it is completed rather than asking.
7. **The acceptance gate checks the wrong shape.** It compares only the three
   high endpoints. It does not check low-end agreement, final range width,
   price-to-source binding, variant/grade/quantity compatibility, currency,
   shipping, date, or duplicate comps. Consequently three consistently broad
   searches pass.
8. **Medianing range endpoints does not create a comparable set.** When each
   search sampled a different population, the median low and median high may not
   describe any coherent market.
9. **Six model calls per lot amplify cost and failure.** Applying the current
   three-grounded-plus-three-extraction pattern uniformly to roughly 415 lots
   would require about 2,490 calls before retries. Repetition is being used to
   compensate for an under-specified evidence model.

## 3. Target runtime

Create a new vertical slice without initially deleting the old paths:

```text
src/blue_toad/
  acquisition/
    listing.py     # discover listing rows and captions
    fetch.py       # fetch/validate full-size images
    job.py         # upload manifest/images, verify coverage, write READY last
  cycles/
    model.py       # immutable CycleRequest, source identities, statuses
    storage.py     # cloud object contract and generation-safe writes
    dispatch.py    # READY event -> one processing job
    worker.py      # materialize/stream inputs and seal validated results
  processing/
    models.py      # PhotoPiece, Observation, MatchEdge, Cluster, SoldComp, Valuation
    image.py       # byte validation and hashing only
    observe.py     # the same multimodal observation pass for every photo
    match.py       # whole-cycle candidate retrieval and relationship scoring
    puzzle.py      # iterative cluster rebuild, split/merge, convergence checks
    identify.py    # cluster identity from all member views
    research.py    # sold-result retrieval adapter(s)
    comp_match.py  # deterministic comp normalization and compatibility checks
    value.py       # deterministic valuation from accepted SoldComp rows
    pipeline.py    # pieces -> converged clusters -> identity/evidence/valuation
  cli.py           # thin acquisition/process development commands
tests/core/
  fixtures/       # a small, reviewed image/evidence corpus
```

The puzzle/identification/pricing core should stay deliberately small and typed;
line count is a guardrail, not a reason to weaken the uniform-photo invariant.
Acquisition and cycle orchestration get a separate budget. The initial production
dependencies should be only those required for the model client, vector/index
operations, image validation, selected sold-data source, Cloud Storage, and job
dispatch. FastAPI is needed only if an HTTP control/event endpoint remains;
Firestore, OpenPyXL, Playwright, and media tooling remain optional adapters.

### 3.1 Cloud landing contract

One cycle owns an immutable cloud prefix:

```text
shops/<shop>/cycles/<cycle>/
  control/request.json
  input/manifest.json
  input/images/<stable-photo-id>.<detected-extension>
  control/READY.json
  status/acquisition.json
  status/processing.json
  output/blobs/<sha256>/<artifact>
  output/artifact_manifest.json
```

Required rules:

- `request.json` is the creation lock for a cycle id.
- Every image is validated before upload: successful HTTP response, detected
  image MIME, decodability, minimum dimensions, byte size, and SHA-256.
- The manifest records listing URL/id, sequence, caption, source URL, durable
  object name, object generation, detected MIME/dimensions, byte size, and hash.
- HTML, WAF/challenge responses, thumbnails, duplicate filenames, missing
  sequences, and partial downloads fail acquisition.
- Acquisition may resume safely. An already uploaded object is reused only when
  its recorded hash and generation match.
- `READY.json` is the only processing trigger and is written after manifest/image
  coverage reconciles exactly. Image-finalize events must not launch hundreds of
  partial cycle jobs.
- Duplicate READY/Eventarc deliveries resolve to one launch claim. Processing is
  idempotent by cycle/request/source hashes.
- A failed acquisition writes status and never writes READY. A failed processor
  never updates ACTIVE.
- The processing job reads cloud source identities. Its ephemeral paths never
  appear in published artifacts.

This preserves the strongest part of the current `src/cycles` work while
removing the required local staging directory.

### 3.2 Puzzle contracts

```text
PhotoPiece
  photo_id
  cycle_id
  sequence
  caption
  source_object, source_generation, image_sha256

Observation
  photo_id
  detected_objects[]
  visible_text[]
  visual_embedding
  scene/background_features
  viewpoint
  visible_marks[]
  visible_condition[]

MatchEdge
  photo_a, photo_b
  relation: same_item | same_lot | spatial_neighbor | incompatible
  score
  evidence[]
  iteration

ItemCluster
  cluster_id
  member_photo_ids[]
  identity
  sale_unit
  conflicts[]
  confidence
  revision

PuzzleState
  cycle_id
  iteration
  assigned_photo_count
  total_photo_count
  clusters[]
  changed_edges, merges, splits, identity_changes
  stable_passes
  complete
```

Required invariants:

- Every manifest photo has exactly one `PhotoPiece` and one `Observation`.
- Every piece belongs to exactly one item cluster at publication. Singleton
  clusters are valid.
- Matching considers candidates from the whole cycle; sequence adjacency may be
  evidence but never the search boundary.
- Merge and split decisions preserve their evidence and iteration history.
- Cluster identity is regenerated from all member photos after membership
  changes; a first-photo caption is not authoritative.
- The loop completes only with 100% assignment, no contradictory memberships,
  and stable graph/identity revisions across consecutive passes.
- Pricing starts from stable cluster identities, never independently from each
  angle of the same object.

### 3.3 Identification contract

```text
Identification
  item_class
  maker
  model_or_series
  variant
  approximate_date
  quantity
  sale_unit                  # single item, pair, collection, unknown
  visible_marks[]
  visible_condition[]
  tested_state               # tested, untested, unknown
  unknowns[]
  valuation_uncertainties[]
  confidence
  image_sha256
  model_and_prompt_version
```

Unknown fields stay unknown. A valuation uncertainty such as card grade, lot
scope, camera functionality, or collection quantity must not be hidden inside
prose. There is no terminal refusal state in this contract.

### 3.4 Evidence contract

```text
SoldComp
  source
  source_item_id
  direct_url
  title
  sold_price
  currency
  shipping                 # separate; never silently folded into sold price
  sold_at
  quantity
  condition_or_grade
  query
  fetched_at
  match_score
  mismatch_reasons[]
```

The model may propose queries and help score semantic similarity. It may not
author sold prices, sold dates, result counts, or source URLs. If a search tool
cannot return individual sold records with inspectable evidence, it is a discovery
aid only and cannot authorize a price.

### 3.5 Valuation contract

- Normalize currency, quantity, and shipping policy before calculation.
- Reject asking listings, duplicate records, incompatible sale units, clearly
  different variants, and incompatible graded/ungraded populations.
- Produce a valuation for every stable cluster. Prefer at least three accepted
  exact sold records, then analogous sold records, then a clearly labeled market
  prior when direct evidence is sparse.
- Compute a median unit value and robust dispersion from accepted records when
  available. Do not manufacture a low/high range by combining model summaries.
- When dispersion is high or a pricing attribute is unknown, widen uncertainty,
  lower `evidence_grade`, and preserve the reason; do not drop the cluster.
- Return every accepted/rejected comp and reason beside the estimate.
- Keep resale valuation separate from auction bid math. Bid policy consumes a
  valuation later; it does not belong in grounded research.

Every valuation carries one explicit basis:

```text
exact_sold_comps | analogous_sold_comps | category_market_prior
```

Thus every puzzle piece reaches a priced cluster, while downstream bid policy can
still decide how much authority to give a weak evidence grade.

## 4. Distillation series

### D0 — Freeze and measure

Goal: establish a safe baseline before deletion.

- Tag the current commit and export the current demo/video/data as a release or
  external archive.
- Record hashes for the nine-bid sent sheet, source manifest, selected fixture
  images, and current JSON outputs.
- Add an artifact compatibility test that exposes the current obsolete grounded
  cache instead of silently accepting synthetic-only coverage.
- Record a `cloc`, tracked-size, history-size, dependency, and entry-point
  inventory.

Gate: the existing outcome can be recovered, and the baseline report is
reproducible from a clean clone.

### D1 — Remove weight from the current tree

Goal: make the working repository code-first without rewriting history yet.

- Move final videos, narration, screenshots, probe montages, generated workbooks,
  complete cycle caches, and historical manifests to release/object storage.
- Keep links and checksums in `docs/evidence/`, not the binaries.
- Retain only a deliberately small set of licensed test images and compact JSON
  evidence fixtures.
- Expand cleanup for ignored raw captures, local environments, and generated
  outputs, but never delete them automatically without an explicit target.
- Add a tracked-file size gate (for example, fail above 2 MB unless allowlisted).

Gate: a normal checkout is below 25 MB excluding `.git` and developer-created
environments; tests do not require the 462-photo corpus.

### D2 — Distill listing acquisition into the cloud landing boundary

Goal: make the auction listing flow directly into durable, processable cloud
input without requiring a permanent local gallery directory.

- Extract listing parsing and image fetching from `cache_gallery.py` into an
  acquisition library/job.
- Reuse the validated `CycleRequest`, cycle-prefix, immutable object, READY, and
  launch-claim concepts from the current `src/cycles` work.
- Upload each validated full-size photo directly to its cycle input prefix and
  persist resumable acquisition status.
- Generate the authoritative manifest from successful uploaded objects, not
  local filenames.
- Verify exact discovered/uploaded/manifest coverage, then write READY last.
- Keep a local object-store adapter for tests and an optional explicit export
  command for debugging.

Gate: given a listing fixture, one acquisition run produces a complete immutable
cloud cycle and starts exactly one processor; interruption, challenge HTML,
missing images, duplicate events, and retry cannot produce a READY partial cycle.

### D3 — Build the uniform puzzle engine

Goal: give every cloud photo the same observation path and iteratively assemble
the complete item/lot graph.

- Implement `PhotoPiece`, `Observation`, `MatchEdge`, `ItemCluster`, and
  `PuzzleState`.
- Run the same observation schema on every image. Remove `worth_appraising`,
  fit-score appraisal selection, and caption-only fallbacks from reconstruction.
- Build a whole-cycle candidate index from visual embeddings, OCR/marks, captions,
  and scene features. Every piece queries it; sequence distance never excludes a
  candidate.
- Score same-item, same-lot, spatial-neighbor, and incompatible edges.
- Rebuild clusters, regenerate identity from all member views, and repeat until
  the completion invariants hold.
- Persist each iteration so a worker retry resumes rather than restarts or loses
  earlier merge/split evidence.
- Preserve visible marks, unknowns, quantity, sale unit, conflicts, and valuation
  uncertainties as structured fields.

Gate: all fixture photos are observed once, assigned exactly once, and converge
to the reviewed clusters; long-gap repeat photos merge, visually similar distinct
items remain split, and processing imports no runner, server, Gate, memory, or
bid-math module.

### D4 — Replace summarized grounding with evidence-first pricing

Goal: make every dollar trace to an individual sold record.

- Implement query generation from `Identification`.
- Select one sold-data adapter capable of returning individual completed sales.
- Normalize result rows and apply deterministic compatibility checks.
- Compute valuation from accepted `SoldComp` records and a typed, explicitly
  labeled fallback basis when exact records are sparse.
- Store uncertainty reasons such as `sparse_exact_comps`, `scope_unknown`,
  `condition_unknown`, `high_dispersion`, `source_unavailable`, and
  `identity_uncertain`; none removes the cluster from output.
- Cache immutable evidence attempts by image, identification, query, source,
  and policy versions. Never overwrite attempt history.

Gate: every stable cluster has a valuation and explicit basis. Every
`exact_sold_comps` valuation has individually inspectable records; changing
quantity, grade, condition, membership, or identity invalidates the research
cache; the numeric valuation can be recalculated from its stored evidence/basis
without a model call.

### D5 — Prove it on a small gold set

Goal: measure correctness before restoring scale.

- Select 20-30 representative photos: single item, rare item, graded/ungraded
  card, tested/untested camera, pair, bulk box, ambiguous scope, no exact comps,
  adjacent repeat views, and long-gap repeat views.
- Human-review the expected piece relationships, clusters, identity, allowed
  uncertainty, accepted/rejected comps, valuation, and evidence basis.
- Measure identification family accuracy, exact-variant precision when visible,
  pair-edge precision/recall, final cluster precision/recall, comp acceptance
  precision, evidence-grade accuracy, and valuation error against a reviewed
  reference.
- Include the current pathological lots (BT-018, BT-054, BT-291, BT-296) as
  regression cases.

Gate: 100% piece coverage; zero duplicate pricing of multi-angle views; zero
incorrect cross-item merges; zero asking-price leakage; zero unit/lot or
graded/ungraded comp mixing; every valuation has a reproducible basis and honest
uncertainty.

### D6 — Route consumers through the core, then retire duplicates

Goal: establish one owner for each responsibility.

- Make cloud cycle processing call the puzzle core for the complete source set.
- Retire the old triage/grouping/dedup paths after puzzle parity; reconstruction
  has one owner.
- Keep bid mechanics/allocation as an optional postprocessor.
- Make the server and cloud worker call library APIs; no code under `src/`
  imports `scripts/`.
- Collapse the standalone pricing script and streaming pricing class onto one
  batch adapter.
- Retire or quarantine `run_aug22_cycle.py`; turn `run_vertex_pipeline.py` and
  `dry_run_single_photo.py` into thin compatibility wrappers, then remove them
  after one release.
- Move container decomposition, memory, curator, Gate UI, spreadsheets/email,
  and cloud publication into explicit optional packages. Delete any optional
  capability that lacks a real consumer or acceptance test.

Gate: one canonical pipeline owns observation, matching, cluster identity, and
valuation; all retained entry points produce the same puzzle and valuation
records for the same cloud source/evidence inputs.

### D7 — Rewrite Git history after coordination

Goal: make clones small, not merely the latest checkout.

- Announce a history rewrite and require collaborators to finish or export
  work first.
- Use `git filter-repo` to remove historical video/audio/probe/generated-data
  blobs, or create a clean repository from the distilled tree if preserving the
  old commit graph has little value.
- Publish an archival tag/bundle separately, force-push the rewritten refs, and
  require fresh clones.
- Keep future large releases outside Git or in Git LFS only when source control
  semantics are truly needed.

Gate: packed Git history is below 25 MB and a clean clone plus test install can
run the core fixture suite without downloading demo or historical assets.

## 5. Keep, move, and remove decision

Keep in the operational core:

- listing acquisition and full-size image validation;
- immutable cloud input, READY dispatch, processing status, and sealed results;
- image validation and hashing;
- uniform per-photo observation;
- whole-cycle match graph and iterative cluster convergence;
- one model client seam and cluster-identification schema;
- sold-record adapters and deterministic matching;
- deterministic valuation with explicit evidence basis and uncertainty;
- a small CLI/API seam and focused tests.

Keep as optional auction extensions only when still wanted:

- bounded-container handling;
- choice/times-the-money mechanics, bid policy, and budget allocation;
- human questions/rulings and durable memory;
- email/spreadsheet output;
- operator UI.

Move out of the code repository:

- final and intermediate video/audio;
- full galleries and generated model caches;
- probe outputs and montages;
- screenshots and generated workbooks except minimal fixtures;
- historical submission artifacts.

Remove after parity or archive:

- duplicate runners and artifact writers;
- live product imports from `scripts/`;
- embedded Aug-22 defaults in generic paths;
- model-produced comp counts and aggregate price ranges;
- triage/fit gates that prevent a photo from receiving the uniform observation,
  matching, identification, and valuation path;
- synthetic tests that prove only wiring while shipped artifacts violate the
  current schema;
- unused spatial/UI/demo claims or code that is not retained as an explicit
  product extension.

## 6. Recommended first implementation slice

The first code change should be D2: combine listing acquisition and cloud staging
behind one tested boundary while retaining the current READY-triggered worker.
Then build D3 plus the data types needed by D4. This creates a stable destination
for migrated behavior and gives deletion an objective parity target. In parallel,
D1 may remove current tracked artifacts, but D7 should wait until the core passes
the gold-set gate and current dirty work has been reconciled.
