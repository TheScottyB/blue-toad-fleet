# Repository Remediation and Submission Integrity — design

**Date:** 2026-08-22  
**Baseline:** `8ef89bc` plus the current uncommitted `docs/TODO.md` review  
**Status:** proposed master design; not an implementation plan  
**Source inventory:** `docs/TODO.md` A1–A7, B0–B8, C1–C9, D1–D3,
E1–E3, F0–F21

This document turns the repository-wide TODO audit into one coherent target
architecture. The paired execution plan is
`docs/superpowers/plans/2026-08-22-repository-remediation.md`.

`src/cycles/` currently exists as untracked concurrent work. This design treats
its immutable cycle request, object store, job launcher, and worker as a candidate
implementation of the cycle/publish boundary. The remediation lane must review
and integrate that work; it must not overwrite or silently adopt it.

---

## 1. Goal

Ship one reproducible auction-cycle pipeline whose visible claims, source
evidence, decisions, bid sheet, clerk email, console, screenshots, and video all
describe the same validated cycle.

The core invariant is:

> No answer, model result, merge, price, bid, document, screenshot, or video is
> authoritative merely because a file was written. It becomes authoritative only
> after its decision-bearing inputs are identified, its validation gates pass,
> and the complete artifact set is promoted together.

This design also preserves the operator's feature-floor instruction. Spatial
mapping, container decomposition, eBay absorption, grounded pricing, proactive
pushback, durable memory, and choice-lot handling remain product requirements.
Unsupported copy is not accepted as a substitute for implementing them, and
invalid evidence is not retained merely to protect a headline.

---

## 2. Problems to solve

The audit found six interacting classes of failure:

1. **Money-path divergence.** The console, email, hard-coded operator overrides,
   question answers, mechanic parser, allocator, and speculative remainder path
   do not share one decision state or one clerk instruction.
2. **Unsafe authority.** The public Answer endpoint can mutate durable Firestore
   without authenticated operator identity; inferred reshoot edges can change
   money without human approval.
3. **Partial publication.** Model failures, stale caches, interrupted downloads,
   and obsolete scripts can still overwrite sealed sheets, screenshots, or video.
4. **Evidence gaps.** Grounded pricing is offline, eBay velocity is not a cycle
   input, the curator cannot see bounded evidence, and spatial surface/zone code
   is not wired into production.
5. **Artifact drift.** Counts, test totals, runtime versions, map claims, and bid
   totals are duplicated across Markdown, HTML, title cards, diagrams, scripts,
   screenshots, and narration.
6. **Non-reproducible proof.** The July comparison, capability probes, capture
   utilities, and media builders depend on bad joins, personal paths, anonymous
   temp files, hard-coded durations, or uncommitted inputs.

These are not independent cleanup tickets. For example, wiring answers into
allocation before fixing rule scope would turn a harmless queue bug into an
incorrect authorization to spend. Publishing grounded prices before fixing cache
identity would make stale evidence authoritative. The order is part of the
design.

---

## 3. Non-goals

- Do not add OpenCV image hashes, FAISS, COLMAP, or a second embedding stack.
- Do not add an upscaling stage; the capability probe already showed fabricated
  decision-bearing text.
- Do not automate bidding against an auction API. The authoritative output is a
  human-reviewed clerk email and bid sheet.
- Do not turn third-party listing text into instructions. Browser research is
  read-only and listing content is data, never control input.
- Do not preserve the July benchmark as “ground truth” without rebuilding it from
  reproducible inputs and the current pipeline.
- Do not make every TODO a permanent feature. Rebaseline first; close obsolete
  findings with evidence rather than implementing them.

---

## 4. System boundaries and ownership

### 4.1 Cycle identity

Every run has one immutable `CycleRequest`:

```text
cycle_id
listing_id
shop_id
auction title/date/timezone/venue/deadline
budget_cap
auto_send_threshold
source manifest identity
created_at
```

Decision-bearing outputs live under that cycle. No Aug-22 filename may be a
default for a parameterized run. A cycle may be retried, but its immutable source
request and source-object hashes do not change.

The durable source manifest retains storage-relative/object references. A worker
may add a runtime materialization path while executing, but that temporary path
is never serialized as the published photo identity. Deleting the worker's
temporary directory must not break any published source reference.

