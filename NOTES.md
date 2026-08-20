# Blue Toad Fleet — Engineering Logbook & Architecture Decisions (ADR)

An immutable record of operational principles, domain discoveries, architecture decisions, and ground-truth benchmark reconciliations for the **Blue Toad Fleet** multi-agent sourcing system.

---

## 1. Domain Discovery & The Operational Reality

### The Commercial Environment
* **The Retail Operator:** Richmond General — a one-person heritage resale shop located at 10324 N Main St, Richmond, Illinois (McHenry County).
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

### ADR-001: The Spatial Room Graph & Invariant Showroom Topology
* **Context:** Rural auction galleries drop 450+ unlabelled photos with zero lot numbers. Generic vision models treat photos as isolated images, creating duplicate bids across multi-angle shots and failing to identify multi-box estate runs.
* **Decision:** Reconstruct the physical 200 Elizabeth Lane pole barn showroom (2 Center Islands, 2 Long Side Walls, Back Wall hanging displays, and Under-Table Concrete Floor space).
* **Mechanism:**
  1. *Surface Invariant Segmentation:* Detects background textures (blue pleated vinyl tablecloth vs. raw pine plywood vs. concrete slab) to classify physical room zones.
  2. *Peripheral Margin Co-Visibility:* Scans image borders for adjacent goods (e.g. a sliver of a DiMaggio hat next to a Dan Marino photo) to link uncaptioned photos to table clusters.
  3. *Trajectory Clustering:* Preserves the auctioneer's natural walking path, merging 10 loose under-table box photos into **ONE Poppy Trail dinnerware estate set** and eliminating 95 duplicate multi-angle bids.

### ADR-002: Multi-Tiered Model Routing on Vertex AI
* **Context:** Running 450+ raw images through heavyweight multimodal models on every cycle is cost-prohibitive and slow. Conversely, lightweight models lack the nuanced reasoning required for maker identification.
* **Decision:** Route inference through two specialized tiers:
  * **Tier 1 (Triage Fan-out):** `gemini-3.5-flash-lite` filters 460+ photos in seconds for ~$0.30 per cycle, eliminating low-margin clutter and background filler.
  * **Tier 2 (Deep Appraisal):** `gemini-3.6-flash` appraises high-conviction candidate survivors using structured OpenAPI 3.0 schemas on the `global` Vertex endpoint.

### ADR-003: The Honest Refusal Rule & Uncertainty Budget
* **Context:** Standard LLMs hallucinate plausible-sounding prices on unmarked goods, poisoning the bid sheet and risking real capital.
* **Decision:** Implement an explicit **Uncertainty Budget**. On recognizable, high-conviction items (e.g. 1960s Pabst lighted sign), extract maker comps. On unmarked, low-velocity pottery or mystery lots, explicitly emit:
  `NO EXTERNAL COMP — human pricing required`
  *Refusing to guess is a load-bearing production safety feature.*

### ADR-004: The "Buyer's Choice" Shelf Sniper
* **Context:** Country auctioneers sell vertical shelving units as "Buyer's Choice / Times the Money" (the winning bidder chooses 1, 2, or all items at the hammer price). Naive automated agents bid on the group, causing the auction clerk to multiply $8 \times \$45 = \$360$.
* **Decision:** Detect multi-item vertical shelving units, rank items by liquidity, and enforce a strict `max_quantity = 1` absentee directive.

### ADR-005: The Collaborative Partner & Proactive Pushback
* **Context:** Autonomous trading bots operating on real money either buy junk or fail silently. Conversely, passive chatbots act as subservient yes-men.
* **Decision:** Build an expert collaborative peer that presents a structured 3-tier pitch (Alpha Picks, Fast Smalls, Wildcard Challenge) and provides proactive pushback grounded in live market velocity:
  * *Example:* When the owner gave broad skip instructions on sports cards, the agent used real-time eBay completed velocity to push back and preserve the **13 Golden Era 1959–1969 Topps baseball cards ($100 cap)**, delivering a $300+ resale spread.
  * *Cross-Cycle Keyed Memory:* Uses deterministic `(QuestionKind, Category)` rule keys to permanently resolve house conventions without vector drift.

