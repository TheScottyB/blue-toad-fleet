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

Blue Toad is not a modern online auction with lot numbers or bidding apps. Every two weeks, the auction house publishes a single webpage with 450+ unlabelled, uncataloged photographs of estate goods and a list of SEO keywords. 

For a solo shop owner, preparing absentee proxy bids before the strict Friday 8:00 PM cutoff is practically impossible. It requires clicking through 450 raw photos, identifying obscure makers, researching pricing comps, calculating margin math, and formatting a proxy bid email while running the retail floor.

Every cycle had two outcomes, and both cost the business:
1. **When the owner attends in person:** He rushes over at 9:00 AM for the single one-hour preview window and comes back with an uncurated $300 truckload of low-margin goods that takes an entire year to clear.
2. **When the owner cannot attend:** He misses the sale completely.

Capital was never the constraint — **time and visual throughput were**. The goal is not a truckload of clutter; the goal is securing five to ten high-velocity assets that turn in under 30 days at a 35–40% target margin.

---

## What it does

Blue Toad Fleet transforms an uncataloged 450-photo gallery drop into an actionable, positive-EV absentee bid sheet through six domain-specific agent mechanisms:

### 1. The Spatial Room Graph (Reconstructing the Pole Barn)
* **Why We Do It:** Auction galleries drop 450+ unlabelled photos with zero lot numbers. Treating photos as isolated images causes duplicate bids on multi-angle shots, misses multi-box estate runs, and leaves the buyer blind during Saturday's 1-hour preview window. Reconstructing the physical room solves these critical failure modes.
* **How It Works:** Auctioneers don't teleport; they walk a physical room. Blue Toad Fleet reconstructs the physical 200 Elizabeth Lane pole barn showroom (2 Center Islands, 2 Long Side Walls, Back Wall displays, and Under-Table Floor Space):
  * **Surface Signature Invariants:** Segments background surface textures (blue pleated vinyl vs. raw pine plywood vs. concrete slab) to determine physical room zones.
  * **Peripheral Margin Co-Visibility:** Scans image borders for neighboring items (e.g., a sliver of a DiMaggio hat on the border of a Dan Marino photo) to anchor uncaptioned photos to table clusters.
  * **Trajectory Clustering:** Preserves the auctioneer's physical walking path via natural sorting, merging 10 loose under-table box photos into **ONE Poppy Trail estate dinnerware set** instead of 10 blind bids and eliminating 95 duplicate multi-angle bids.

### 2. Container Lot Decomposition ("Mining for Gold")
* **Why Spatial Isolation is Required:** High-margin gold in rural auctions (e.g., 11–12 Edison Blue Amberol cylinders, 1959–69 Topps baseball cards, estate costume jewelry trays) is dumped into cardboard boxes or plastic tubs on crowded utility tables. Without spatial mapping to isolate the container and mask out surrounding room noise, vision models blend the box with adjacent table clutter (clocks, lamps, tools) and generate dirty, hallucinated comps.
* **How It Works:** Relying directly on the Spatial Room Graph, the agent isolates the container boundary, suppresses background table noise, and itemizes the individual high-velocity assets inside the bin. It separates genuine alpha from filler, unlocking hidden margin while maintaining clean pricing boundaries.

### 3. The Honest Refusal Rule & Uncertainty Budget
Unlike generic AI tools that hallucinate a price on every photo, Blue Toad Fleet enforces an explicit **uncertainty budget**. On recognizable items (e.g., 1960s Pabst lighted sign), it extracts maker, period, and comps. On items with no grounded comparable, the refusal is made deterministically downstream of the model — `price_lot` returns `max_bid=None` with the reason `no external comp — human pricing required`, and the allocator can never allocate such a lot. Refusing to guess is a production safety feature, and it is enforced in code rather than requested of the model.

Grounded pricing exposed a live Vertex edge case: combining Google Search with `response_schema` preserved the search queries but returned **zero `grounding_chunks`**; the same call without the schema returned six citation chunks. Blue Toad splits the operation into a free-text grounded research call that preserves Google-supplied citations and a second, no-tools schema call instructed to extract only figures from that research note. It takes the median of three grounded samples and refuses prices that lack citations, lack two sold comps, or disagree too widely.

