# Blue Toad Fleet — Engineering Logbook & Architecture Decisions (ADR)

An engineering record of operational principles and architecture decisions for
the **Blue Toad Fleet** supervised sourcing system. Historical observations are
not release evidence unless they are linked from `docs/SUBMISSION_CLAIMS.md`.

---

## 1. Domain Discovery & The Operational Reality

### The Commercial Environment
* **The Retail Operator:** Richmond General — a one-person heritage resale shop located at 10325 N Main St, Richmond, Illinois (McHenry County).
* **The Sourcing Target:** Blue Toad Auctions — located at 200 Elizabeth Lane, Genoa City, Wisconsin (Walworth County), **2.3 miles north via US-12** (5-minute drive / 53-minute walk across the state line).
* **The Auction Format:** A traditional country estate auction held bi-weekly on Saturday mornings.
* **The Sourcing Friction:** 
  * Blue Toad does **not** have an online bidding app or pre-assigned lot numbers.
  * Every two weeks, the auction house publishes a single web gallery containing **450+ unlabelled, uncataloged photographs** and an SEO keyword block.
  * Absentee proxy bids must be submitted by email to `info@bluetoadauctions.com` before the strict **Friday 8:00 PM cutoff**.
  * The buyer only receives a **single 1-hour physical inspection window** on Saturday morning (9:00 AM – 10:00 AM) before the hammer starts.

### The Failure Modes of Manual Operation
1. **Attending In-Person Without Prep:** The operator rushes in at 9:00 AM, gets overwhelmed by 450 items in 60 minutes, and buys an uncurated $300 truckload of low-margin goods that consumes precious shop floor space for 12 months.
2. **Missing the Auction:** Running the retail counter prevents 6 hours of manual photo inspection, comp research, and margin math on Friday afternoon. The channel is abandoned, leaving high-velocity margins on the table.
3. **The Core Principle:** Capital is not the constraint — **time and visual throughput are**. The goal is securing 5 to 10 high-velocity assets that turn in under 30 days at a 35–40% target gross margin.

---

## 2. Architecture Decision Records (ADR)

### ADR-001: Evidence-Gated Spatial Grouping
* **Context:** Rural auction galleries drop 450+ unlabelled photos with zero lot numbers. Generic vision models treat photos as isolated images, creating duplicate bids across multi-angle shots and failing to identify multi-box estate runs.
* **Decision:** Use captions and natural capture order as the conservative
  baseline, reviewed embedding edges for non-adjacent repeat views, and accept
  physical zones only from a manifest/model-bound observation sidecar.
* **Fail-closed surface:** With no sidecar, the Gate says walk-order grouping and
  does not render a physical showroom topology. The checked-in August fixture is
  currently in this state.

### ADR-002: Multi-Tiered Model Routing on Vertex AI
* **Context:** Running 450+ raw images through heavyweight multimodal models on every cycle is cost-prohibitive and slow. Conversely, lightweight models lack the nuanced reasoning required for maker identification.
* **Decision:** Route inference through two specialized tiers:
  * **Tier 1 (Triage Fan-out):** `gemini-3.5-flash-lite` filters low-margin
    clutter. A fresh run must publish measured token, latency, retry, fallback,
    error, and cost telemetry before any cycle-wide speed/cost claim is made.
  * **Tier 2 (Deep Appraisal):** `gemini-3.6-flash` appraises high-conviction candidate survivors using structured OpenAPI 3.0 schemas on the `global` Vertex endpoint.

### ADR-003: The Honest Refusal Rule & Uncertainty Budget
* **Context:** Standard LLMs hallucinate plausible-sounding prices on unmarked goods, poisoning the bid sheet and risking real capital.
* **Decision:** Implement an explicit **Uncertainty Budget**. On recognizable, high-conviction items (e.g. 1960s Pabst lighted sign), extract maker comps. On unmarked, low-velocity pottery or mystery lots, explicitly emit:
  `NO EXTERNAL COMP — human pricing required`
  *Refusing to guess is a load-bearing production safety feature.*

### ADR-004: The "Buyer's Choice" Shelf Sniper
* **Context:** Country auctioneers sell vertical shelving units as "Buyer's Choice / Times the Money" (the winning bidder chooses 1, 2, or all items at the hammer price). Naive automated agents bid on the group, causing the auction clerk to multiply $8 \times \$45 = \$360$.
* **Decision:** Detect multi-item vertical shelving units, rank items by liquidity, and enforce a strict `max_quantity = 1` absentee directive.

### ADR-005: The Collaborative Partner & Bounded Challenge
* **Context:** Autonomous trading bots operating on real money either buy junk or fail silently. Conversely, passive chatbots act as subservient yes-men.
* **Decision:** Present a structured three-tier pitch. Permit challenge prose
  only for a typed conflict between a standing rule and fresh, lot-matched
  evidence. Reject added lots, amounts, margins, velocity, citations, or buy/bid
  recommendations. The BT-235 Seller Hub capture proves an annual absorption
  ratio of 46 sold / 46 active = 1.0; it does not justify a sports-card claim.
  * *Cross-Cycle Keyed Memory:* Uses deterministic `(QuestionKind, Category)` rule keys to permanently resolve house conventions without vector drift.

### ADR-006: Pure Deterministic BidMath Engine
* **Context:** Valuations and budget allocations must be 100% reproducible, auditable, and decoupled from model inference.
* **Decision:** All appraisals feed into pure, dependency-free valuation math:
  $$\text{Target Max Bid} = \text{Low-Mid Comp} \times 0.375 \times (1.0 - \text{Condition Penalty})$$
  $$\text{All-In Cost} = \text{Max Bid} \times (1.0 + \text{Absentee Fee})$$
  * Enforces standard **$5.00 bidding increments** (up to $100) and the mandatory **15% absentee buyer fee**.
  * Backed by 173 unit tests executing in under half a second.

