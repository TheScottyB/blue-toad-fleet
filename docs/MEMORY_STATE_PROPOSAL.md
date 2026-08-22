# Proposal: Durable Memory and Reviewable Auction State

**Status:** Proposed  
**Scope:** Submission-focused hardening before the All Things Agentic deadline  
**Decision requested:** Approve a narrow Firestore-backed memory layer and a real operator-feedback path; keep the purpose-built Google GenAI SDK loop and do not add ADK.

## Executive summary

Blue Toad Fleet already has a strong memory *model*: operator answers become typed `StandingRule` values, matching questions are answered automatically in later cycles, object-specific uncertainty remains visible, and the queue converges without pretending every unknown has been learned away.

The deployed service does not yet give that model durable state. New rules are stored in a process-global Python dictionary, disappear when a Cloud Run instance restarts, can diverge across instances, and are not tied to an authenticated operator or an audit record. The visible Gate Console also renders answer buttons that do not submit answers. Finally, the appraisal cache is unaware of prompt, model, image, or rule changes, so a newly learned rule can coexist with a stale appraisal.

This proposal closes those gaps with the smallest architecture that makes the submission claim literal:

1. Store cross-cycle standing rules and their history in Firestore.
2. Address answers by a stable question ID and accept only questions the current cycle actually asked.
3. Wire the Gate Console's Answer action to the real API.
4. Recompute the affected lots after an answer and fingerprint cached appraisals against their actual inputs.
5. Display an evidence trail: what was learned, when, from which question, and what changed downstream.

The deterministic queue, pricing, allocation, and clerk-instruction code remains unchanged. ADK, vector search, generalized self-modifying agents, and a broad platform rewrite are explicitly out of scope.

## Why this work matters for the submission

The submission is scored 30% on architectural discipline and 30% on demo and production readiness. The existing keyed-memory design is easy to explain and extensively tested, but a judge can reasonably ask two questions that the deployed service cannot answer today:

* “Will the agent remember this after Cloud Run restarts?”
* “Can I press Answer and watch that memory change the resulting work?”

The proposed change produces a defensible yes to both while strengthening the existing Collaborative Partner story. It does not create a second product narrative. The auction workflow remains the feature; persistence and provenance make it credible.

## Current state

### What is already strong

* `StandingRule` is a typed domain value keyed by `(QuestionKind, category)`.
* `build_queue` deterministically groups, ranks, caps, auto-answers, drops, and defers questions.
* `learn` distinguishes reusable conventions from object-specific facts.
* Standing rules are injected into later Gemini appraisal prompts.
* Deferred questions continue to flag affected lots rather than silently disappearing.
* The two-cycle demonstration proves that the clarification queue settles instead of oscillating or collapsing dishonestly.
* The costume-jewelry A/B run demonstrates that an operator rule can move `fit_score` from `0.2` to `0.85` and change the bid gate.

### Gaps to close

| Area | Current behavior | Risk |
|---|---|---|
| Persistence | Rules live in module-level `STATE` | Restart or redeploy loses new memory |
| Scale-out | Each Cloud Run process owns a separate list | Concurrent instances can disagree |
| Provenance | Seed rules are hardcoded and answers overwrite by key | No durable account of who taught what or why |
| Validation | `/api/answer` accepts raw kind/category/answer | A caller can teach a rule for a question the system never asked |
| Generalization | The API creates a rule even when `learn()` rejects it | Object-specific marks or condition can become unsafe global memory |
| Cache validity | Cache checks presence and lot coverage | Stale results can survive model, prompt, image, schema, or memory changes |
| User interface | Answer/Skip controls are static HTML | The visible collaboration loop is not operable |
| Decision propagation | Normal console requests reuse cached appraisals | A new answer does not visibly produce a new sheet decision end to end |
| Isolation | One global state is shared by every caller | No operator, shop, or cycle boundary |

## Proposed design

### 1. Keep memory, cycle state, and artifacts separate

These concepts have different lifetimes and should not share one global dictionary.

| State class | Examples | Lifetime | Authority |
|---|---|---|---|
| Cross-cycle memory | Shop appetite, house grouping convention, risk policy | Multiple auctions | Operator-approved rule store |
| Active-cycle state | Listing, budget, questions, answers, approval status | One auction cycle | Cycle record |
| Reproducibility artifacts | Triage, appraisal, grounding results, image hashes | One input/version fingerprint | Immutable or replace-on-refresh cache |

The pure domain functions continue to accept ordinary Python values. Persistence stays behind small repository interfaces so unit tests do not require Google Cloud.

