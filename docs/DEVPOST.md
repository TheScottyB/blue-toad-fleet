# Blue Toad Fleet — Official Devpost Submission

**Tagline:** Velocity to distill the information. Collaboration on the judgment.  
**Track:** The Collaborative Partner  
**Solo Eligibility:** Built solo, in 13 days, by one person.  
**Live Application URL:** https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app  
**Public Code Repository:** https://github.com/TheScottyB/blue-toad-fleet  

---

## Form Fields Quick Reference

* **Built with (Tags):**  
  `Google Cloud Run`, `Vertex AI`, `Gemini 3.6 Flash`, `Gemini 3.5 Flash Lite`, `Gemini 2.5 Flash`, `Python`, `FastAPI`, `Docker`, `OpenPyXL`, `Pytest`, `Computer Vision`, `Multimodal AI`, `Auction Logistics`, `Retail Tech`
* **"Try it out" links:**  
  * `https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app` (Live Cloud Run Gate Console)
  * `https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/walk` (The Walk — all 462 photos in shot order, loop closure badged)
  * `https://github.com/TheScottyB/blue-toad-fleet` (Public GitHub Repository)
  * `https://github.com/TheScottyB/blue-toad-fleet/blob/master/media/blue_toad_fleet_demo.mp4` (4-beat narrated walkthrough, ~3:48)
* **What date did you start this project?** `08-18-2026`
* **Did you add Reproducible Testing instructions to your README?** `Yes` (`make install`, `make demo`, `make cycles`, `make test`)
* **Hosted project URL:** `https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app`
* **Which Google AI Models did you use?** `Gemini 3.6 Flash, Gemini 3.5 Flash Lite, Gemini 2.5 Flash`
* **Submitter Type:** `Individual`
* **Country of residence:** `United States`
* **Which Category are you submitting to?** `The Collaborative Partner`
* **Organization name:** `Richmond General`

---

# Project Story (Copy & Paste Below into "About the project")

## Inspiration

Richmond General is a one-person heritage resale shop in Richmond, Illinois (McHenry County). Blue Toad Auctions is located at 200 Elizabeth Lane, Genoa City, Wisconsin (Walworth County), 2.3 miles north via US-12 (5-minute drive / 53-minute walk across the state line).

Blue Toad is not a modern online auction with lot numbers or bidding apps. Every two weeks, the auction house publishes a single webpage with 400+ unlabelled, uncataloged photographs of estate goods and a list of SEO keywords. 

For a solo shop owner, preparing absentee proxy bids before the Friday 8:00 PM deadline he works to is practically impossible. It requires clicking through hundreds of raw photos, identifying obscure makers, researching pricing comps, calculating margin math, and formatting a proxy bid email while running the retail floor.

Every cycle had two outcomes, and both cost the business:
1. **When the owner attends in person:** He rushes over at 9:00 AM for the single one-hour preview window and comes back with an uncurated $300 truckload of low-margin goods that takes an entire year to clear.
2. **When the owner cannot attend:** He misses the sale completely.

Capital was never the constraint — **time and visual throughput were**. The goal is not a truckload of clutter; the goal is securing five to ten high-velocity assets that turn in under 30 days at a 35–40% target margin.

---

## What it does

Blue Toad Fleet transforms an uncataloged gallery drop into a reviewable,
budget-bounded absentee bid draft through seven domain-specific mechanisms:

### 1. Evidence-Gated Spatial Grouping
Auctioneer captions and natural capture order provide a conservative grouping
baseline; reviewed similarity edges can join non-adjacent repeat views. A
physical zone is accepted only from a validated observation sidecar bound to the
exact manifest and embedding model. Without one, the Gate explicitly shows
walk-order grouping and no room map. The checked-in August fixture has no
spatial-observation sidecar, so this submission does not claim a reconstructed
pole-barn topology for that run.