### ADR-006: Pure Deterministic BidMath Engine
* **Context:** Valuations and budget allocations must be 100% reproducible, auditable, and decoupled from model inference.
* **Decision:** All appraisals feed into pure, dependency-free valuation math:
  $$\text{Target Max Bid} = \text{Low-Mid Comp} \times 0.375 \times (1.0 - \text{Condition Penalty})$$
  $$\text{All-In Cost} = \text{Max Bid} \times (1.0 + \text{Absentee Fee})$$
  * Enforces standard **$5.00 bidding increments** (up to $100) and the mandatory **15% absentee buyer fee**.
  * Backed by 160 unit tests executing in under 0.1 seconds.

---

## 3. Ground-Truth Benchmark Reconciliations

### July 11, 2026 Historical Benchmark Reconciliation
* **Dataset:** 452 raw gallery photos (`data/july11_gallery_4136050/manifest.json`).
* **Physical Lots Consolidated:** 357 physical lots (95 multi-angle duplicate photos merged).
* **Legacy V1 Wishlist Chaos:** 88 unranked flat rows summing to **$14,340.00** unbudgeted max bids.
* **Fleet V2 Sourcing Schedule:**
  * Hard Budget Cap: **$2,205.00**
  * Auto-Send Threshold: **$40.00**
  * Committed Max Bids: **$1,915.69**
  * Committed All-In (w/ 15% fee): **$2,203.15** (strictly fitted within $2,205 cap).
  * Output: `data/BlueToad_2026-07-11_Benchmark_Comparison.xlsx`.

### August 22, 2026 Live Sourcing Cycle Reconciliation
* **Dataset:** 462 raw gallery photos (`data/aug22_gallery_4160518/manifest.json`).
* **Physical Lots Consolidated:** 358 physical lots (104 multi-angle duplicate photos merged).
* **Approved Sourcing Schedule (12 Targeted Lots):**
  1. `BT-001`: Vintage Topps Baseball Cards (1959–69 Golden Era) — Start $35.00 | Max $100.00 | All-In $115.00
  2. `BT-041`: Edison Rolls (11–12 canisters + bare roll) — Start $15.00 | Max $40.00 | All-In $46.00
  3. `BT-002`: Estate Costume Jewelry (Tray Lot 1) — Start $10.00 | Max $25.00 | All-In $28.75
  4. `BT-087`: Costume Jewelry (Tray Lot 2) — Start $10.00 | Max $25.00 | All-In $28.75
  5. `BT-181`: Estate Costume Jewelry (Tray Lot 3) — Start $10.00 | Max $25.00 | All-In $28.75
  6. `BT-050`: Lionel Building Set — Start $10.00 | Max $25.00 | All-In $28.75
  7. `BT-021`: Princess Phone — Start $10.00 | Max $20.00 | All-In $23.00
  8. `BT-048`: ET Nightlight — Start $10.00 | Max $20.00 | All-In $23.00
  9. `BT-235`: Century Progress Bottle — Start $10.00 | Max $15.00 | All-In $17.25
  10. `BT-016`: Trading Cards — Start $10.00 | Max $15.00 | All-In $17.25
  11. `BT-030`: Non-Sport Trading Cards — Start $10.00 | Max $15.00 | All-In $17.25
  12. `BT-066`: Handheld Video Games (Radica/LCD) — Start $5.00 | Max $10.00 | All-In $11.50
* **Total Committed Max:** **$335.00**
* **Total Committed All-In (w/ 15% fee):** **$385.25** (strictly fitted within $600 cap).
* **Increment Discipline:** Standard $5.00 increments across all bids.
* **Output Artifacts:** `data/aug22_absentee_bid_email.txt` and `data/BlueToad_2026-08-22_BidSheet.xlsx`.

---

## 4. Production Cloud Deployment

* **Host:** Google Cloud Run (`us-central1`, project `threebatdrone-prod-420`).
* **Live Service URL:** [https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app](https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app)
* **Endpoints:**
  * `GET /`: Interactive Gate Console with 2D Showroom Topology and Curator Challenge.
  * `GET /health`: Instant JSON health probe (`200 OK`).
  * `GET /api/lots`: JSON catalog and priority breakdown.
  * `GET /api/questions`: Active clarification queue & cross-cycle memory rules.
  * `POST /api/answer`: Promotes operator answers to standing rules and reallocates sheet.
  * `GET /api/email`: Formatted absentee bid email draft for `info@bluetoadauctions.com`.