Question fixtures are cycle inputs too. A generic cycle defaults to no historical
questions; an explicit fixture/wrapper may supply cycle-specific questions, all
of whose lot ids must exist in that cycle.

The untracked `src/cycles/model.py` is directionally aligned with this contract
but currently lacks auction metadata and evidence/publish identities. Integration
must add those fields or explicitly source them from a versioned cycle metadata
object.

### 4.2 Staging and promotion

Pipeline state is explicit:

```text
STAGED -> RUNNING -> DEGRADED | VALIDATED -> PUBLISHED
                              \-> FAILED
```

- `STAGED`: normalized manifest plus every named source image are durable.
- `RUNNING`: models and deterministic transforms may write only to a run-specific
  staging prefix/directory.
- `DEGRADED`: one or more required calls/rows failed. Diagnostic artifacts may be
  retained, but no final sheet/email/active pointer is written.
- `VALIDATED`: coverage, schema, provenance, money, and artifact checks pass.
- `PUBLISHED`: the complete validated artifact manifest is promoted atomically and
  the cycle becomes the shop's active cycle.
- `FAILED`: the last known-good published cycle remains untouched.

`READY`, `LAUNCHED`, and `ACTIVE` markers from `src/cycles/storage.py` may
implement this state machine if their preconditions and atomicity are tested.

### 4.3 One authoritative artifact manifest

A published cycle has an `artifact_manifest.json` containing, at minimum:

```text
cycle_request_hash
source_manifest_hash
model/prompt/schema versions
standing-rule revision set
approved reshoot-edge revision
comp-evidence revision set
decision snapshot hash
test/evidence snapshot hash
artifact path, media type, sha256, byte size for every output
published_at and publisher identity
```

The email, workbook, API snapshot, console facts, screenshots, diagrams, title
cards, and video must be traceable to that manifest. An artifact missing from the
manifest is not a release artifact.

### 4.4 Canonical writer rule

Each authoritative path has exactly one owner:

| Artifact | Canonical owner |
|---|---|
| cycle decision snapshot | canonical cycle pipeline |
| bid sheet | canonical cycle pipeline |
| absentee email | shared `compile_absentee_email` path |
| active cycle pointer | publish/promote service |
| screenshot evidence | validated capture orchestrator |
| final demo MP4 | one media assembler |
| submission facts | evidence snapshot generator |

Legacy runners/builders either delegate to the canonical owner, write clearly
historical filenames, or are removed. Tests enumerate protected paths and fail if
multiple scripts own one.

The canonical Python entry point has frozen, typed `PipelineConfig` and
`PipelineResult` boundaries and explicit intake, appraisal, decision, and artifact
stages. Reusable stages raise typed exceptions; only a thin command-line boundary
maps them to exit codes. Production imports do not depend on repository
`sys.path` mutation or serialization through arbitrary `__dict__` access.

---

## 5. Decision and evidence model

### 5.1 Typed operator answers

Answers separate **standing policy** from **cycle/lot rulings**:

```text
StandingPolicy
  shop_id
  kind: POLICY | APPETITE
  category
  answer
  revision, source_question_id, actor, timestamps

LotRuling
  shop_id, cycle_id
  lot_id or cluster_id
  kind: LOT_GROUPING | SCOPE | MECHANIC | CONDITION_OVERRIDE
  typed payload
  source_question_id, actor, revision, timestamps
```

`LOT_GROUPING` and `SCOPE` never generalize by category. A text answer is parsed
into a typed, reviewable payload before it may alter grouping or bid mechanics.
Unreadable or contradictory rulings refuse the affected decision instead of
guessing.

The answer transaction is:

```text
authenticate actor
-> validate current question/revision
-> persist policy or lot ruling
-> recompute affected groups/appraisals/decisions
-> validate full money state
-> stage replacement artifacts
-> return before/after decision diff
```

The response may say `pending_reappraisal=true` only when an asynchronous job was
actually queued and its status can be followed. It must not present an unchanged
recalculation as an applied answer.

### 5.2 Operator authentication

Read-only public demo endpoints may remain public. Durable mutations require
fail-closed operator authorization. The immediate release may use the current
server-configured operator token entered at runtime, provided an absent token
fails closed and the token is never embedded in HTML. Cloud Run IAM/IAP or an
authenticated server-side session is the preferred identity-bearing replacement.