What the evidence does support is on display live at `/walk`: every one of the
462 photos rendered serpentine in exact shot order, lot runs marked, and the
walk's one confirmed loop closure — the auctioneer returned to the costume
jewelry trays 179 frames later — badged at both endpoints. That closure was
found by `gemini-embedding-2`, where sequence proximity cannot find it by
construction (recall@25 85.7% for embeddings vs 0.0% for sequence proximity on
the reshoot corpus — `docs/CAPABILITY_PROBE.md`).

Grouping itself is a puzzle loop, not a funnel. Caption lot numbers are hard
constraints; walk adjacency and the approved embedding edges are proposals
that can be wrong and are revisited; merges and splits iterate to a stable
membership under a deterministic, round-capped loop; and a photo that matches
nothing becomes a singleton cluster instead of a silent drop. The earlier
funnel pass discarded exactly one of the 462 photos — the walk strip rendered
it as a visibly ungrouped tile rather than hiding it — and the puzzle loop's
first result was to seat it: the August fixture now groups all 462 photos
into 415 clusters with nothing left off the board.

### 2. Container Lot Decomposition ("Mining for Gold")
A bounded-container pass lists only visible contents. A possible alpha changes
the price only when its identifying mark is observed and no mark question is
open; otherwise deterministic pricing uses the bulk floor and labels the alpha
as unconfirmed upside. This boundary is tested without assuming a room map.

### 3. The Honest Refusal Rule & Uncertainty Budget
Unlike generic AI tools that hallucinate a price on every photo, Blue Toad Fleet enforces an explicit **uncertainty budget**. On recognizable items (e.g., 1960s Pabst lighted sign), it extracts maker, period, and comps. On items with no grounded comparable, the refusal is made deterministically downstream of the model — `price_lot` returns `max_bid=None` with the reason `pending deep comps — verified sold-price evidence is still needed`, and the allocator can never allocate such a lot. Refusing to guess is a production safety feature, and it is enforced in code rather than requested of the model.

Grounded pricing exposed a live Vertex edge case: combining Google Search with `response_schema` preserved the search queries but stripped the `grounding_chunks` citations, while the same call without the schema returned them (a live-session observation; the raw responses were not archived). Blue Toad splits the operation into a free-text grounded research call that preserves Google-supplied citations and a second, no-tools schema call instructed to extract only figures from that research note. It takes the median of three grounded samples and refuses prices that lack citations, lack two sold comps, or disagree too widely.

### 4. The "Choice-Lot Sniper" (Walls, Table Lines & Shelving Units)
Country auctioneers frequently sell grouped assets as "Buyer's Choice / Times the Money," where the spoken hammer is a per-unit price and the clerk multiplies it by the count. Blue Toad Fleet models that mechanic explicitly instead of assuming every photograph represents one charge.

BT-002 closed the collaborative loop on real money. Gemini saw three labeled jewelry trays and asked whether the bid covered one tray or all three. The auctioneer confirmed, *"Yes, that is a ×3 bid."* Recorded as the text ruling *"take all three trays at ×3,"* `mechanic_from_ruling` resolved it to `TIMES_THE_MONEY, 3`. The owner's **$25 per-unit cap became $75 committed max / $86.25 all-in**, the allocator budgeted the full exposure, and `clerk_directive` wrote: *"BT-002 — times the money: $25.00 per unit x 3. All-in $86.25."* Without that answer, the sheet would have understated its own commitment by $50 before fees.

### 5. Bounded Challenge & The Curator's Read
The curator's prose is bounded by one rejection filter that fires in
production: a dollar figure the sheet did not compute is rejected and the
deterministic template renders instead (`invented_amounts` in
[`src/gate/pitch.py`](../src/gate/pitch.py), enforced on the live path by
[`src/gate/voice.py`](../src/gate/voice.py)). Four further filters — added
lot id, margin, velocity, and buy recommendation — are implemented and
unit-tested in `challenge_text_is_trusted`
([`src/gate/challenge.py`](../src/gate/challenge.py)), but they inspect only
the pushback field and run only when a typed challenge is attached; the live
console builds its pitch without one, so those four do not run in production
today. The evidence-gated challenge seam — `select_challenge`, which would
surface a `REVIEW_CONFLICT` only when a typed standing rule conflicts with
fresh lot-matched evidence — is implemented and tested as a contract but is
not yet wired into the live console; we state that plainly rather than
presenting it as shipped. The committed Seller Hub
capture verifies BT-235's annual absorption ratio (46 sold / 46 active = 1.0),
not the previously drafted sports-card example.

