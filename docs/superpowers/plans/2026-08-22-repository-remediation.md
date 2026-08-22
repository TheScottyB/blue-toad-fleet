# Repository Remediation and Submission Integrity — implementation plan

> **For implementers:** Execute this plan in order. Keep each task independently
> reviewable, run the named tests before moving on, and update `docs/TODO.md` with
> evidence rather than assumption. Checkbox state in this plan tracks execution;
> it does not by itself close the source finding.

**Goal:** Produce one authenticated, evidence-backed, reproducible auction-cycle
pipeline that either atomically publishes a complete reconciled artifact set or
leaves the last known-good cycle untouched. Make every judge-facing claim and
media artifact derive from that published cycle.

**Design:**
`docs/superpowers/specs/2026-08-22-repository-remediation-design.md`

**Baseline:** `8ef89bc` plus the current uncommitted `docs/TODO.md` review.

**Tech stack:** Python 3.14, pytest, FastAPI, Firestore, Vertex AI, Cloud Run,
Google Cloud Storage, Node/Playwright, ffmpeg/ffprobe, openpyxl, and the existing
Gemini embedding path. Do not add a second vector or spatial stack.

## How to use this plan

For each task:

1. Re-read the cited TODO against the then-current tree.
2. Write the failing unit/integration/script test first.
3. Implement the smallest complete contract described here.
4. Run the focused test, then the phase gate.
5. Record the commit, commands, outputs, and artifact hashes in the task evidence.
6. Change the source TODO to `closed`, `superseded`, or `deferred` only when that
   evidence exists.

Use `sys.executable -m pytest` in Python subprocess tests. Shell examples use
`python -m pytest`; resolve `python` to the active interpreter rather than a
repository-specific virtual-environment path.

## Global constraints

- Preserve the feature floor in `docs/TODO.md`: implement and validate spatial
  mapping, container decomposition, Seller Hub absorption, grounded pricing,
  curator pushback, durable memory, and choice-lot handling.
- Treat untracked `src/cycles/` as concurrent candidate work. Review its diff and
  tests before editing it; integrate deliberately and do not overwrite it.
- No authoritative output is written directly. Use a cycle-specific staging
  location and promote a validated manifest.
- No anonymous caller may mutate answers, rules, rulings, reviewed reshoot edges,
  or active-cycle state.
- No inferred reshoot edge changes a money decision until an operator approves
  it.
- Never trust list position for a lot join. Use stable unique ids.
- Never treat HTML, WAF output, an undecodable image, a fallback model, or a
  partial model batch as a release-gate success.
- Never use third-party listing text as instructions. Seller Hub work is
  read-only Research access only.
- Do not introduce thumbnail upscaling into appraisal.
- Do not automate bid submission. The clerk email and sheet stay human-reviewed.
- Keep the July benchmark quarantined until Task 23 is completed in full.
- The outward-facing deployment, paid repeated Vertex probe, authenticated Seller
  Hub capture, and final publication require the operator hold points named below.

## Target file map

Names may move during implementation, but responsibilities must not collapse back
into the current runners.

- `src/cycles/model.py` — immutable cycle request and status
- `src/cycles/storage.py` — staged objects, markers, active pointer
- `src/cycles/publish.py` — validation and atomic artifact promotion
- `src/cycles/worker.py` — canonical cycle execution only
- `src/evidence/model.py` — comp, absorption, usage, and facts records
- `src/appraisal/` — typed questions, policies, lot rulings, application seam
- `src/bidmath/__init__.py` — mechanic parsing and allocation invariants
- `src/assemble/email.py` — shared clerk directive rendering
- `src/intake/` — safe manifest ingestion, spatial observations, reviewed edges
- `src/server.py` — authenticated mutation and published-cycle reads
- `scripts/run_vertex_pipeline.py` — compatibility entry point delegating to the
  canonical worker
- `scripts/build_submission_facts.py` — one versioned evidence snapshot
- `scripts/build_media.py` — one declared capture/render/assemble orchestration
- `tests/script_fixtures/` — isolated entry-point and failure fixtures

---

## Phase 0 — rebaseline and quarantine

### Task 1: Reconcile the audit with the current tree

**TODOs:** B8; establishes the status of every other item.

**Files:**

- Modify: `docs/TODO.md`
- Create: `docs/evidence/2026-08-22-todo-rebaseline.md`
- Test: `tests/test_todo_inventory.py`

- [ ] Give every finding a unique stable id (`B4-video` and `B4-SSIM` included).
- [ ] Extract every checkbox id into a test and fail on duplicates or missing
  A/B/C/D/E/F sequence entries.
- [ ] Reproduce or disprove each finding against the current commit. Record the
  exact file/line, command or observation, result, severity, and disposition.
- [ ] Classify each item as `open`, `closed-with-evidence`, `superseded`, or
  `intentionally-deferred`; do not infer closure from new-looking code.
- [ ] Update stale counts and citations in place instead of appending another
  contradictory note.
- [ ] Add links from `docs/TODO.md` to this plan, the design, and the rebaseline
  evidence.

**Verify:**

```bash
python -m pytest tests/test_todo_inventory.py -v
git diff --check
```

**Done when:** every source TODO has one current verdict and reproducible evidence.

### Task 2: Quarantine invalid July evidence

**TODOs:** B0, F18 (historical corruption coverage).

**Files:**