### 4. The "Choice-Lot Sniper" (Walls, Table Lines & Shelving Units)
Country auctioneers frequently sell grouped assets as "Buyer's Choice / Times the Money," where the spoken hammer is a per-unit price and the clerk multiplies it by the count. Blue Toad Fleet models that mechanic explicitly instead of assuming every photograph represents one charge.

BT-002 closed the collaborative loop on real money. Gemini saw three labeled jewelry trays and asked whether the bid covered one tray or all three. The auctioneer confirmed, *"Yes, that is a ×3 bid."* Recorded as the text ruling *"take all three trays at ×3,"* `mechanic_from_ruling` resolved it to `TIMES_THE_MONEY, 3`. The owner's **$25 per-unit cap became $75 committed max / $86.25 all-in**, the allocator budgeted the full exposure, and `clerk_directive` wrote: *"BT-002 — times the money: $25.00 per unit x 3. All-in $86.25."* Without that answer, the sheet would have understated its own commitment by $50 before fees.

### 5. Proactive Velocity Pushback & The Curator's Negotiation
The fleet acts as an **expert commercial partner, not a passive yes-man**. On Friday afternoon, the agent presents a 3-tier pitch (Top 3 Alpha Picks, Fast Smalls, and a Wildcard Challenge). When the owner asked to drop sports cards and tools due to store backlog, the agent used real-time eBay velocity data to respectfully push back:
> *"Understood on dropping modern sports cards, but heads up on Photo #1: these are 13 Golden Era 1959–1969 Topps cards in hard top-loaders (Mays/Aaron era) with <14 day turnaround at 4x margin. Recommend keeping a $100 defensive cap."*

### 6. Deterministic Greedy Budget Allocation
Appraisals feed into pure, unit-tested bid math implementing the store's documented 35–40% buy-in band (applied at its 37.5% midpoint), condition discounts, standard $5.00 auction increments, and the mandatory 15% absentee fee. The final absentee email is compiled automatically for `info@bluetoadauctions.com`.

---

## How we built it

* **Required Stack — what satisfies each requirement:**
  * **Gemini 3.5 or newer:** `gemini-3.6-flash` (multimodal appraisal) and `gemini-3.5-flash-lite` (triage fan-out), both on Vertex AI's `global` endpoint.
  * **Agent framework — a purpose-built agent loop over the Google GenAI SDK.** The loop is the part that does the work, and it is ours: a triage fan-out narrows 462 photos to candidates ([`run_triage_batch`](../src/appraiser/engine.py)); survivors get a deep multimodal appraisal that is required to emit a *question* wherever a determining attribute is not visible, rather than a guess ([`run_appraisal_batch`](../src/appraiser/engine.py)); those questions are merged, ranked by how much of the sheet they repair, and capped ([`build_queue`](../src/appraisal/__init__.py)); answers the operator gives are promoted to `StandingRule`s keyed `(QuestionKind, Category)` that survive into the next cycle ([`learn`](../src/appraisal/__init__.py)); a question the desk cannot answer — a 2mm hallmark on a clasp — is *deferred* rather than asked ([`DESK_ANSWERABLE`](../src/appraisal/__init__.py)); grounded pricing preserves citations in one search-backed call and uses a second schema-only call instructed to extract the figures from that research note ([`price_lot_grounded`](../src/appraiser/engine.py)); and the result becomes a clerk-facing instruction a human at an auction block can act on ([`clerk_directive`](../src/bidmath/__init__.py)).
    That memory is load-bearing, not decorative: on a bulk costume-jewelry tray, appraising with the operator's standing rules versus without moves `fit_score` from 0.2 to 0.85 and flips the bid gate from SKIP to BID. Cross-cycle memory changes what gets bought.
  * **Google GenAI SDK (`google-genai`) — the model layer under that loop.** `genai.Client(vertexai=True, ...)` for application-default-credential auth that runs unchanged locally and inside Cloud Run, `types.Part.from_bytes` for multimodal request assembly, and `types.GenerateContentConfig(response_schema=...)` for constrained decoding — which is what makes a missing maker's mark come back as `null` plus a question instead of a confident invention. See [`src/appraiser/engine.py`](../src/appraiser/engine.py).
  * **Google Cloud infrastructure — Cloud Run:** single-container serverless hosting on project `threebatdrone-prod-420`.