### 6. Deterministic Greedy Budget Allocation
Appraisals feed into pure, unit-tested bid math implementing the store's documented 35–40% buy-in band (applied at its 37.5% midpoint), condition discounts, standard $5.00 auction increments, and the mandatory 15% absentee fee. The final absentee email is compiled automatically for `info@bluetoadauctions.com`.

### 7. Channel-Specific Velocity — eBay Absorption from the Operator's Own Seller Hub
Price alone cannot tell a good buy from a shelf-sitter. The metric that can is
**absorption**: units sold in the last 365 days divided by active listings now
— how much of the standing supply clears in a year, on eBay specifically, read
from the operator's own authenticated Seller Hub research account rather than
scraped or guessed. The recorded proof of why it matters: a 1966 concert
poster and a cast-iron pencil sharpener sell at nearly the same average price
($22.12 vs $21.44), but the poster absorbs at 0.75 (16 months of supply)
against the sharpener's 2.14 (5.6 months). Price cannot separate those two
items; absorption does, and the per-lot comp reports in `data/comps/` carry
the Seller Hub screenshots and page-printed date windows as evidence — pixels,
because text is the medium models make things up in. Three silent-failure
traps in the Seller Hub interface (a date control that labels without
filtering, a row limit that renders zero instead of erroring, pagination with
no end marker) are documented in `docs/PLAYBOOK-ebay-velocity.md`, each one a
wrong number that looks like a right one. The same capability ships as an MCP
connector (`scripts/comps_mcp_server.py`) exposing `ebay_absorption` and
`ebay_comps` to the operator's desktop agent, with model-screened comparables
— the question asked of each listing title is *"is this THAT item?"* — and a
comp set that could not be screened is reported as UNFILTERED, never silently
passed off as clean.

---

## The cycle that ran — sent, accepted, executed, answered

This is not a demo pipeline pointed at sample data. The August 22 cycle
completed the entire premise against a real auction, with every step verified
in the mailbox:

* The absentee sheet — nine lots, **$275.00 committed / $316.25 all-in**, every
  cap under a $600 envelope — was generated, reviewed at the Gate, and sent to
  Blue Toad on August 21.
* The auction house accepted it ("Got it, thanks!"), executed it at the block
  on August 22, and reported the outcome the same evening: *"sorry you did not
  win."* Zero lots won. Zero dollars spent. The receipt is in the repository:
  `docs/evidence/2026-08-22-mailbox-record.md` carries the outcome message
  verbatim from the mailbox — and its own quoted chain contains the sent
  sheet and the acceptance, so the whole narrative is checkable from one
  archived message.
* Losing every lot is the system working, not failing. The caps are defensive
  by design: BT-041 (Edison cylinder lot) was capped at $25 against a $29–$43
  sold-comp cluster on the deepest market comped that cycle — a ceiling the
  room can beat only by paying at or above market. The recorded lesson for the
  next cycle is to revisit the cap, not the comp.
* The spend-to-return shape the sheet committed to, derived from the allocated
  decisions' own comp provenance on the live API: **$713–$879 estimated resale
  against $316.25 all-in — 2.25×–2.78×** if every cap had held.

And the next cycle is already in flight: Blue Toad's September 5 auction was
posted with 414 photos live as of August 29, on the same bi-weekly Saturday
cadence the house has published through December. The system exists because
this stream does not stop.

---

## How we built it