- Modify: `README.md`
- Modify: `docs/DEVPOST.md`
- Modify: `NOTES.md`
- Modify: `scripts/run_july11_benchmark.py`
- Modify or move: `data/BlueToad_2026-07-11_Benchmark_Comparison.xlsx`
- Test: `tests/test_july_benchmark_quarantine.py`

- [ ] Add tests reproducing the triple-counted legacy total, seven-id collision,
  position-based misjoin, and absent Choice mechanic proof.
- [ ] Remove July totals, savings, timing, and A/B claims from every judged
  artifact until the benchmark satisfies Task 23.
- [ ] Make the existing runner refuse to write a submission artifact and label
  any retained workbook historical/unverified.
- [ ] Replace benchmark-derived persuasion with the independently tested
  all-in-cap invariant where appropriate.
- [ ] Add a submission check that fails if quarantined figures or filenames are
  referenced by judged copy.

**Verify:**

```bash
python -m pytest tests/test_july_benchmark_quarantine.py tests/test_pricing_invariants.py -v
```

**Done when:** no release command or judged artifact treats the current July file
as ground truth.

### Task 3: Restore clean-clone behavior

**TODOs:** B1, B2.

**Files:**

- Modify: `.gitignore`
- Modify: `tests/test_docs_match_the_sheet.py`
- Test: `tests/test_clean_clone_contract.py`

- [ ] Change image ignore rules to ignore directory contents, then explicitly
  re-include the required fixtures.
- [ ] In an isolated temporary index, prove a required image can be removed from
  the index and added again without `-f`.
- [ ] Replace `.venv/bin/pytest` with `sys.executable -m pytest` and derive the
  repository root from the test file location.
- [ ] Run the doc guard from a non-root working directory.
- [ ] Assert no test or release script contains a personal absolute path.

**Verify:**

```bash
python -m pytest tests/test_clean_clone_contract.py tests/test_docs_match_the_sheet.py -v
```

**Phase 0 gate:** the TODO inventory is unique/current, July evidence is
quarantined, and the judge-facing guard runs from a clean-clone-shaped environment.

---

## Phase 1 — cycle ownership and fail-closed publication

### Task 4: Define immutable cycle identity and typed pipeline boundaries

**TODOs:** F2, F20, F21; foundation for F0, F1, F4, B3.

**Files:**

- Review/modify: `src/cycles/model.py`
- Review/modify: `src/cycles/storage.py`
- Review/modify: `src/cycles/jobs.py`
- Review/modify: `src/cycles/worker.py`
- Modify: `scripts/stage_cycle.py`
- Modify: `scripts/run_vertex_pipeline.py`
- Test: `tests/test_cycles.py`
- Test: `tests/test_pipeline_stages.py`

- [ ] First review the untracked `src/cycles/` implementation and record which
  contracts are accepted, changed, or rejected.
- [ ] Extend `CycleRequest` with auction title, date, timezone, venue, deadline,
  budget cap, source-manifest identity, and schema version.
- [ ] Validate `cycle_id`, `listing_id`, and shop/object path components against
  path traversal, empty values, and ambiguous normalization.
- [ ] Derive email subject, filenames, metadata, and object prefixes only from
  the typed request.
- [ ] Add frozen `PipelineConfig` and `PipelineResult` records with `Path` and
  typed mapping fields; replace the seven-value return tuple.
- [ ] Extract intake, appraisal, decision/pricing, and artifact-writing stages.
  Reusable stages raise typed exceptions; a thin `main(argv) -> int` owns
  argument parsing and exit codes.
- [ ] Remove reusable-core `sys.exit`, arbitrary `__dict__` serialization, and
  repository `sys.path` mutation; enable Ruff for the refactored runner.
- [ ] Inject cycle-specific question fixtures through configuration. Generic
  cycles default to none, and the explicit Aug-22 wrapper supplies its historic
  set.
- [ ] Reject any configured question whose lot/cluster id is absent from the
  current cycle.
- [ ] Make two different cycle requests produce disjoint output trees and correct
  auction copy.
- [ ] Refuse execution when required metadata is missing.

**Verify:**

```bash
python -m pytest tests/test_cycles.py tests/test_pipeline_stages.py -v
```

### Task 5: Establish one owner for every authoritative artifact

**TODOs:** F0, F3.

**Files:**

- Modify or retire: `scripts/run_aug22_cycle.py`
- Modify: `scripts/run_vertex_pipeline.py`
- Modify or retire: `scripts/build_video.py`
- Modify: `scripts/assemble_final.py`
- Create: `src/cycles/ownership.py`
- Test: `tests/test_artifact_ownership.py`

- [ ] Enumerate protected paths: cycle state, bid sheet, absentee email, active
  pointer, screenshots, submission facts, and final MP4.
- [ ] Assign exactly one canonical writer to each path.
- [ ] Make legacy entry points delegate to that owner, write clearly historical
  names, or exit with migration guidance.
- [ ] Test that `run_aug22_cycle.py` cannot overwrite the nine-bid authoritative
  sheet/email with its old schedule.
- [ ] Test that the legacy video builder cannot replace the narrated final.
- [ ] Fail CI when a new script claims a protected path directly.

**Verify:**

```bash
python -m pytest tests/test_artifact_ownership.py tests/test_sheet_matches_what_was_sent.py -v
```

### Task 6: Stage, validate, and atomically publish a cycle

**TODOs:** F1, F18, F19.

**Files:**

- Create: `src/cycles/publish.py`
- Modify: `src/cycles/model.py`
- Modify: `src/cycles/storage.py`
- Modify: `src/cycles/worker.py`
- Modify: `scripts/run_vertex_pipeline.py`
- Test: `tests/test_cycle_publication.py`
- Test: `tests/test_script_failures.py`