Required authorization behavior:

- anonymous `POST /api/answer` -> 401/403, no state change;
- absent production auth configuration -> fail closed, no state change;
- authenticated operator -> optimistic-concurrency checked write;
- stale question/rule revision -> 409;
- actor and source question recorded in rule/ruling history;
- the UI uses the same supported auth mechanism as the API.

### 5.3 Comp evidence

`CompEstimate` must be backed by a provenance record:

```text
CompEvidence
  evidence_id
  lot_id, identification fingerprint, image/source hash
  method: grounded_search | seller_hub | operator_reference
  low/high, sold_comp_count, sources
  model/prompt/policy versions
  sample results and refusal reason
  status: usable | refused | transient_failure
  created_at, reviewed_at
```

Transient failures are retryable and do not masquerade as completed refusals.
Changes to identification, image, model, prompt, or source policy invalidate the
cache key. Only `usable` evidence becomes a `CompEstimate`; refused or missing
evidence deterministically prevents allocation.

Hand-entered reference comps remain allowed only when labeled
`operator_reference` and surfaced distinctly from grounded evidence.

### 5.4 eBay absorption evidence

Seller Hub research is an operator-authorized, read-only evidence import:

```text
absorption = sold_units_in_verified_window / active_listings_at_capture
```

The record includes query, exact displayed date window, sold units (not merely
rows), active count, capture timestamps, pagination coverage, evidence screenshots
or exported rows, and reviewer. A URL dropdown value is not proof of the date
window. No Listings, Orders, Marketing, Payments, or Messages action is permitted.

### 5.5 Approved reshoot edges

Embedding output produces **proposed** edges. Production grouping consumes only
**approved** edges:

```text
ReshootEdgeReview
  cycle_id, photo_a, photo_b
  model/input hashes, similarity and rank evidence
  proposed_at
  decision: approved | rejected
  reviewer, reviewed_at, note
```

The vector cache and approved-edge sidecar are versioned together. Forced
regeneration cannot separate new vectors from old edges. A false merge has higher
cost than a missed merge, so approval is fail-closed.

### 5.6 One clerk directive

`clerk_directive(decision)` is the only semantic instruction generator for both
console and email. Formatting may differ, but the parsed instruction tuple must be
identical.

Speculative/contingent decisions are separated from committed allocations:

- they do not consume committed cap;
- they do not appear as firm bids;
- their directive names the contingency;
- summaries report committed and contingent exposure separately.

Mechanic parsing must scope negation to the mechanic phrase and treat implausible
multipliers/elections consistently.

---

## 6. Pipeline validation gates

### 6.1 Source gate

- Every manifest photo resolves to one non-empty, decodable, appraisal-grade
  image with detected MIME, dimensions, SHA-256, and unique safe filename.
- Published photo references resolve through durable object/storage identities
  after all worker-local temporary directories are removed.
- TLS verification is on.
- HTML/WAF/challenge responses cannot be stored as images.
- Gallery text is decoded once at ingestion and escaped at every HTML boundary.
- Initial downloads and cache replacements are temporary-file + atomic rename.

### 6.2 Model-coverage gate

- Requested ids equal successful ids for every required stage.
- No required row carries an `error` field.
- Required schema fields are present and valid.
- Exact required models are reported separately from fallback diagnostics.
- A degraded run cannot publish.

### 6.3 Decision gate

- All decision ids are unique and join to lots by id, never list position.
- Grouping, approved reshoots, lot rulings, comps, mechanics, pricing, allocation,
  summary, email, and workbook reconcile from one decision snapshot.
- Committed all-in never exceeds the operator-supplied cap.
- Every allocated lot has usable labeled comp evidence and a resolved mechanic.
- No speculative decision is represented as committed.

### 6.4 Artifact gate

- Outputs are written to a run-specific staging location.
- Every artifact passes type/content checks before promotion.
- Workbook ids are unique and detail rows reconcile to the decision snapshot.
- Screenshot capture validates URL/title/body/page markers before replacing proof.
- Final video has the expected audio stream, dimensions, duration, size, and facts
  snapshot identity.
- Promotion is atomic from the consumer's perspective.

### 6.5 Clean-clone gate