* **Required Stack — what satisfies each requirement:**
  * **Gemini 3.5 or newer:** `gemini-3.6-flash` (multimodal appraisal) and `gemini-3.5-flash-lite` (triage fan-out), both on Vertex AI's `global` endpoint.
  * **Agent framework — a purpose-built agent loop over the Google GenAI SDK.** The loop is the part that does the work, and it is ours: a triage fan-out narrows 462 photos to candidates ([`run_triage_batch`](../src/appraiser/engine.py)); survivors get a deep multimodal appraisal that is required to emit a *question* wherever a determining attribute is not visible, rather than a guess ([`run_appraisal_batch`](../src/appraiser/engine.py)); those questions are merged, ranked by how much of the sheet they repair, and capped ([`build_queue`](../src/appraisal/__init__.py)); answers the operator gives are remembered at the scope they deserve — policy and appetite answers become durable `StandingRule`s keyed `(QuestionKind, Category)` that survive into the next cycle, while grouping and scope answers are deliberately object-scoped rulings for their specific lots, because a ruling about one jewelry tray must never silently authorize a mechanic on next month's unrelated lot ([`learn`](../src/appraisal/__init__.py)); a question the desk cannot answer — a 2mm hallmark on a clasp — is *deferred* rather than asked ([`DESK_ANSWERABLE`](../src/appraisal/__init__.py)); grounded pricing preserves citations in one search-backed call and uses a second schema-only call instructed to extract the figures from that research note ([`price_lot_grounded`](../src/appraiser/engine.py)); and the result becomes a clerk-facing instruction a human at an auction block can act on ([`clerk_directive`](../src/bidmath/__init__.py)).
    That memory is load-bearing, not decorative: on a bulk costume-jewelry tray, appraising with the operator's standing rules versus without moves `fit_score` from 0.2 to 0.85 and flips the bid gate from SKIP to BID. Cross-cycle memory changes what gets bought.
  * **Google GenAI SDK (`google-genai`) — the model layer under that loop.** `genai.Client(vertexai=True, ...)` for application-default-credential auth that runs unchanged locally and inside Cloud Run, `types.Part.from_bytes` for multimodal request assembly, and `types.GenerateContentConfig(response_schema=...)` for constrained decoding — which is what makes a missing maker's mark come back as `null` plus a question instead of a confident invention. See [`src/appraiser/engine.py`](../src/appraiser/engine.py).
  * **Google Cloud infrastructure — Cloud Run:** single-container serverless hosting on project `threebatdrone-prod-420`.
* **Google Cloud Infrastructure:**
  * **Vertex AI:** Multi-tiered model routing utilizing `gemini-3.5-flash-lite` for high-speed, cost-effective triage ($0.30/1M tokens) and `gemini-3.6-flash` for deep multimodal appraisal with structured OpenAPI 3.0 schemas on the `global` endpoint.
  * **Google Cloud Run:** Single-container serverless hosting (`us-central1` on project `threebatdrone-prod-420`) serving the Gate Console UI, Sourcing API, and health endpoints.
* **Core Software Architecture:**
  * Pure, decoupled Python backend — no orchestration framework, no vector store, no agent runtime. The loop above is ~10,500 lines of typed Python under `src/` as of August 29, and the decision layer — photo grouping, the question queue, cross-cycle memory and the bid math — makes no model calls, so every number that reaches a bid sheet is reproducible and unit-tested.
  * Deterministic keyed memory `(QuestionKind, Category)` that generalises house conventions without vector drift.
  * Automated Excel bid sheet generator (`openpyxl`) and formatted absentee email draft generator.
  * A comprehensive local pytest suite; the release report records the exact
    collected, passed, skipped, and failed counts instead of hand-maintained copy.

---

## Challenges we ran into