- [ ] Implement explicit `STAGED`, `RUNNING`, `DEGRADED`, `VALIDATED`,
  `PUBLISHED`, and `FAILED` states with legal transitions.
- [ ] Write every output beneath a run-specific staging prefix/directory.
- [ ] Build `artifact_manifest.json` with request/source/model/rule/evidence/
  decision hashes and per-artifact hash, type, and size.
- [ ] Preserve durable storage-relative/object photo references separately from
  worker-local materialization paths. Never serialize a temporary path as the
  published source identity.
- [ ] Validate exact requested/successful id coverage, required schemas, zero
  required error rows, unique ids, id-based joins, comp provenance, mechanics,
  and budget reconciliation.
- [ ] Promote the complete manifest atomically, then update `ACTIVE`; never
  update `ACTIVE` first.
- [ ] Simulate model exception, partial output, interrupted write, invalid
  workbook, and manifest mismatch. Preserve the last known-good active cycle.
- [ ] Delete the worker temporary directory in an integration test and resolve
  every photo in the published manifest from durable storage afterward.
- [ ] Retain diagnostic artifacts for degraded runs without presenting them as
  final output.

**Verify:**

```bash
python -m pytest tests/test_cycle_publication.py tests/test_script_failures.py -v
```

### Task 7: Secure the source/image/text boundary

**TODOs:** F6, F7, F15, F16.

**Files:**

- Modify: `scripts/cache_gallery.py`
- Modify: `scripts/recache_full_size.py`
- Modify: `scripts/dry_run_single_photo.py`
- Modify: `scripts/test_vertex_live.py`
- Modify: `scripts/build_local_gallery.py`
- Modify: `scripts/build_beat2.py`
- Modify: `src/appraiser/images.py`
- Test: `tests/test_source_integrity.py`
- Test: `tests/test_images.py`

- [ ] Restore default hostname/certificate verification everywhere; support only
  an explicitly configured source CA when needed.
- [ ] Download to a temporary file and validate status, detected MIME from bytes,
  decodability, dimensions, appraisal grade, hash, and safe unique filename.
- [ ] Reject HTML, WAF/challenge output, partial files, and MIME/extension lies.
- [ ] Record per-photo hashes/failures and return non-zero for incomplete requested
  coverage.
- [ ] Decode HTML entities exactly once during manifest ingestion.
- [ ] Escape all third-party caption/path values at each HTML output boundary;
  add ampersand, quote, tag, malformed-text, and path fixtures.
- [ ] Make the live Vertex gate require an appraisal-grade image and exact
  required model; report fallback calls as diagnostics only.

**Verify:**

```bash
python -m pytest tests/test_source_integrity.py tests/test_images.py tests/test_intake.py -v
```

### Task 8: Make embedding regeneration and money-bearing merges reviewable

**TODOs:** F9, F10, E3 (edge safety portion).

**Files:**

- Modify: `scripts/embed_gallery.py`
- Modify: `scripts/list_reshoot_edges.py`
- Modify: `src/intake/embed.py`
- Modify: `src/intake/spatial.py`
- Modify: `scripts/run_vertex_pipeline.py`
- Test: `tests/test_embed_cache.py`
- Test: `tests/test_reshoot.py`

- [ ] Generate the full vector cache and proposed-edge sidecar under temporary
  names with manifest, model, input hashes, and uniform-dimension checks.
- [ ] Swap the mutually consistent pair together only after full coverage passes.
- [ ] Preserve the last known-good pair on missing image, API failure, dimension
  mismatch, or interruption.
- [ ] Introduce reviewed edge records with proposed/approved/rejected status,
  reviewer, timestamp, evidence, and revision.
- [ ] Make production grouping consume approved edges only and fail closed on
  stale model/input/review identities.
- [ ] Add known positive and real-gallery negative pairs; false-positive merges
  must fail the release gate.

**Verify:**

```bash
python -m pytest tests/test_embed_cache.py tests/test_reshoot.py tests/test_lot_grouping.py -v
```

**Phase 1 gate:** two cycles cannot collide; obsolete writers cannot replace
protected artifacts; source inputs are validated; a partial run and unreviewed
merge both fail without changing the active cycle.

---

## Phase 2 — authenticated answers and one money path

### Task 9: Verify fail-closed auth and harden durable operator mutations

**TODOs:** B6.

**Files:**

- Modify: `src/server.py`
- Modify: `src/gate/render.py`
- Modify: `infra/deploy.sh`
- Modify: `src/memory/firestore.py`
- Test: `tests/test_server.py`
- Test: `tests/test_answer_auth.py`

- [ ] First reproduce the current B6 closure: absent production configuration
  returns 503, a wrong token returns 401, the authorized path succeeds, and no
  denied request changes durable state.
- [ ] Verify the console accepts the operator token at runtime for Answer and
  cycle-start actions and never embeds it in generated HTML.
- [ ] For the immediate release, retain the fail-closed server-configured token
  only if its deployment/configuration tests pass. Otherwise choose Cloud Run
  IAM/IAP or an authenticated server-side session and document the local/test
  equivalent.
- [ ] Record identity-backed auth as the preferred follow-up if the shared-token
  release contract is accepted; do not reopen B6 without contrary evidence.
- [ ] Keep read-only demo routes public only if desired; deny anonymous answer,
  policy, ruling, review, and publish mutations.