---

## 3. Ground-Truth Benchmark Reconciliations

### July 11, 2026 historical material

Frozen input lives at `data/july11_gallery_4136050/` (AuctionZip listing
4136050, 452 photos / 324 captioned). The original desktop-apps workbook —
`BlueToad_2026-07-11_BidSheet.xlsx`, 88 bid rows + a 452-row training tab — is
Side A. Images are cached as appraisal-grade `_fl` files with hashes on the
manifest (tracked — the listing HTML is already gone from AuctionZip).

The comparison to run later is that BidSheet versus a **current-pipeline**
workbook on the same cached photos, joined by photo sequence. That Side B
workbook does not exist yet.

`data/BlueToad_2026-07-11_Benchmark_Comparison.xlsx` stays quarantined: it is
not Side A, not Side B, and not release evidence. `scripts/run_july11_benchmark.py`
still refuses to publish.

### August 22, 2026 fixture
* **Dataset:** 462 raw gallery photos (`data/aug22_gallery_4160518/manifest.json`).
* **Canonical grouping:** 415 groups, including reviewed non-adjacent reshoot
  edges. Puzzle loop: every photo assigned; unmatched is a singleton.
* **Sent sheet (mailbox):** 9 lots; $275.00 committed max and $316.25 all-in.
  The only artifact ever sent.
* **Full-coverage allocation:** 46 lots; $520.00 max / $598.00 all-in under $600.
  Sealed output: `data/aug22_gallery_4160518/artifact_manifest.json`.
* **Video:** `media/blue_toad_fleet_demo.mp4` is current submission evidence while
  `make video-verify` passes. Stills in `docs/screenshots/` remain historical.

---

## 4. Production Cloud Deployment

* **Host:** Google Cloud Run (`us-central1`, project `threebatdrone-prod-420`).
* **Live Service URL:** [https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app](https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app)
* **Endpoints:**
  * `GET /`: Interactive Gate Console with walk-order grouping unless validated
    spatial observations exist, plus a bounded curator read.
  * `GET /health`: Instant JSON health probe (`200 OK`).
  * `GET /api/lots`: JSON catalog and priority breakdown.
  * `GET /api/questions`: Active clarification queue & cross-cycle memory rules.
  * `POST /api/answer`: Promotes operator answers to standing rules and reallocates sheet.
  * `GET /api/email`: Formatted absentee bid email draft for `info@bluetoadauctions.com`.

---

## 5. Cycle Amendment — August 22, 2026 (post-cutoff revision, 16:5X CDT 8/21)

### House Rule Resolved: `(lot_grouping, jewelry_trays)` → TIMES THE MONEY
* **Open question:** BT-002 appraisal emitted `lot_grouping` — "single tray or all trays together?" (confidence_gap 0.40).
* **Ground truth:** Bill Theesfield (Blue Toad), email 2026-08-21 21:43 UTC — *"Yes, that is a x3 bid."*
* **Standing rule promoted:** Estate jewelry display trays sold as a labelled run (12/14/16) are **times-the-money**, not one-of-choice. ADR-004's blanket `max_quantity = 1` is **not** universal — it applies to vertical shelving choice lots, not labelled tray runs.

### DEFECT: ADR-001 dedup miss — BT-181 was a duplicate of BT-002
* **Observed:** BT-181 (photo 181, "estate costume jewelry") is a **close-up of trays 12 and 14** already captured in BT-002 (photo 002). Matching invariants: gold-tone flat-link necklace, gold coin charm bracelet, green enamel Christmas tree brooch, blue lapis-glass round pendant, blue-edged black velvet tray on concrete slab.
* **Root cause:** Trajectory clustering merges *sequence-adjacent* photos. These sit **179 frames apart** — the auctioneer returned to the same table later in the shoot. Co-visibility margin scan did not fire because the close-up crops out all peripheral goods.
* **Impact if unfixed:** $28.75 all-in paid twice for the same trays, plus a self-competing absentee bid at the block.
* **Fix owed:** add a **non-adjacent perceptual-hash pass** over accepted lots within a category before the sheet is emitted. Sequence distance must not gate dedup.

### Comp Coverage Gap
* BT-002 / BT-087 / BT-181 carried **no entries in `grounded_prices.json`** (46 grounded lots, none of them). Their $25 maxes derived from `value_magnitude_hint` alone — a model prior, not sold comps. This is ADR-003 behaving correctly (honest refusal) but the **bid sheet did not surface the distinction**, so ungrounded guesses sat next to grounded comps at identical confidence.
* **Fix owed:** flag ungrounded lots explicitly on the sheet (`NO EXTERNAL COMP`) and require operator sign-off above a $20 max.

### Revised Sheet (SENT 2026-08-21, replaces original)
* BT-002: $25.00 **per tray x 3 = $75.00** — taking all three (was $25 / qty 1).
* BT-087: $25.00 → **$15.00** — 38% recheck; bulk unsorted tote at 0.20 penalty ceilings at $22.80 all-in.
* BT-181: **REMOVED** — duplicate of BT-002.
* BT-016 / BT-030: not carried onto the sent sheet (absent from the original absentee email as well).
* **Total Committed Max: $275.00** | **All-In (15%): $316.25** (prior sheet: $260.00 / $299.00).
* Benchmark used: 0.38 resale factor (operator-specified this cycle; ADR-006 codifies 0.375).
* Artifacts: `data/aug22_absentee_bid_email_REVISED.txt`.