```python
class RuleStore(Protocol):
    def active_rules(self, shop_id: str) -> list[StandingRule]: ...
    def put(self, rule: StandingRuleRecord, expected_revision: int | None) -> None: ...
    def history(self, shop_id: str, rule_key: str) -> list[RuleEvent]: ...

class CycleStore(Protocol):
    def get(self, cycle_id: str) -> CycleState: ...
    def record_answer(self, cycle_id: str, answer: AnswerRecord) -> None: ...
```

Implementations:

* `InMemoryRuleStore` and `InMemoryCycleStore` for unit tests.
* `FileRuleStore` for the credential-free local demonstration.
* `FirestoreRuleStore` and `FirestoreCycleStore` when `GOOGLE_CLOUD_PROJECT` and the deployment configuration select Cloud state.

### 2. Use a deliberately small Firestore schema

```text
shops/{shop_id}
  rules/{rule_id}
  rule_events/{event_id}

cycles/{cycle_id}
  questions/{question_id}
  answers/{answer_id}
```

`rules/{rule_id}`:

```json
{
  "shop_id": "richmond-general",
  "kind": "appetite",
  "category": "jewelry",
  "answer": "BUY — bulk estate costume jewelry moves in the storefront",
  "learned_cycle": "2026-08-22",
  "source_question_id": "q_…",
  "active": true,
  "revision": 3,
  "created_at": "server timestamp",
  "updated_at": "server timestamp",
  "review_after": null
}
```

`rule_id` is the SHA-256 digest of the canonical `shop_id + kind + normalized_category` key. The readable fields remain in the document, while the deterministic ID prevents duplicate active rules during concurrent writes.

Every create, replace, or revoke operation also appends a `rule_event`. History is never inferred from the current record.

### 3. Make generalization policy explicit

Only these answer kinds may become cross-cycle standing rules:

* `policy`
* `lot_grouping`
* `scope`
* `appetite`

`mark` and `condition` answers are observations about specific objects. They may be attached to their affected lot for the current cycle, but they must never be promoted to category-wide memory.

Rules also need different review behavior:

* House grouping and scope conventions remain active until revoked.
* Inventory appetite and risk policy may carry `review_after` because “the tool backlog is full” is not necessarily permanent.

The API must call the domain policy once and return a clear non-promotion result when an answer is cycle-specific. It must not manufacture a `StandingRule` after `learn()` rejects one.

### 4. Address real questions, not caller-supplied categories

Replace the current answer contract:

```json
{ "kind": "appetite", "category": "jewelry", "answer": "BUY" }
```

with:

```json
{
  "question_id": "q_4f2…",
  "answer": "BUY — bulk estate costume jewelry moves in the storefront",
  "expected_revision": 2
}
```

A stable question ID is derived from cycle, kind, normalized category, cluster, affected lot IDs, and question-schema version. The server loads the question, verifies that it belongs to the active cycle and is answerable, records the answer, and then applies the domain promotion policy.

This prevents arbitrary rules from being injected and provides an exact provenance link between question, answer, and memory.

### 5. Make the appraisal cache depend on its inputs

For each appraisal, calculate a fingerprint over:

* model and endpoint;
* system-prompt and response-schema hashes;
* image SHA-256;
* caption and category hint;
* container-decomposition hash, when present;
* canonical active standing rules relevant to the lot;
* application cache-schema version.

```text
appraisal_fingerprint = sha256(canonical_json(all_inputs_above))
```

A cached result is reusable only when its fingerprint matches. Lot-ID coverage remains a necessary batch check, but it is no longer treated as proof that the contents are current.

When an answer is stored, affected lots are re-appraised with that rule set or marked pending if Vertex AI is unavailable. Pricing and allocation then rerun from the resulting appraisals. The response reports the before/after result instead of returning only `status: learned`.

### 6. Wire the Gate Console to the real flow

The console should support one narrow interaction:

1. Select a question.
2. Enter or choose the operator answer.
3. Submit to the same-origin answer endpoint.
4. Show `saving → learned → re-appraising → recalculated` states.
5. Display the resulting rule, affected lots, and before/after bid outcome.

The public hosted console remains readable without credentials. Mutating endpoints require an operator credential; CORS is restricted to the service origin. For the single-operator submission, an operator token entered for the browser session and validated server-side is sufficient. Store the deployment secret in Google Secret Manager and never embed it in rendered HTML or repository files.

## End-to-end transaction

```text
Gemini emits an answerable question
            ↓
Queue assigns a stable question ID and persists it for the cycle
            ↓
Operator answers the actual question in the Gate Console
            ↓
Server validates cycle, question, actor, and expected revision
            ↓
Answer is stored; reusable answer becomes a versioned StandingRule
            ↓
Affected appraisal fingerprints change
            ↓
Affected lots are re-appraised, repriced, and reallocated
            ↓
Console shows the before/after decision and durable audit evidence
```