- [ ] Record authenticated actor identity on every durable mutation.
- [ ] Add optimistic concurrency and return 409 for stale question/rule revisions.
- [ ] Make the shipped UI use the supported session without embedding a long-lived
  secret in JavaScript or HTML.
- [ ] Test anonymous denial with zero state change, authorized success, stale
  conflict, expired session, and UI mutation.

**Verify:**

```bash
python -m pytest tests/test_answer_auth.py tests/test_server.py -v
```

### Task 10: Split standing policy from lot/cycle rulings

**TODOs:** A7; prerequisite for A6 and C3.

**Files:**

- Modify: `src/appraisal/__init__.py`
- Modify: `src/memory/store.py`
- Modify: `src/memory/firestore.py`
- Modify: `src/memory/ids.py`
- Modify: `src/server.py`
- Test: `tests/test_appraisal.py`
- Test: `tests/test_memory.py`
- Test: `tests/test_rule_scope.py`

- [ ] Define `StandingPolicy` for genuinely category-wide policy/appetite and
  `LotRuling` for cycle-specific grouping/scope/mechanic/condition decisions.
- [ ] Key lot rulings by shop, cycle, stable lot or cluster id, kind, and revision.
- [ ] Preserve source question, actor, timestamps, and typed payload.
- [ ] Migrate or explicitly reject ambiguous legacy records; never silently
  promote a cluster answer into category memory.
- [ ] Prove a ruling for trays 12/14/16 cannot suppress or authorize an unrelated
  jewelry lot in the same or future cycle.

**Verify:**

```bash
python -m pytest tests/test_rule_scope.py tests/test_memory.py tests/test_appraisal.py -v
```

### Task 11: Correct mechanic parsing and implausible counts

**TODOs:** A1, A4.

**Files:**

- Modify: `src/bidmath/__init__.py`
- Modify: `tests/test_ruling_to_mechanic.py`
- Modify: `tests/test_elective_quantity.py`

- [ ] Add the operator's exact phrase, “do not limit me to one unit,” as a
  TIMES_THE_MONEY regression.
- [ ] Scope negation to the mechanic assertion itself (for example, “not an x3
  bid”) instead of rejecting a bare `not` anywhere.
- [ ] Define one policy for implausible multiplier and election counts: refuse
  the affected ruling consistently rather than discarding one field.
- [ ] Cover contradictory text, unknown mechanic, plausible upper bounds, and
  `units_available` interactions.

**Verify:**

```bash
python -m pytest tests/test_ruling_to_mechanic.py tests/test_elective_quantity.py tests/test_bid_mechanics.py -v
```

### Task 12: Unify clerk instructions and exposure accounting

**TODOs:** A2, A3, A5.

**Files:**

- Modify: `src/bidmath/__init__.py`
- Modify: `src/assemble/email.py`
- Modify: `src/gate/render.py`
- Modify: `scripts/run_vertex_pipeline.py`
- Test: `tests/test_absentee_email.py`
- Test: `tests/test_bidmath.py`

- [ ] Make `clerk_directive(decision)` the only semantic instruction generator
  used by console and email.
- [ ] Represent instruction semantics as a structured tuple/object, with output
  formatting layered above it.
- [ ] Ensure a remainder opportunity says “only if it comes back up” and can
  never render as a firm all-units bid.
- [ ] Separate committed and contingent exposure in allocation and summaries;
  contingent decisions do not consume committed cap headroom.
- [ ] Give `remainder_opportunity` and `elect` intentional production callers or
  remove their public/test-only contracts.
- [ ] Assert console and email parse to the same instruction for every mechanic,
  refusal, election, and contingent state.

**Verify:**

```bash
python -m pytest tests/test_absentee_email.py tests/test_bidmath.py tests/test_choice_lot.py -v
```

### Task 13: Apply answers through grouping, appraisal, pricing, and artifacts

**TODOs:** A6, C3, D2.

**Files:**

- Modify: `src/appraisal/__init__.py`
- Modify: `src/server.py`
- Modify: `src/cycles/worker.py`
- Modify: `src/assemble/email.py`
- Modify: `scripts/run_vertex_pipeline.py`
- Test: `tests/test_answer_application.py`
- Test: `tests/test_choice_lot.py`

- [ ] Create a typed application seam that consumes current policy and lot
  rulings before grouping/mechanic/pricing/allocation.
- [ ] Recompute every affected downstream decision, then stage replacement
  sheet, email, console facts, and state from one snapshot.
- [ ] Return an explicit before/after decision diff; report pending work only when
  a real followable job was queued.
- [ ] Generalize choice/times-money fields beyond `OPERATOR_APPROVED` hard-coded
  records.
- [ ] Add an end-to-end BT-002 fixture: three trays -> question -> x3 ruling ->
  TIMES_THE_MONEY -> $75 committed max -> matching clerk line.
- [ ] Add a second test where an answer changes committed money and a failed
  recomputation leaves the published cycle untouched.

**Verify:**

```bash
python -m pytest tests/test_answer_application.py tests/test_choice_lot.py tests/test_server.py -v
```

**Phase 2 gate:** anonymous writes fail; lot rulings cannot leak by category; the
operator phrase parses correctly; console/email agree; an authenticated answer
changes a tested money decision through a validated replacement snapshot.

---

## Phase 3 — evidence-backed feature floor

### Task 14: Create provenance-backed, retryable comp evidence

**TODOs:** C5, E2, F8.

**Files:**

