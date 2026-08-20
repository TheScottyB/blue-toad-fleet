# Blue Toad Fleet — Devpost Submission Draft

**Track:** The Collaborative Partner  
**Tagline:** *Velocity to distill the information. Collaboration on the judgment.*  
**Primary Repository:** [github.com/TheScottyB/blue-toad-fleet](https://github.com/TheScottyB/blue-toad-fleet)  
**Solo Eligibility:** Built solo, in 13 days, by one person.

---

## Inspiration

Richmond General is a one-person resale shop in Richmond, Illinois. Blue Toad Auctions is 2.3 miles north, across the state line in Genoa City, Wisconsin — five minutes up US-12.

Whether the owner is standing in the auction room or behind his own counter, the work is the same, and it is the work he does not have time for.

Blue Toad is not a live online auction. There is no bidding app to keep half an eye on between customers, and there are no lot numbers — the house publishes a long gallery of 400+ unlabelled photographs and a list of SEO keywords for one-off estate goods. A live online sale can be followed from a counter. A rural country auction cannot.

So every two-week cycle has two outcomes and both cost the business:
1. **When he attends in person:** He rushes over at 9:00 AM for the one-hour preview, and comes back with an uncurated $300 truckload that takes an entire year of dusting, researching, and haggling to clear.
2. **When he cannot attend:** He misses the sale entirely because preparing absentee bids requires opening 400+ raw photos, identifying items, researching comps, calculating margin math, and emailing `info@bluetoadauctions.com` before Friday at 8:00 PM.

Capital is not the constraint. Time is. And a truckload is not the goal; five to ten high-velocity items that turn in under thirty days at a 35–40% margin target is the goal.

**The hypothesis this project tests:** If prebids go in on the right high-velocity items consistently, every two weeks, the results beat ad-hoc buying by a wide margin. Every proxy bid carries positive expected value, win or lose. Losing more often than winning is acceptable. Bidding blindly is not.

---

## What It Does

Blue Toad Fleet transforms a chaotic, unlabelled gallery drop into an actionable, positive-EV absentee bid sheet through six domain-specific agent mechanisms:

### 1. The Spatial Room Graph (Reconstructing the Pole Barn)
The auctioneer photographs the sale by walking the invariant showroom (two long side walls, two center island utility tables, back wall hanging displays, and a rear floor space). Instead of treating photos as disconnected thumbnails, the agent analyzes background surface signatures (blue tablecloth vs. concrete floor) and peripheral co-visibility in image margins, stitching 450+ photos into physical table clusters.

### 2. Container Lot Decomposition ("Mining for Gold")
In rural auctions, high-margin items are buried in uncataloged plastic tubs and cardboard box lots. The agent segments the container boundary, extracts and itemizes individual high-velocity assets (e.g. 9 vintage Edison cylinder records), and explicitly masks/rejects surrounding table clutter (clocks in foreground, bobbleheads in rear) to prevent dirty market comps.

### 3. The Honest Refusal Rule
Unlike generic AI tools that guess a dollar value on every photo, Blue Toad Fleet has an explicit **uncertainty budget**. On recognizable items (e.g. 1960s Pabst lighted sign), it extracts maker, period, and comps. On unmarked, low-velocity pottery, it explicitly emits `"NO EXTERNAL COMP — human pricing required"`, protecting the shopkeeper from buying dead-weight inventory.

### 4. The "Buyer's Choice" Shelf Sniper
Country auctioneers sell vertical shelving units as "Buyer's Choice / Times the Money" (e.g. high bidder takes 1, 2, or all 8 lanterns at the hammer price). Naive bots get trapped by taking all 8 ($360 blowout). Blue Toad Fleet detects vertical shelf units, ranks the items by liquidity (Pick #1: Blue Adlake globe), and enforces a strict `max_quantity = 1` absentee directive.

### 5. Cross-Cycle Memory & Proactive Partner Pushback
Every Friday at 4:00 PM, the fleet surfaces its top clarification questions—ranked strictly by value-at-stake and confidence gap, capped at 12. As the shopkeeper answers, answers are promoted to persistent `StandingRules`. In our July 11 benchmark, Cycle 1 asked 12 questions; Cycle 2 needed only 7.

Crucially, the agent acts as an **expert peer, not a passive chatbot**. When the owner gives broad directives (e.g. *"drop sports cards and tools"*), the fleet provides respectful, data-driven pushback based on real-time eBay velocity:
> *"Understood on dropping modern sports cards, but heads up on Photo #1: these are 13 Golden Era 1959–1969 Topps cards in hard top-loaders (Mays/Aaron era) with <14 day eBay turnaround at 4x margin. Recommend keeping a $100 defensive cap."*

### 6. Deterministic Greedy Budget Allocation
Appraisals feed into pure, unit-tested bid math implementing the store's 38% margin target, condition penalties, and 15% absentee buyer's fee. Bids $\le \$35$ are marked **AUTO-SEND**; high-value lots require one-click human sign-off. The final prebid email is compiled automatically for `info@bluetoadauctions.com`.

---

## Live Google Cloud Deployment (Project: `threebatdrone-prod-420`)

* **Live Gate Console & API:** [https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app](https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app)
* **Live Health Check:** `https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/health`
* **Live Sourcing API:** `https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/api/lots`
* **Live Absentee Email Generator:** `https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/api/email`

---

## Why Not Full Autonomy? (The Anti-"Trading-Bot" Narrative)

Every hackathon sees automated "trading bot" demos claiming to make $100,000 while the creator sleeps. Full autonomy on real cash is easy to film and impossible to verify.

In real-world small business, blind autonomy is dangerous. Models hallucinate, context gets distorted, and auction terms have fine print. Blue Toad Fleet is built around **The Collaborative Partner** thesis:
> *"Velocity to distill the information. Collaboration on the judgment."*

The machine handles high-speed visual throughput (chewing through 450 photos in seconds); the human operator provides strategic appetite and final financial closure.

---

## How We Built It

* **Google Cloud Architecture:**
  * **Vertex AI:** `gemini-3.6-flash` (deep multimodal appraisal & structured OpenAPI 3.0 schemas) and `gemini-3.5-flash-lite` (fast triage fan-out at \$0.30/1M tokens).
  * **Cloud Run:** Single-container serverless hosting serving the Gate Console and API.
* **Core Engine:** Written in Python with zero framework lock-in, tested with 160+ unit tests across intake, bidmath, appraisal, and schema conversion.

---

## Ground-Truth A/B Benchmark (July 11 Dataset)

We benchmarked Blue Toad Fleet against the legacy 452-photo July 11 auction dataset:
* **Duplicate Merges:** Merged **95 multi-angle duplicate photos** into single lot groups, eliminating duplicate proxy bids.
* **Budget Discipline:** Legacy V1 requested an unconstrained \$14,340.00 across all candidate rows; Fleet V2 allocated **\$1,915.69 max (\$2,203.15 all-in)**, adhering strictly within the **\$2,205.00** store budget cap.
* **Touchpoints:** Filtered 452 raw photos down to **47 Auto-Send lots** and **16 Needs-Approval lots**, reducing Friday review time to under 2 minutes.

---

## 4-Minute Devpost Video Storyboard

* **0:00 – 0:45 (The Friction):** Title card (*"Built solo, in 13 days, by one person"*). The Richmond General counter, US-12 to Genoa City, 450 unlabelled photos, the $300 truckload trap.
* **0:45 – 1:45 (The Visual Distillation):** Gemini 3.5 Flash-Lite triage demo, Gemini 3.6 Flash container decomposition on the Edison cylinder box lot, and the Refusal to Guess rule.
* **1:45 – 2:45 (The Collaborative Partner):** The Gate Console, question ranking by impact, cross-cycle memory collapsing questions from 12 to 7, and the Choice-Lot Shelf Sniper.
* **2:45 – 3:45 (Google Cloud Proof):** Google Cloud Console, Cloud Run service URL, live Vertex AI logs on project `threebatdrone-prod-420`, greedy budget allocation, and the generated absentee email.
* **3:45 – 4:00 (The Closing):** *"Velocity to distill the information. Collaboration on the judgment."* Real prebids submitted with real money while the shop stays open.