- Tests run through `sys.executable -m pytest` from paths derived from `__file__`.
- Required images/probe inputs can be added normally under `.gitignore` rules.
- No personal absolute path or undocumented global `/tmp` file is required.
- Capability reports are generated from committed machine-readable results or a
  documented, hash-verified fetch recipe.

---

## 7. Spatial and container feature floor

### 7.1 Spatial path

The current proven live behavior is:

- file/walk order and triage/caption grouping;
- approved non-adjacent embedding reshoot edges;
- one seat per merged lot;
- `Zone.UNKNOWN` holding strip when no validated zone exists.

The full Spatial Room Graph requires a production caller for listing observations,
surface signatures, peripheral co-visibility, adjacency claims, trajectory, and
zone assignment. Zone labels may not be inferred from category copy. Until a lot
has validated zone evidence it remains unplaced.

Acceptance is corpus-based: known positive/negative pairs, no approved false merge,
all lots represented once, and map seats reconciling to the decision snapshot.

### 7.2 Container decomposition

The two-stage locate -> crop -> itemize path remains. A confirmed alpha requires a
visible mark/evidence with no unresolved determining question. Otherwise pricing
uses the bulk floor and names the alpha only as upside. Container counts never
come from hallucinated small text or thumbnail upscaling.

---

## 8. Queue, curator, performance, and cost

### 8.1 Question coverage

The queue may cap desk questions, but dropped questions cannot silently disappear
from risk accounting. The cycle snapshot records asked, auto-answered, deferred,
dropped, and affected lots. A release policy explicitly decides whether dropped
high-impact questions block allocation or force affected lots to refuse/flag.

### 8.2 Evidence-based curator challenge

Selection remains deterministic. The curator receives a bounded
`ChallengeFacts` object only when all elements exist:

- exact standing SKIP rule;
- exact conflicting lot and current decision;
- sourced comp and/or absorption evidence;
- allowed figures and citations;
- deterministic reason the challenge was selected.

The model phrases those facts and cannot invent another lot, price, margin, or
velocity. Without `ChallengeFacts`, pushback is absent rather than generic.

### 8.3 Performance

The system reports measured stage durations. If triage remains sequential because
of previous-summary context, copy states the measured result. Parallelization may
use bounded chunks only after tests prove adjacent grouping recall is preserved.

### 8.4 Cost

Planning estimates and measured cost are separate fields. Per-call telemetry
records cycle, stage, model, usage tokens/units, retry/fallback, latency, and
estimated/list price at execution. Cycle totals include triage, appraisal,
decomposition, grounding, embeddings, and curator calls. No estimate is labeled
as metered spend.

---

## 9. Submission facts and media

### 9.1 Evidence snapshot

One versioned `submission_facts.json` is generated from a published artifact
manifest and test collector. It contains mutable facts such as:

- cycle/photo/group/duplicate/appraisal/bid/refusal counts;
- committed max/all-in and resale range;
- runtime/model/memory backend;
- tests collected/passed/skipped and command/commit;
- feature evidence status (`implemented`, `validated`, `not yet validated`);
- source artifact hashes.

Render scripts consume this snapshot and refuse missing keys. They do not carry
fallback numbers or marketing claims.

### 9.2 Claim inventory

Every judged artifact maps its claims to spec requirements and evidence:

```text
README
DEVPOST
VIDEO_SCRIPT and narration
blog and social post
architecture diagram
title cards
screenshots
demo video
```

The inventory detects contradictory or unsupported statements. Feature-floor
claims remain release blockers until their evidence status is validated.

### 9.3 Media pipeline

- One final assembler owns `media/blue_toad_fleet_demo.mp4`.
- Every recording uses an isolated directory and the page's actual video handle.
- Narration/video durations come from probes, not constants.
- Every input is declared in a run manifest; no undocumented `/tmp` input.
- Capture/build commands fail non-zero on missing, stale, challenged, silent, or
  invalid output.
- The final cut is built only after the facts snapshot and copy freeze.

---

## 10. July benchmark policy

The current July artifact is quarantined from submission evidence. Rebuilding it
requires all of the following:

- committed reproducible legacy source workbook or legally redistributable,
  hash-verified input recipe;