- Create: `src/evidence/model.py`
- Modify: `src/appraiser/pricing.py`
- Modify: `src/appraiser/engine.py`
- Modify: `scripts/run_grounded_pricing.py`
- Modify: `src/server.py`
- Modify: `src/cycles/worker.py`
- Test: `tests/test_comp_evidence.py`
- Test: `tests/test_pricing.py`

- [ ] Define usable/refused/transient-failure evidence with method, citations,
  sold-comp count, identification/image/input/model/prompt/policy hashes, attempts,
  and timestamps.
- [ ] Keep successful evidence separate from attempt history. Retry transient
  failures and invalidate on any decision-bearing fingerprint change.
- [ ] Use temporary write plus atomic replace for local caches and equivalent
  generation/versioning in object storage.
- [ ] Convert only usable grounded rows into `CompEstimate`; distinguish
  `grounded_search` from `operator_reference` in state, sheet, and console.
- [ ] Refuse allocation when required comp evidence is absent rather than using
  an unlabeled value-magnitude prior.
- [ ] Show coverage and refusal reasons, including BT-002/BT-087, in the cycle
  snapshot.
- [ ] Prove one grounded result reaches `price_lot`, allocation, email, and
  artifact provenance end to end.

**Verify:**

```bash
python -m pytest tests/test_comp_evidence.py tests/test_pricing.py tests/test_live_cache_parity.py -v
```

### Task 15: Account for every triage question

**TODOs:** E1.

**Files:**

- Modify: `src/appraisal/__init__.py`
- Modify: `src/cycles/publish.py`
- Modify: `src/server.py`
- Test: `tests/test_question_coverage.py`

- [ ] Record asked, auto-answered, deferred, dropped, and affected lot ids before
  applying the desk cap.
- [ ] Classify whether each question can affect grouping, mechanic, identity,
  comp, or allocation.
- [ ] Define the release rule: an unresolved/dropped money-bearing question makes
  its affected lot refuse or blocks publication; low-impact deferrals remain
  visible.
- [ ] Surface totals and affected lots in the API and submission facts.
- [ ] Re-evaluate the reported 148 dropped questions under the new policy.

**Verify:**

```bash
python -m pytest tests/test_question_coverage.py tests/test_appraisal.py -v
```

### Task 16: Wire the Spatial Room Graph into production conservatively

**TODOs:** C1, C6, E3.

**Files:**

- Modify: `src/intake/spatial.py`
- Modify: `src/intake/manifest.py`
- Modify: `src/assemble/__init__.py`
- Modify: `src/server.py`
- Modify: `scripts/run_vertex_pipeline.py`
- Modify: `src/gate/render.py`
- Test: `tests/test_spatial.py`
- Test: `tests/test_reshoot.py`
- Test: `tests/test_corpus.py`

- [ ] Keep `gemini-embedding-2` and approved reviewed edges as the non-adjacent
  duplicate mechanism; do not add dHash or upscaling.
- [ ] Define validated observation inputs for listing, surface signature,
  co-visibility, adjacency, trajectory, occupancy, and zone assignment.
- [ ] Give `apply_trajectory`, `adjacency_graph`, surfaces, zones, and occupancy
  non-test production callers before rendering physical claims.
- [ ] Keep evidence-free seats in `Zone.UNKNOWN`; never derive a physical zone
  from category or persuasive copy.
- [ ] Verify known loops 1↔284, 26↔455, 15↔404, and 2↔181 plus negative pairs,
  no approved false merge, and one seat/decision representation per lot.
- [ ] Rebaseline corpus totals after approved merges and feed them to the facts
  snapshot rather than hard-coded copy.

**Verify:**

```bash
python -m pytest tests/test_spatial.py tests/test_reshoot.py tests/test_corpus.py tests/test_assemble.py -v
```

### Task 17: Complete bounded container decomposition

**TODOs:** C2.

**Files:**

- Review/modify: `src/appraiser/containers.py`
- Modify: `src/appraiser/engine.py`
- Modify: `src/appraiser/schema.py`
- Modify: `src/appraiser/pricing.py`
- Test: `tests/test_container_decomposition.py`

- [ ] Review the concurrent container implementation before changing it.
- [ ] Preserve two-stage locate -> crop -> itemize with explicit evidence and
  model-call failure handling.
- [ ] Confirm an alpha only when its mark is observed and no determining mark
  question remains open.
- [ ] Price confirmed alpha plus bulk floor; otherwise bid the bulk floor and
  label the alpha as upside, never as committed value.
- [ ] Add the empirically unreadable bulk-tray hallmark fixture and require the
  honest unconfirmed path.
- [ ] Add decomposition coverage/provenance to the publication gate.

**Verify:**

```bash
python -m pytest tests/test_container_decomposition.py tests/test_engine.py tests/test_pricing.py -v
```

### Task 18: Import verified Seller Hub absorption evidence

**TODOs:** C4.

**Operator hold point:** authenticated browser research is read-only and requires
the operator's active seller session. Never navigate to or act in Listings,
Orders, Marketing, Payments, or Messages.

**Files:**

- Create: `scripts/import_ebay_absorption.py`
- Create/modify: `src/evidence/model.py`
- Modify: `docs/PLAYBOOK-ebay-velocity.md`
- Modify: `src/cycles/worker.py`
- Test: `tests/test_ebay_absorption.py`

- [ ] Define an import/capture contract containing query, exact displayed date
  window, sold units, active listings, pagination/page counts, captures/rows,
  timestamps, source account, and reviewer.