If re-appraisal fails, the answer and rule remain recorded, the prior sheet remains intact, and the affected lots show `pending_reappraisal`. A failed model call must never partially overwrite a known-good bid sheet.

## API response and audit evidence

The answer endpoint should return enough evidence for the UI and tests:

```json
{
  "status": "applied",
  "answer_id": "a_…",
  "rule": {
    "rule_id": "r_…",
    "revision": 3,
    "learned_cycle": "2026-08-22"
  },
  "affected_lots": ["BT-002", "BT-087", "BT-181"],
  "before": {"allocated": false, "fit_score": 0.2},
  "after": {"allocated": true, "fit_score": 0.85},
  "appraisal_source": "live_vertex",
  "trace_id": "t_…"
}
```

The console can present this without exposing private model reasoning. The evidence is inputs, state transitions, outputs, and provenance—not a chain-of-thought transcript.

## Verification plan

### Domain tests

* Policy, grouping, scope, and appetite answers can generalize.
* Mark and condition answers never generalize.
* Category normalization produces stable keys.
* A revoked or expired rule never auto-answers a question.
* Rule replacement preserves history and increments revision.

### Persistence tests

* A learned rule survives store reconstruction, simulating a process restart.
* Concurrent writes with the same expected revision produce one winner and one conflict.
* Rules are isolated by shop and cycle.
* Firestore adapter contract matches the in-memory implementation through emulator tests.

### Cache tests

* Same inputs reuse an appraisal.
* Changing an image, prompt, schema, model, or relevant rule invalidates it.
* An unrelated category rule does not invalidate every lot.
* Failed refresh leaves the last known-good artifact intact and visibly stale.

### API and UI tests

* Only an existing, answerable question can be answered.
* Unauthenticated writes are rejected.
* Duplicate submissions are idempotent.
* Answering the jewelry-appetite question produces the demonstrated fit and gate change.
* The browser-visible flow reaches the durable store and renders the resulting audit evidence.

### Existing safety gates

The complete unit suite, pricing invariants, historical regression tests, live-vs-cache parity checks, bid-sheet reconciliation, and documentation drift tests remain required before deployment.

## Delivery plan

### Phase 1 — Correctness boundary

* Add store protocols and in-memory implementations.
* Fix the rule-promotion allowlist, including explicit policy behavior.
* Change the answer API to use persisted question IDs.
* Add rule provenance, revision, and revocation tests.

**Exit condition:** no API path can promote an object-specific fact or an unasked question into standing memory.

### Phase 2 — Durable Cloud state

* Add Firestore adapters and deployment configuration.
* Seed the five existing rules through an auditable migration rather than source-code initialization.
* Add restart, isolation, and optimistic-concurrency verification.

**Exit condition:** a rule written to the deployed service remains visible after a new Cloud Run revision or instance handles the next request.

### Phase 3 — Visible collaboration and cache correctness

* Wire the Gate Console controls.
* Add input fingerprints and targeted re-appraisal.
* Show before/after decisions and pending/failure states.
* Record a short, unedited proof of the complete interaction.

**Exit condition:** the operator answers one real question and the deployed console visibly produces a durable rule and a changed downstream result.

## Demo beat

The submission video needs only one memory sequence:

1. Show a costume-jewelry lot initially scored outside the shop's known appetite.
2. Answer the agent's existing appetite question in the Gate Console.
3. Show the durable rule with its cycle and provenance.
4. Show the affected lot re-appraised and the bid gate change.
5. Refresh or route through a second request and show that the rule remains.

This is more persuasive than showing a database dashboard. Firestore can appear briefly in the architecture diagram or Cloud Console proof; the commercial before/after remains the center of the demonstration.

## Non-goals

* Adding Google ADK solely for framework branding.
* Vector embeddings or semantic memory retrieval.
* Autonomous modification of application code.
* Multi-tenant account management beyond clean shop/cycle isolation.
* Migrating deterministic bid math into a model or agent runtime.
* Persisting private chain-of-thought.
* Rebuilding all pipeline artifacts as a general workflow platform.

## Recommendation

Approve the proposal as a narrow submission-hardening feature. The current keyed-memory algorithm should remain the source of truth; Firestore supplies durability, provenance, and concurrency control, while the Gate Console supplies the missing visible interaction. This improves the exact judging dimensions that matter without sacrificing the simplicity, reproducibility, or honest architecture claims that already distinguish Blue Toad Fleet.