1. **Uncalibrated Multi-Angle Ingestion:** Rural auction galleries contain repeat views and multi-box runs with zero metadata. We made merges reviewable, manifest-bound, and fail-closed; physical placement remains unavailable unless a spatial sidecar proves it.
2. **Preserving Citations Under Structured Output:** In live Vertex validation, a Google-Search-grounded call with `response_schema` recorded its queries but stripped the citation chunks; removing the schema restored them (observed live; raw responses not archived). We separated grounded research from structured extraction, then reject any price without usable citations.
3. **The "Times the Money" Multiplier Trap:** BT-002 proved the risk was real: the auctioneer's ×3 ruling changed a $25 per-unit ceiling into $75 of committed exposure. The ruling now flows through mechanic parsing, allocation, totals, and the clerk instruction.
4. **Preventing Unsupported Pushback:** A language model can turn a vague
   disagreement into invented market claims. Challenges are now typed,
   evidence-windowed, and rejected when the prose exceeds the supplied facts.
5. **Cloud Run Edge Routing Nuances:** Google Front End (GFE) edge proxies intercepting specific root paths required precise endpoint mapping (`/health`) to ensure instant public HTTP 200 verification.

---

## Accomplishments that we're proud of

* **Fail-closed deterministic allocation:**
  * Every authorized mechanic is reconciled into one all-in exposure, and the
    allocator is tested never to exceed the operator-supplied cap.
  * Historical July A/B output is quarantined and is not presented as evidence.
* **Historical August fixture, honestly bounded:**
  * The local fixture computes 462 photos, 415 groups, and **9 allocations
    ($275.00 max / $316.25 all-in)** under a $600 cap.
  * It is not current release evidence: its legacy state has unresolved
    allocated lots and no sealed artifact manifest, both of which now block
    publication.
* **Release-gated Cloud proof:**
  * The public Cloud Run endpoint is listed above, but deployment revision
    parity, recorded latency, and final media are claims only after the release
    report records them.

---

## What we learned

* **Evidence Matters More Than a Persuasive Map:** capture order is useful, but
  physical topology is shown only when cycle-bound observations support it.
* **More Pixels Can Mean More Fabrication:** an upscaling arm was rejected
  after it invented a lens serial number that the smaller original had read
  correctly — and the appraisal tier transcribed the invention at unchanged
  confidence. The probe record is `docs/CAPABILITY_PROBE.md`; the rule it
  bought is zero tolerance for enhancement stages between the camera and the
  appraiser.
* **Fail-Closed Beats Fail-Quiet — Caught Before It Shipped:** when durable
  Firestore memory was made fail-closed instead of silently downgrading to
  container disk, the very next deploy crash-looped on its first boot — the
  newly dedicated runtime service account held zero project roles, because
  every grant lived downstream of the deploy step. No serving revision was
  ever affected: earlier revisions had worked only by grace of an over-broad
  default identity, and the roleless one failed loudly before it served a
  single request. The fix (`infra/deploy.sh` grants roles before first boot)
  turned a would-be silent downgrade into a visible boot failure, and
  `memory_durable: true` into a statement the health endpoint can back.
* **The Collaborative Partner Paradigm:** Full autonomy on real money is dangerous and unverified. Real commercial value is created when the machine provides visual distillation and the human provides physical intuition and final closure.
* **Keyed Memory Beats Vector Drift:** Simple, deterministic `(kind, category)` rule keys learn permanent house conventions without prompt drift or embedding degradation.

---

## What's next for Blue Toad Fleet

* **The September 5 cycle, live:** listing 4160519 is already posted with 414
  photos; the intake, comp, and gate loop runs against it on the same
  bi-weekly cadence this system was built for.
* **Automated Eventarc Pipeline:** Wiring GCS bucket drops directly to Cloud Run workers via Pub/Sub topics and dead-letter queues.
* **KMS-Signed Gmail OAuth Broker:** Direct automated transmission of approved absentee drafts via Google Secret Manager and KMS grants (as designed in `docs/BROKER.md`).
* **Multi-House Spatial Expansion:** Collecting reviewed, manifest-bound spatial
  observations at neighboring Midwestern estate auction houses.