- [ ] Verify the displayed results date line; do not trust `dayRange` or dropdown
  label alone.
- [ ] Sum `Total sold` units instead of counting rows, keep SOLD pages at the
  supported limit, and stop only on a verified terminal short page/state.
- [ ] Compute only `sold_units_last_365_days / active_listings_now`; do not add
  days-on-market.
- [ ] Validate the committed Boston Champion evidence (295 sold units, 138
  active, 2.14 absorption) from its source captures before using it as a fixture.
- [ ] Attach the evidence revision to the cycle; missing/stale evidence produces
  “unavailable,” not a fit-score proxy.

**Verify:**

```bash
python -m pytest tests/test_ebay_absorption.py -v
```

### Task 19: Add bounded evidence-based curator pushback

**TODOs:** C7.

**Files:**

- Modify: `src/gate/pitch.py`
- Modify: `src/gate/voice.py`
- Modify: `src/gate/render.py`
- Create: `src/gate/challenge.py`
- Test: `tests/test_pitch.py`
- Test: `tests/test_voice.py`

- [ ] Define deterministic `ChallengeFacts` with exact SKIP rule, matched lot,
  current decision, sourced comp/absorption evidence, allowed figures, and
  citations.
- [ ] Select challenges deterministically; the language model may phrase only
  the supplied facts.
- [ ] Refuse/hide the challenge when any required fact is missing or stale.
- [ ] Test that invented lots, figures, margins, velocity, and unsupported BUY
  recommendations cannot pass schema/renderer validation.

**Verify:**

```bash
python -m pytest tests/test_pitch.py tests/test_voice.py tests/test_gate.py -v
```

### Task 20: Meter performance and cycle cost

**TODOs:** C8, C9.

**Files:**

- Modify: `src/appraiser/routing.py`
- Modify: `src/appraiser/engine.py`
- Modify: `src/cycles/worker.py`
- Modify: `src/evidence/model.py`
- Test: `tests/test_usage_telemetry.py`

- [ ] Record stage start/end/duration plus per-call stage, model, usage units,
  input/output tokens where available, retry, fallback, and latency.
- [ ] Aggregate triage, appraisal, decomposition, grounding, embeddings, curator,
  and failed/retried calls by cycle.
- [ ] Label static rate multiplication as `estimate`; label measured usage/cost
  separately and record the rate snapshot used.
- [ ] Benchmark the real full-corpus triage path. If sequential context remains,
  report measured time; parallelize only after adjacency/grouping recall tests
  pass for bounded chunks.
- [ ] Feed measured duration/cost status into submission facts.

**Verify:**

```bash
python -m pytest tests/test_usage_telemetry.py tests/test_engine.py -v
```

**Phase 3 gate:** every allocated lot has usable labeled comp evidence, question
risk is accounted for, spatial/container decisions are evidence-bounded, Seller
Hub absorption is verified when present, curator prose cannot exceed its facts,
and performance/cost labels distinguish measured values from estimates.

---

## Phase 4 — reproducible proof, facts, capture, and media

### Task 21: Generate one submission facts snapshot and claim inventory

**TODOs:** B7, D1, D2, D3, F4.

**Files:**

- Create: `scripts/build_submission_facts.py`
- Create: `docs/SUBMISSION_CLAIMS.md`
- Create: `tests/test_submission_facts.py`
- Modify: `scripts/build_beat2.py`
- Modify: `scripts/make_title_cards.mjs`
- Modify: `scripts/generate_architecture_diagram.py`

- [ ] Generate a versioned `submission_facts.json` from the published artifact
  manifest, decision snapshot, evidence records, runtime, and test collector.
- [ ] Include source hashes for photo/group/merge/appraisal/bid/refusal counts,
  committed max/all-in, resale range/return multiple, runtime/model/backend,
  tests collected/passed/skipped, measured duration/cost, and feature evidence
  status.
- [ ] Derive resale return once from the same decision path; do not hand-type the
  $316.25 / $713–$879 / 2.25x–2.78x example into renderers.
- [ ] Represent the Vertex grounding two-call discovery and BT-002 answer-to-money
  story with code/test/evidence citations.
- [ ] Inventory every claim in README, DEVPOST, video script/narration, blog,
  social post, architecture diagram, title cards, screenshots, and video.
- [ ] Make renderers require the facts snapshot and fail on missing, stale, or
  manifest-mismatched facts; remove all numeric fallback prose.

**Verify:**

```bash
python -m pytest tests/test_submission_facts.py tests/test_docs_match_the_sheet.py -v
```

### Task 22: Make capability probes reproducible and validate SSIM

**TODOs:** B4-SSIM, B5, F17.

**Operator hold point:** the repeated appraisal arms spend Vertex quota. The
zero-tolerance no-upscaling decision does not wait on a fabrication-rate estimate.

**Files:**

- Modify: `scripts/probes/task3_baselines.py`
- Modify: `scripts/probes/rescore_upscaling.py`
- Modify: `artifacts/signature_upscale_probe/`
- Modify: `docs/CAPABILITY_PROBE.md`
- Test: `tests/test_capability_probes.py`

- [ ] Consume the committed embedding JSON or a documented conversion, not an
  uncommitted NPZ.
- [ ] Commit redistributable probe inputs or document a hash-verified fetch recipe
  plus generation metadata for restricted/model-created artifacts.
- [ ] Compare the hand-rolled SSIM against one known reference implementation or
  fixture with declared tolerance.
