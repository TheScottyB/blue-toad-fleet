# Blue Toad Fleet — 4-Minute Walkthrough Video Script

> **Build note:** Mutable figures below use `{{...}}` placeholders. The narration
> generator resolves them from `media/submission_facts.json`, verifies that the
> snapshot still matches its hashed sources, and refuses stale evidence. The
> checked-in MP4 predates this workflow and must be regenerated before its spoken
> claims can be treated as current submission evidence.

**Target Duration:** Exactly 3:45 – 3:55 (Under the 4:00 strict maximum).  
**Recording Format:** Screen capture of browser tabs + live voiceover.

---

## 🎬 Beat 1: The Solo Card & The Commercial Problem (0:00 – 0:45)

* **Visual on Screen:**
  1. **(0:00 – 0:03)** Title card: `Blue Toad Fleet — Built solo, in 13 days, by one person.`
  2. **(0:03 – 0:45)** Open browser tab showing the raw 462-photo uncataloged gallery drop (`docs/screenshots/00-raw-auction-gallery.png` or `manifest.json`). Scroll through the uncataloged, unlabelled photos.
* **Voiceover:**
  > *"I run Richmond General, a one-person resale shop in Richmond, Illinois. Five minutes up US-12 across the Wisconsin line in Genoa City, Blue Toad Auctions publishes 450 uncataloged photos every two weeks for a Saturday estate sale. There are no lot numbers, no online bidding app, and a strict Friday 8:00 PM absentee cutoff.
  >
  > Because the listing site blocks automated scrapers, our pipeline begins with a sanctioned gallery drop. For a solo shopkeeper running the counter, reviewing 450 unlabelled photos, identifying obscure makers, and researching comps by hand is impossible.
  >
  > Every two weeks I faced the same dilemma: either rush over at 9:00 AM on Saturday for a 1-hour preview and get stuck with an uncurated $300 truckload of low-margin junk, or freeze from the fear of making an embarrassing $500 pricing blunder and miss the sale completely.
  >
  > Capital was never the constraint — time, visual throughput, and bidding confidence were."*

---

## 🎬 Beat 2: Photo Grouping & Container Decomposition (0:45 – 1:45)

* **Visual on Screen:**
  1. Show the manifest-backed intake animation and real duplicate-angle pairs.
  2. Switch to the Architecture Diagram ([`docs/architecture_diagram.png`](architecture_diagram.png)) and the container decomposition evidence.
* **Voiceover:**
  > *"Generic vision models treat an auction gallery as a disconnected bag of photos. Blue Toad starts with the gallery's sequence and captions: an uncaptioned follow-up can attach to the preceding lot, while an auctioneer-written caption prevents a cheap model from merging a real lot away.*
  >
  > *A reviewed image-similarity sidecar then catches repeat views that are far apart in the walk. This run turns {{cycle.photos}} photos into {{cycle.groups}} groups; {{cycle.duplicate_or_non_lot_photos}} duplicate-angle or non-lot views never become independent bids.*
  >
  > *For bounded trays and boxes, a second pass locates the physical container and itemizes only what is inside it. Live Vertex testing also exposed a grounding trap: structured output kept the search queries but dropped every citation. Blue Toad separates grounded research from schema extraction, takes the median of three samples, and refuses any price it cannot cite or reproduce."*

---

## 🎬 Beat 3: The Gate Console, Choice-Lot Sniper & Proactive Pushback (1:45 – 2:45)

* **Visual on Screen:**
  1. Switch to the live Cloud Run Gate Console ([https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app](https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app)).
  2. Show the **Curator's Negotiation Banner**, **Question Queue**, bid sheet, and skip reasons.
* **Voiceover:**
  > *"On Friday afternoon, the fleet doesn't dump an unconstrained wishlist on the owner. It opens the Gate Console, serving serverless on Google Cloud Run.*
  >
  > *On BT-002, Gemini saw three labeled jewelry trays and asked whether the bid applied once or three times. The auctioneer confirmed x3. Blue Toad carried that written ruling into a seventy-five-dollar committed ceiling, eighty-six dollars and twenty-five cents all-in, and an explicit instruction telling the clerk to take all three.*
  >
  > *The curator can push back on a standing rule, but the operator still owns the decision. Evidence, the budget impact, and the resulting allocation stay visible instead of being hidden inside a model response.*
  >
  > *And with deterministic keyed memory, answers to house policy questions are learned permanently, shrinking repetitive friction cycle after cycle."*

---

## 🎬 Beat 4: Live Google Cloud Proof & Final Sealed Sourcing Draft (2:45 – 4:00)

* **Visual on Screen:**
  1. Open Google Cloud Console showing the currently ready Cloud Run revision and service URL.
  2. Tab to `/api/lots` and open the sealed [`data/aug22_absentee_bid_email.txt`](../data/aug22_absentee_bid_email.txt).
  3. Show the current test run in terminal (`make test`).
* **Voiceover:**
  > *"Everything runs in production on Google Cloud Run and Vertex AI. The repository collects {{tests.collected}} tests; {{tests.passed}} pass locally and {{tests.skipped}} skip by policy.*
  >
  > *The final sheet commits {{money.committed_max|usd}} across {{cycle.approved_bids}} approved bids—{{money.committed_all_in|usd}} all-in with the mandatory fifteen-percent absentee fee, strictly formatted to standard five-dollar auction increments.*
  >
  > *The system compiles the final sealed email draft ready for info@bluetoadauctions.com while Richmond General stays open for business.*
  >
  > *Blue Toad Fleet: Velocity to distill the information. Collaboration on the judgment."*

---

## Summary Checklist for Recording

- [ ] Opening Title Card shown for 3 seconds (`Built solo, in 13 days, by one person.`).
- [ ] Messy AuctionZip 450-photo gallery shown.
- [ ] Architecture diagram and evidence-backed photo grouping explained.
- [ ] Grounded-research / structured-extraction split explained.
- [ ] Live Cloud Run Gate Console demonstrated ([https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app](https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app)).
- [ ] BT-002 ×3 ruling and clerk instruction shown.
- [ ] Proactive Pushback on 1959–69 Topps cards highlighted.
- [ ] Google Cloud Console (`threebatdrone-prod-420`) and unit tests displayed.
- [ ] Total time: Under 4 minutes.