- true item-row filtering with no totals/subtotals/fallback double count;
- stable unique lot ids;
- id-based joins after allocation;
- current grouping, mechanic, evidence, pricing, and allocation paths;
- explicit labeling of synthetic vs observed inputs;
- measured, not asserted, operator time;
- scorecard values derived from verified detail rows;
- tests reproducing the historical corruption and proving it fixed.

Until then, the only permissible July claims are independently verified receipt
facts whose source evidence is available, plus generic tested invariants such as
the hard budget cap.

---

## 11. Release gates

A submission candidate is releasable only when:

1. B8 rebaseline classifies every TODO as open, closed-with-evidence, superseded,
   or intentionally deferred.
2. No P0/P1 money, auth, publication, evidence-integrity, or authoritative-writer
   issue remains open.
3. One clean-clone command runs unit, integration, script, and artifact checks.
4. A staged representative cycle either publishes a complete reconciled artifact
   set or fails without changing the active cycle.
5. Anonymous mutation is denied and authenticated answer application produces a
   tested before/after money diff.
6. Every allocated lot has usable provenance and resolved mechanic state.
7. Submission facts regenerate all mutable copy/media figures without hand edits.
8. Final screenshots and video match the published artifact manifest.
9. The live health/status endpoints name the deployed commit and active artifact
   manifest.
10. The operator approves the final clerk email, bid sheet, reshoot reviews, copy,
    and video.

---

## 12. TODO coverage matrix

Duplicate B4 identifiers are disambiguated as `B4-video` and `B4-SSIM`.

| TODO | Design disposition |
|---|---|
| A1, A4 | Mechanic parser consistency and phrase-scoped negation (§5.6) |
| A2, A3, A5 | One clerk directive; separate contingent exposure (§5.6) |
| A6 | Typed answer recomputation and publish transaction (§5.1) |
| A7 | Standing policy vs lot ruling scopes (§5.1) |
| B0 | Quarantine/rebuild policy (§10) |
| B1, B2 | Clean-clone gate (§6.5) |
| B3 | Canonical deploy after release gates (§11) |
| B4-video | Facts-driven final recording (§9) |
| B4-SSIM, B5 | Reproducible/validated capability probes (§6.5, §9.1) |
| B6 | Verify the current fail-closed closure; identity-backed hardening (§5.2) |
| B7 | Claim inventory and evidence snapshot (§9.1–§9.2) |
| B8 | Mandatory rebaseline before implementation (§11.1) |
| C1, C6, E3 | Spatial production path and approved reshoots (§5.5, §7.1) |
| C2 | Bounded container decomposition (§7.2) |
| C3 | Typed mechanic rulings applied to decisions (§5.1, §5.6) |
| C4 | Seller Hub absorption evidence (§5.4) |
| C5, E2 | Provenance-backed comp integration (§5.3) |
| C7 | Bounded evidence-based challenge (§8.2) |
| C8 | Measured performance (§8.3) |
| C9 | Metered vs estimated cost (§8.4) |
| D1, D2, D3 | Evidence snapshot/claim inventory; rebaseline may close (§9) |
| E1 | Queue risk accounting and release policy (§8.1) |
| F0, F2, F3 | Canonical writer and cycle identity (§4) |
| F1 | Staging, validation, atomic promotion (§4.2, §6) |
| F4 | Facts snapshot consumed by renderers (§9.1) |
| F5, F11, F12 | Validated isolated capture (§6.4, §9.3) |
| F6, F7, F15, F16 | Safe input/image/text boundary (§6.1–§6.2) |
| F8 | Content-addressed retryable comp evidence (§5.3) |
| F9 | Transactional vector/edge cache (§5.5) |
| F10 | Human-approved money-bearing merges (§5.5) |
| F13, F14 | Declared media inputs and probed timing (§9.3) |
| F17 | Reproducible probe inputs/results (§6.5) |
| F18 | Script/artifact integration gates (§6, §11) |
| F19 | Durable source identity, distinct from worker paths (§4.1, §6.1) |
| F20 | Cycle-specific question inputs only (§4.1, §5.1) |
| F21 | Typed, staged canonical pipeline boundaries (§4.4, §6) |

Every TODO in the 2026-08-22 inventory is represented above. Implementation may
close stale items during rebaseline, but it may not silently drop them.