- [ ] Generate report tables from machine-readable results and input hashes.
- [ ] With operator approval, run roughly 27 randomized appraisal-tier arms and
  report field-level exact-match/fabrication rate, model, prompt, temperature,
  ordering, and failures.
- [ ] Preserve the “no generative upscaling in the decision path” gate regardless
  of the measured rate.

**Verify:**

```bash
python -m pytest tests/test_capability_probes.py -v
```

### Task 23: Rebuild the July benchmark only if it remains a submission feature

**TODOs:** B0 (optional rebuild branch).

**Files:**

- Modify: `scripts/run_july11_benchmark.py`
- Regenerate: `data/BlueToad_2026-07-11_Benchmark_Comparison.xlsx`
- Modify only after validation: `README.md`, `docs/DEVPOST.md`, `NOTES.md`
- Test: `tests/test_july_benchmark.py`

- [ ] Decide explicitly: remove permanently, or rebuild. Removal closes this task
  once Task 2 evidence proves all downstream references are gone.
- [ ] For rebuild, commit the legal legacy input or a hash-verified recipe.
- [ ] Select true item rows, exclude totals/subtotals, remove corrupt fallbacks,
  and use stable unique ids.
- [ ] Run the current grouping/evidence/mechanic/pricing/allocation pipeline.
- [ ] Join outputs to inputs by id after allocation and validate every detail row.
- [ ] Prove Choice behavior from typed state and label any synthetic input.
- [ ] Measure operator review time under a declared protocol or omit the claim.
- [ ] Regenerate the workbook and copy only after all corruption regressions pass.

**Verify:**

```bash
python -m pytest tests/test_july_benchmark.py tests/test_pricing_invariants.py -v
```

### Task 24: Make screenshot and recording capture isolated and fail-closed

**TODOs:** F5, F11, F12.

**Files:**

- Modify: `scripts/cdp_capture.py`
- Modify: `scripts/capture_raw_gallery.mjs`
- Modify: `scripts/capture_screenshots.mjs`
- Modify: `scripts/record_walkthrough.mjs`
- Modify: `scripts/record_gallery.mjs`
- Modify: `scripts/record_beat2.mjs`
- Modify: `scripts/record_terminal.mjs`
- Test: `tests/test_capture_scripts.py`

- [ ] Capture to isolated run-specific temporary directories.
- [ ] Bind each Playwright output to that page's video handle/path; never select
  the newest anonymous WebM from a shared directory.
- [ ] Validate final URL, title, HTTP status, expected body markers, absence of
  sign-in/CAPTCHA/challenge markers, and artifact type before atomic rename.
- [ ] Close pages/tabs/contexts in `finally`.
- [ ] Fingerprint/rebuild local gallery input per manifest; never reuse a global
  `/tmp/gallery_local.html` by existence alone.
- [ ] Require every requested anchor/screenshot and exit non-zero on missing,
  stale, challenged, or invalid output.
- [ ] Prove a challenge page and interrupted capture preserve an existing valid
  screenshot.

**Verify:**

```bash
python -m pytest tests/test_capture_scripts.py -v
```

### Task 25: Build one declared, duration-probed media pipeline

**TODOs:** F3, F13, F14, F18.

**Files:**

- Create: `scripts/build_media.py`
- Modify: `scripts/build_beat2.py`
- Modify: `scripts/build_terminal_replay.py`
- Modify: `scripts/assemble_final.py`
- Retire/delegate: `scripts/build_video.py`
- Create: `media/build-manifest.json`
- Test: `tests/test_media_pipeline.py`

- [ ] Declare deterministic producers for beat JSON, terminal replay JSON, beat
  videos, narration, cards, captures, final output, and their source hashes.
- [ ] Replace undocumented global `/tmp` inputs with a run-specific build
  directory managed by the orchestration command.
- [ ] Probe narration/video duration with ffprobe, validate beat boundaries, and
  permit only a declared final-frame pad tolerance.
- [ ] Validate audio stream, dimensions, duration, codec/container readability,
  maximum size, facts snapshot identity, and all input hashes.
- [ ] Atomically replace `media/blue_toad_fleet_demo.mp4` only after every check
  passes; preserve the prior final on any failure.
- [ ] Add script tests for missing producer, silent video, short footage, stale
  facts, concurrent/leftover recordings, and interrupted final write.

**Verify:**

```bash
python -m pytest tests/test_media_pipeline.py tests/test_artifact_ownership.py -v
```

### Task 26: Freeze copy and re-record the current demo

**TODOs:** B4-video, B7.

**Operator hold point:** narration and final visual approval.

**Files:**

- Modify: `README.md`
- Modify: `docs/DEVPOST.md`
- Modify: `docs/VIDEO_SCRIPT.md`
- Modify: `docs/blog/index.html`
- Modify: `docs/blog/SOCIAL_POST.md`
- Modify: `NOTES.md`
- Regenerate: `docs/architecture_diagram.png`
- Regenerate: `media/cards/`
- Regenerate: `docs/screenshots/`
- Regenerate: `media/blue_toad_fleet_demo.mp4`

- [ ] Resolve every claim-inventory row against validated evidence without
  lowering the required feature floor.
- [ ] Freeze the generated facts snapshot and all prose before recording.
- [ ] Generate diagram, cards, and screenshots from the same facts/manifest.
- [ ] Re-record Beat 4 and any other narration that contains stale lot, dollar,
  test, runtime, map, timing, or feature statements.
- [ ] Assemble through Task 25 only and review the final audiovisual cut end to
  end.
