# Blue Toad Fleet

<div align="center">
  <img src="docs/app_icon.png" width="140" alt="Blue Toad Fleet Logo" style="border-radius: 24px; margin-bottom: 12px;" />
  <h3>Velocity to distill the information. Collaboration on the judgment.</h3>
  <p><b>A supervised multimodal sourcing pipeline that turns uncataloged rural-auction galleries into reviewable, budget-bounded bid drafts on Google Cloud.</b></p>

  [![Google Cloud Run](https://img.shields.io/badge/Google%20Cloud%20Run-Live%20Service-34d399?style=flat-square&logo=googlecloud)](https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app)
  [![Vertex AI](https://img.shields.io/badge/Vertex%20AI-Gemini%203.6%20Flash-a78bfa?style=flat-square&logo=google)](https://cloud.google.com/vertex-ai)
  [![Unit Tests](https://img.shields.io/badge/Unit%20Tests-release--gated-38bdf8?style=flat-square&logo=pytest)](https://github.com/TheScottyB/blue-toad-fleet)
  [![License: MIT](https://img.shields.io/badge/License-MIT-fbbf24?style=flat-square)](LICENSE)
</div>

---

## Public Google Cloud Endpoint (Project: `threebatdrone-prod-420`)

The endpoint exists, but repository revision parity is a release-gated fact. Do
not treat the public service as evidence for this working tree: `make release-check`
records the audited commit, tree state, and gate results in `docs/evidence/RELEASE.md`,
and does not yet compare against the deployed revision — live parity is confirmed
only by deploying a release build and recording that deployment.

* **Live Gate Console & UI:** [https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app](https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app)
* **Live Health Endpoint:** [https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/health](https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/health)
* **Live Sourcing API:** [https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/api/lots](https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/api/lots)
* **Live Question Queue:** [https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/api/questions](https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/api/questions)
* **Live Absentee Email Generator:** [https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/api/email](https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/api/email)

---

## Demo Video

[`media/blue_toad_fleet_demo.mp4`](media/blue_toad_fleet_demo.mp4) — a narrated, four-beat walkthrough covering the commercial problem, evidence-backed photo grouping, the live Gate Console, and Cloud Run/test-suite proof. The checked-in cut was recorded on 2026-08-20 and contains that run's historical figures; it is not current submission evidence.

The replacement workflow is declared in [`media/video_manifest.json`](media/video_manifest.json), derives mutable copy from a verified evidence snapshot, isolates every browser recording, and has one authoritative final assembler. See [`docs/VIDEO_WORKFLOW.md`](docs/VIDEO_WORKFLOW.md) before rebuilding. `make video-verify` checks dimensions, duration, size, and audio against the declared facts snapshot without changing the MP4 (run `make video-prepare` first to produce that snapshot).

---

## Try it in 30 Seconds (No GCP, No OAuth, No Keys Required)

```bash
git clone https://github.com/TheScottyB/blue-toad-fleet.git
cd blue-toad-fleet

# 1. Install dependencies (creates .venv automatically)
make install

# 2. Run the deterministic decision pipeline across seeded lots
make demo

# 3. Watch cross-cycle memory collapse the clarification queue
make cycles

# 4. Run the unit suite (the command reports the current count)
make test
```

---

## The Commercial Problem

Richmond General is a one-person heritage resale shop in Richmond, Illinois (McHenry County). Blue Toad Auctions is located at 200 Elizabeth Lane, Genoa City, Wisconsin (Walworth County), 2.3 miles north via US-12 (5-minute drive / 53-minute walk across the state line).

**Blue Toad is not a modern online auction.** Every two weeks, the auction house publishes a single webpage with 450+ uncataloged photographs of estate goods and a list of SEO keywords. There are no lot numbers and no live bidding app.

For a solo shop owner, preparing absentee prebids before the strict **Friday 8:00 PM cutoff** is practically impossible:
1. **When attending in person:** The owner rushes in at 9:00 AM for the 1-hour preview and gets stuck with an uncurated $300 truckload of low-margin goods that takes a year to clear.
2. **When unable to attend:** He misses the sale completely.

Capital is not the constraint — **time and visual throughput are**. The goal is securing five to ten high-velocity assets that turn in under 30 days at a 35–40% target margin.

---

## Core System Architecture

<div align="center">
  <img src="docs/architecture_diagram.png" width="100%" alt="Blue Toad Fleet Architecture Diagram" style="border-radius: 12px; margin: 16px 0;" />
</div>

### 1. Evidence-Gated Spatial Grouping
* **Why We Do It:** Auction galleries drop hundreds of unlabelled photos with zero lot numbers. Treating each frame as a separate item can create duplicate bids on repeat views and split a multi-photo lot.
* **How It Works:** Natural capture order and auctioneer captions form the conservative baseline. Reviewed similarity edges may merge non-adjacent repeat views. Physical zones are accepted only from a validated `spatial_observations.json` sidecar bound to the exact manifest and model, and no shipped surface renders them yet — the hosted Gate shows **walk-order grouping** and no physical topology. The checked-in August fixture has no such sidecar, so no pole-barn layout is claimed for it.

### 2. Container Lot Decomposition ("Mining for Gold")
* **Why It Exists:** Boxes and trays mix a possible high-value item with bulk material and surrounding table clutter.
* **How It Works:** A bounded-container pass lists only visible contents. Pricing uses a confirmed alpha only when its identifying mark is observed and no mark question remains open; otherwise the lot is priced from its bulk floor and the possible alpha is named only as upside. This path is tested independently of physical-room inference.

### 3. Multi-Tiered Model Routing on Vertex AI (Google GenAI SDK)
Every call to a model goes through the **Google GenAI SDK** (`google-genai`) in
[`src/appraiser/engine.py`](src/appraiser/engine.py) — `genai.Client(vertexai=True, ...)`
for application-default-credential auth that runs unchanged on a laptop and inside
Cloud Run, `types.Part.from_bytes` to assemble the photo alongside the prompt, and
`types.GenerateContentConfig(response_schema=...)` for constrained decoding.

* **Triage Fan-out (`gemini-3.5-flash-lite`):** Filters low-margin clutter and background filler. Per-call tokens, latency, retries, fallback use, errors, rate snapshots, and measured cost are now recorded; no speed or full-cycle cost is claimed until a fresh corpus run produces that telemetry.
* **Deep Multimodal Appraisal (`gemini-3.6-flash`):** Evaluates high-conviction survivors using structured OpenAPI 3.0 schemas on the `global` Vertex endpoint.
* **Per-lot stage handoff:** Ordinary lots enter appraisal immediately; container lots enter as soon as their own spatial decomposition finishes. Each completed appraisal can start grounded comp research while other lots are still being appraised.
* **Honest Refusal Rule:** The appraisal model is forbidden from naming any price at all (`APPRAISAL_SYSTEM`: *"NEVER state or imply a price, estimate or value range"*). The refusal is decided downstream and is deterministic, not model-dependent — `price_lot` ([`src/bidmath/__init__.py`](src/bidmath/__init__.py)) returns a lot whose `CompEstimate` has no sources with `max_bid=None` and the workflow state `pending deep comps`, and `allocate` can never allocate it before verified sold-price evidence arrives. The current local August fixture routes **190 of 414** grouped lots to human pricing, but that historical fixture is not release-eligible under the new publication gate.

### 3a. Grounded Pricing Without Losing the Evidence
Live Vertex validation exposed a failure at the boundary between Google Search grounding and structured output: adding `response_schema` preserved the search queries but stripped the `grounding_chunks` citations, while the same call without the schema returned them (a live-session observation; the raw responses were not archived in this repository). Blue Toad therefore separates the work. The first call performs grounded research in free text and preserves Google-supplied citations; a second call, with no tools or search, is instructed to extract only the figures in that research note into the pricing schema. Three independent grounded samples are then medianed ([`grounded_batch.py`](src/appraiser/grounded_batch.py)), and the lot is refused if the calls disagree too widely, contain fewer than two sold comps, or provide no usable citation. See [`price_lot_grounded`](src/appraiser/engine.py) and [`price_is_usable`](src/appraiser/pricing.py).

### 3b. The Curator's Read (Gemma 4 on Vertex AI)
The Gate console's pitch banner is written by **Gemma 4** (`gemma-4-26b-a4b-it-maas`),
and it is the only call in the system with no response schema — because it is the
only one whose output is not a decision. `build_pitch` in
[`src/gate/pitch.py`](src/gate/pitch.py) selects the tiers deterministically from
the allocated sheet; Gemma is handed lot ids, captions and the bids the math
already set, and asked to phrase them. It never sees a comparable sale.

Telling a model not to invent a figure is not the same as it not inventing one, so
`invented_amounts` checks the prose against the sheet's own numbers before display.
A figure the system did not compute means the model's entire read is discarded and
the deterministic template ([`template_voice`](src/gate/voice.py)) renders instead —
as it does if Gemma is unreachable.

### 4. The "Choice-Lot Sniper" (Walls, Table Lines & Shelves)
Grouped assets sold "Choice / Times the Money" are the classic clerk-multiplication trap — bid on the group and the clerk multiplies the hammer by the count. The fleet models the mechanic explicitly rather than guessing at it: `mechanic_from_ruling` parses the auctioneer's own written ruling into a `BidMechanic` and a unit count, and a choice lot with no election is budgeted at the **full group** exposure and flagged `needs_election=True` rather than silently assumed to be a single unit.

BT-002 closed this loop on real money. Gemini saw three labeled jewelry trays and asked whether the bid covered one tray or all three. The auctioneer confirmed, *"Yes, that is a ×3 bid."* Recorded as the text ruling *"take all three trays at ×3,"* it resolved to `TIMES_THE_MONEY, 3`: the owner's **$25 per-unit cap became $75 committed max / $86.25 all-in**, and `clerk_directive` wrote: *"BT-002 — times the money: $25.00 per unit x 3. All-in $86.25."* — with `compile_absentee_email` adding the explicit exception line, *"BT-002 is an exception to the one-unit rule: take 3 of the 3 at the per-unit price."* Without that ruling, the sheet would have understated its own exposure by $50 before fees.

### 5. The Collaborative Partner & Bounded Challenge
The Gate presents a three-tier pitch (Alpha Picks, Fast Smalls, and ruled-out
items). A challenge is allowed only when a typed standing rule conflicts with
fresh, lot-matched evidence carrying its own source and observation window. The
model may phrase `REVIEW_CONFLICT`; it may not invent a lot, dollar figure,
margin, velocity, or buy recommendation. Without those facts, pushback is null.
The checked-in Seller Hub evidence supports BT-235's exact annual absorption
calculation (46 sold / 46 active = 1.0); it does not support a sports-card claim.

### 6. Pure Deterministic BidMath Engine
Appraisals feed into pure, unit-tested valuation logic implementing the store's documented **35–40% buy-in band** (applied at its 37.5% midpoint), condition discounts, standard **$5.00 bidding increments**, and the mandatory **15% absentee fee**.

---

## Historical August fixture reconciliation

The checked-in August 22 fixture computes **9 allocated bids ($275.00 max)** and
**$316.25** all-in exposure under the operator's $600 cap. Their selected lots
carry **$713–$879 estimated gross resale**, or **2.25–2.78x** gross cost before
selling expenses. These figures describe the historical local fixture and are
not a publishable current cycle: its old pipeline state lacks the sealed artifact
manifest and still has unresolved allocated lots. The allocation invariant is
tested directly, and the new publisher refuses either condition — though this
particular fixture is stopped one gate earlier still: its pre-provenance pipeline
state is rejected outright.

The former July A/B workbook is quarantined as historical and unverified. It is
not used as submission evidence or as an input to the current pipeline.

---

## Visual Walkthrough & Screenshots

### The Input: 462 Uncataloged Raw Photos (AuctionZip Gallery Drop)
<div align="center">
  <img src="docs/screenshots/00-raw-auction-gallery.png" width="100%" alt="Raw Uncataloged AuctionZip Gallery Drop" style="border-radius: 8px; margin-bottom: 16px;" />
</div>

### The Output: Live Gate Console UI (Google Cloud Run)
<div align="center">
  <img src="docs/screenshots/01-gate-console.png" width="48%" alt="Gate Console Header" style="border-radius: 8px;" />
  <img src="docs/screenshots/02-showroom-topology.png" width="48%" alt="Historical Gate capture; replace after the release gate passes" style="border-radius: 8px;" />
</div>

### Cloud-backed cycle kickoff

The repository now includes a cloud-backed path so a new auction does not need
to be processed from the same disk that captured it. The operator stages the
sanctioned manifest and every
full-resolution photograph in a private Cloud Storage cycle prefix. A READY
marker written last is the explicit kickoff: Eventarc delivers it to the Cloud
Run service, which idempotently launches a Cloud Run Job. The job processes the
cloud copy with Vertex AI, publishes its JSON/workbook/email artifacts back to
the same cycle, and marks it active only after success. The chain is provisioned
and test-covered end to end; no production cycle has yet been processed through it.
Bid transmission remains a human action. See [`docs/CLOUD_CYCLES.md`](docs/CLOUD_CYCLES.md).
<div align="center" style="margin-top: 8px;">
  <img src="docs/screenshots/03-curator-challenge.png" width="48%" alt="Curator Challenge Pitch" style="border-radius: 8px;" />
  <img src="docs/screenshots/05-the-sheet.png" width="48%" alt="Allocated Bid Sheet" style="border-radius: 8px;" />
</div>

---

## Repository Structure

```
blue-toad-fleet/
├── data/                       # Verified cycle data, manifests, and bid sheets
│   ├── aug22_absentee_bid_email.txt            # Historical absentee draft
│   ├── BlueToad_2026-08-22_BidSheet.xlsx       # Historical workbook
├── demo/                       # Credential-free reproducible demo runners
│   ├── run_demo.py             # Pure decision pipeline demo
│   ├── run_cycles.py           # 2-cycle cross-cycle learning demo
│   └── build_console.py        # Static HTML Gate Console compiler
├── docs/                       # Architecture diagrams, Devpost text, screenshots
│   ├── architecture_diagram.png
│   ├── app_icon.png
│   ├── DEVPOST.md              # Complete Devpost submission story
│   ├── VIDEO_SCRIPT.md         # 4-minute video walkthrough script
│   ├── VIDEO_WORKFLOW.md       # Reproducible evidence-backed media workflow
│   └── screenshots/            # High-resolution UI captures
├── infra/                      # Cloud Run deployment scripts
│   ├── deploy.sh               # Deploy service plus cycle infrastructure
│   └── provision_cycles.sh     # Bucket, processor job, IAM, Eventarc
├── scripts/                    # Live cycle runners & verification tools
│   ├── run_aug22_cycle.py      # Retired legacy writer (refuses with guidance)
│   ├── run_july11_benchmark.py # Quarantined historical entry point (refuses)
│   └── capture_screenshots.mjs # Automated Playwright dark-mode screenshot capture
├── src/                        # Core application code
│   ├── appraisal/              # Question queue & cross-cycle keyed memory
│   ├── appraiser/              # Vertex AI client, OpenAPI 3.0 schemas, prompts
│   ├── assemble/               # Lot assembly & multi-angle merging
│   ├── bidmath/                # Pure deterministic valuation & greedy allocator
│   ├── cycles/                 # Cloud Storage contract and Cloud Run Job worker
│   ├── gate/                   # Gate Console UI renderer (pure HTML/CSS)
│   ├── intake/                 # Manifest parsing, natural sort & spatial clustering
│   └── server.py               # Cloud Run FastAPI server & API endpoints
├── tests/                      # Comprehensive pytest suite; count reported by make test
├── Dockerfile                  # Container definition for Google Cloud Run
├── LICENSE                     # MIT License
├── Makefile                    # Standard developer workflow targets
├── pytest.ini                  # Root pytest configuration
└── requirements.txt            # Production Python dependencies
```

---

## Disclosure & Solo Eligibility

All code in this repository was written between August 18 and August 31, 2026.

* **Eligibility:** Built solo, in 13 days, by one person.
* **Pre-existing Context:** The bid math and workflow implement the documented sourcing rules of Richmond General (Richmond, IL). Historical data references real sales receipts and auction manifests from Blue Toad Auctions (Genoa City, WI).
* **Zero Leaked Secrets:** All API keys and GCP service credentials are managed via environment variables and Secret Manager; no private tokens are stored in this repository.