* **Google Cloud Infrastructure:**
  * **Vertex AI:** Multi-tiered model routing utilizing `gemini-3.5-flash-lite` for high-speed, cost-effective triage ($0.30/1M tokens) and `gemini-3.6-flash` for deep multimodal appraisal with structured OpenAPI 3.0 schemas on the `global` endpoint.
  * **Google Cloud Run:** Single-container serverless hosting (`us-central1` on project `threebatdrone-prod-420`) serving the Gate Console UI, Sourcing API, and health endpoints.
* **Core Software Architecture:**
  * Pure, decoupled Python backend — no orchestration framework, no vector store, no agent runtime. The loop above is ~3,500 lines of typed Python, of which the decision layer — photo grouping, the question queue, cross-cycle memory and the bid math — is ~1,300 lines that make no model calls and touch no I/O, so every number that reaches a bid sheet is reproducible and unit-tested.
  * Deterministic keyed memory `(QuestionKind, Category)` that generalises house conventions without vector drift.
  * Automated Excel bid sheet generator (`openpyxl`) and formatted absentee email draft generator.
  * 565 unit tests passing (572 collected; 7 network tests skip by default), in about five seconds.

---

## Challenges we ran into

1. **Uncalibrated Multi-Angle Ingestion:** Rural auction galleries contain duplicate angles and multi-box runs with zero metadata. We solved this by developing the Spatial Room Graph to track background surface transitions and margin co-visibility.
2. **Preserving Citations Under Structured Output:** In live Vertex validation, a Google-Search-grounded call with `response_schema` recorded its queries but returned zero citation chunks; removing the schema returned six. We separated grounded research from structured extraction, then reject any price without usable citations.
3. **The "Times the Money" Multiplier Trap:** BT-002 proved the risk was real: the auctioneer's ×3 ruling changed a $25 per-unit ceiling into $75 of committed exposure. The ruling now flows through mechanic parsing, allocation, totals, and the clerk instruction.
4. **Preventing Passive "Yes-Man" Agent Behavior:** Generic LLMs blindly delete items when an owner gives broad negative feedback. We engineered proactive velocity pushback grounded in completed-sale evidence.
5. **Cloud Run Edge Routing Nuances:** Google Front End (GFE) edge proxies intercepting specific root paths required precise endpoint mapping (`/health`) to ensure instant public HTTP 200 verification.

---

## Accomplishments that we're proud of

* **Ground-Truth A/B Benchmark (July 11 Dataset):**
  * Ingested 452 raw photos and merged **95 multi-angle duplicate photos** into single lots.
  * Slashed legacy unconstrained wishlist spending from **$14,340.00 down to $1,910.00 max ($2,196.50 all-in)**, fitting precisely inside the store's $2,205.00 budget cap.
* **Live August 22 Production Run:**
  * Filtered 462 photos into **9 laser-targeted bids ($275.00 max / $316.25 all-in)** within a strict $600 credit card cap, formatted to $5 bidding increments.
  * Those nine bids represent **$713–$879 estimated gross resale**, a **2.25–2.78x** gross resale-to-cost multiple and $396.75–$562.75 potential gross spread before selling costs.
* **Flawless Google Cloud Deployment:**
  * Serving live traffic with sub-second response times on Cloud Run ([blue-toad-fleet-u5gvrqwvua-uc.a.run.app](https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app)).
* **100% Test Coverage on Core BidMath:**
  * 565 unit tests passing (572 collected; 7 network tests skip by default), in about five seconds.

---

## What we learned

* **Space Matters More Than Pixels:** An auction gallery is not a random bag of photos—it is a physical trajectory through a building. Reconstructing the spatial room topology unlocks 10x higher identification accuracy.
* **The Collaborative Partner Paradigm:** Full autonomy on real money is dangerous and unverified. Real commercial value is created when the machine provides visual distillation and the human provides physical intuition and final closure.
* **Keyed Memory Beats Vector Drift:** Simple, deterministic `(kind, category)` rule keys learn permanent house conventions without prompt drift or embedding degradation.

---

## What's next for Blue Toad Fleet

* **Automated Eventarc Pipeline:** Wiring GCS bucket drops directly to Cloud Run workers via Pub/Sub topics and dead-letter queues.
* **KMS-Signed Gmail OAuth Broker:** Direct automated transmission of approved absentee drafts via Google Secret Manager and KMS grants (as designed in `docs/BROKER.md`).
* **Multi-House Spatial Expansion:** Extending the invariant spatial room graph to neighboring Midwestern estate auction houses in Harvard, Woodstock, and Elkhorn.