- [ ] Confirm the spoken, on-screen, Markdown, HTML, sheet, email, console, and
  live API facts all reconcile to the same artifact manifest.

**Verify:**

```bash
python -m pytest tests/test_submission_facts.py tests/test_docs_match_the_sheet.py tests/test_media_pipeline.py -v
```

**Phase 4 gate:** all proof is reproducible from declared inputs; invalid capture
cannot overwrite valid evidence; one facts snapshot drives every mutable figure;
the final MP4 has one owner and matches the published cycle.

---

## Phase 5 — release verification and deployment

### Task 27: Run the full clean-clone and destructive-entry-point gate

**TODOs:** F18; final validation of all A–F closures.

**Files:**

- Modify: `Makefile`
- Modify: `tests/test_runtime_deps_are_declared.py`
- Create/modify: `tests/test_release_gate.py`
- Modify: `docs/TODO.md`

- [ ] Provide one release command that runs unit, integration, script, clean-clone,
  artifact, claim, capture, and media checks without live mutation.
- [ ] Run destructive/evidence-producing entry points against injected temporary
  output roots.
- [ ] Assert unique ids; no publish on partial failure; last-known-good
  preservation; correct failure exit codes; and one writer per protected path.
- [ ] Run a representative staged cycle that either publishes a complete
  reconciled artifact set or fails without changing `ACTIVE`.
- [ ] Verify every allocated lot has usable provenance, resolved mechanic, and no
  unresolved money-bearing question.
- [ ] Generate a release report with commit, interpreter/dependencies, commands,
  test counts, artifact manifest, and hashes.
- [ ] Update TODO status only from that evidence and leave any operator-dependent
  item visibly pending.

**Verify:**

```bash
python -m pytest -q
make release-check
git diff --check
```

### Task 28: Deploy the validated revision and verify live parity

**TODOs:** B3.

**Operator hold point:** Cloud Run deployment is outward-facing and requires the
operator's approval after Task 27 passes.

**Files:**

- Modify as needed: `infra/deploy.sh`
- Modify: `docs/evidence/RELEASE.md`

- [ ] Deploy only the commit/artifact manifest from Task 27 using the authenticated
  mutation configuration from Task 9.
- [ ] Verify health reports the expected commit, runtime, memory backend, and
  active artifact-manifest identity.
- [ ] Verify anonymous read behavior and anonymous mutation denial.
- [ ] Exercise one authenticated non-destructive answer test against a dedicated
  test cycle, then verify the audited before/after diff and publication behavior.
- [ ] Compare live API/console totals and claims to the frozen facts snapshot.
- [ ] Record revision URL/id, timestamps, smoke results, and rollback target.
- [ ] Roll back if any live fact, auth, or artifact identity diverges.

**Verify:**

```bash
./infra/deploy.sh
make verify-live
```

### Task 29: Final operator sign-off and submission lock

**TODOs:** closes the release workflow after all technical TODOs are evidenced.

- [ ] Operator approves the clerk email and bid sheet.
- [ ] Operator approves every money-bearing reshoot edge/review revision.
- [ ] Operator approves the claim inventory, screenshots, narration, and final
  video.
- [ ] Confirm July quarantine/removal or rebuilt-benchmark decision.
- [ ] Confirm optional paid probe disposition is accurately labeled.
- [ ] Hash the final release artifacts and attach them to the published manifest.
- [ ] Mark the release tag/commit and prevent post-approval renderers from using a
  different facts snapshot.
- [ ] Record remaining intentionally deferred items with owner, consequence, and
  non-claim boundary.

**Final done condition:** all P0/P1 money, auth, publication, and evidence-integrity
items are closed; every remaining feature-floor claim is implemented and
validated; the deployed app and judged artifacts resolve to one approved manifest.

---

## TODO-to-task index

Duplicate B4 identifiers are normalized to `B4-video` and `B4-SSIM`.

| TODO | Execution task(s) |
|---|---|
| A1 | 11 |
| A2 | 12 |
| A3 | 12 |
| A4 | 11 |
| A5 | 12 |
| A6 | 13 |
| A7 | 10 |
| B0 | 2, 23 |
| B1 | 3 |
| B2 | 3 |
| B3 | 28 |
| B4-video | 26 |
| B4-SSIM | 22 |
| B5 | 22 |
| B6 | 9 |
| B7 | 21, 26 |
| B8 | 1 |
| C1 | 16 |
| C2 | 17 |
| C3 | 13 |
| C4 | 18 |
| C5 | 14 |
| C6 | 16 |
| C7 | 19 |
| C8 | 20 |
| C9 | 20 |
| D1 | 21 |
| D2 | 13, 21 |
| D3 | 21 |
| E1 | 15 |
| E2 | 14 |
| E3 | 8, 16 |
| F0 | 5 |
| F1 | 6 |
| F2 | 4 |
| F3 | 5, 25 |
| F4 | 21 |
| F5 | 24 |
| F6 | 7 |
| F7 | 7 |
| F8 | 14 |
| F9 | 8 |
| F10 | 8 |
| F11 | 24 |
| F12 | 24 |
| F13 | 25 |
| F14 | 25 |
| F15 | 7 |
| F16 | 7 |
| F17 | 22 |
| F18 | 2, 5, 6, 25, 27 |
| F19 | 6 |
| F20 | 4 |
| F21 | 4, 27 |

No source TODO is intentionally omitted. Task 1 may close stale findings with
evidence, but later tasks must not silently rely on a stale closure.
