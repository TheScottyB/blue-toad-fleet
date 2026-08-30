# Blue Toad Fleet — 4-Minute Walkthrough Video Script

> **Build note:** Mutable figures below use `{{...}}` placeholders. The narration
> generator resolves them from `media/submission_facts.json`, verifies that the
> snapshot still matches its hashed sources, and refuses stale evidence. The
> checked-in MP4 was built by this workflow on 2026-08-29 from release-eligible
> facts (sealed artifact manifest declared); `make video-verify` confirms it is
> bound to the current facts and inputs.

**Target Duration:** Exactly 3:45 – 3:55 (Under the 4:00 strict maximum).  
**Recording Format:** Screen capture of browser tabs + live voiceover.

---

## 🎬 Beat 1: The Solo Card & The Commercial Problem (0:00 – 0:45)

* **Visual on Screen:**
  1. **(0:00 – 0:03)** Title card: `Blue Toad Fleet — Built solo, in 13 days, by one person.`
  2. **(0:03 – 0:45)** Open browser tab showing the raw 462-photo uncataloged gallery drop (`docs/screenshots/00-raw-auction-gallery.png` or `manifest.json`). Scroll through the uncataloged, unlabelled photos.
* **Voiceover:**
  > *"I run Richmond General, a one-person resale shop in Richmond, Illinois. Five minutes up US-12 across the Wisconsin line in Genoa City, Blue Toad Auctions publishes over four hundred uncataloged photos every other Saturday for an estate sale. There are no lot numbers and no online bidding app, and I have to get my absentee bids in by email before eight o'clock Friday night.
  >
  > Our pipeline begins with a sanctioned gallery drop — we work from the auction house's own published gallery by agreement rather than scraping it. For a solo shopkeeper running the counter, reviewing over four hundred unlabelled photos, identifying obscure makers, and researching comps by hand is impossible.
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
  > *For bounded trays and boxes, a second pass locates the physical container and itemizes only what is inside it. Our own live Vertex testing also hit a grounding trap: with structured output, the search queries survived but our citations disappeared. Blue Toad separates grounded research from schema extraction, takes the median of three samples, and refuses any price it cannot cite or reproduce."*

---

## 🎬 Beat 3: The Gate Console, Choice-Lot Guard & Bounded Challenge (1:45 – 2:45)

* **Visual on Screen:**
  1. Switch to the live Cloud Run Gate Console ([https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app](https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app)).
  2. Show the **Curator's Read**, **Question Queue**, bid sheet, and skip reasons.
* **Voiceover:**
  > *"On Friday afternoon, the fleet doesn't dump an unconstrained wishlist on the owner. It opens the Gate Console, serving serverless on Google Cloud Run.*
  >
  > *On BT-002, Gemini saw three labeled jewelry trays and asked whether the bid applied once or three times. The auctioneer confirmed x3. Blue Toad carried that written ruling into a seventy-five-dollar committed ceiling, eighty-six dollars and twenty-five cents all-in, and an explicit instruction telling the clerk to take all three.*
  >
  > *The curator cannot invent a pushback: without typed, lot-matched evidence, a challenge is discarded and silence ships — a guarantee enforced in code. Evidence, the budget impact, and the resulting allocation stay visible instead of being hidden inside a model response, and the operator owns every decision.*
  >
  > *And with deterministic keyed memory, answers to house policy questions are learned permanently, shrinking repetitive friction cycle after cycle."*

---

## 🎬 Beat 4: Live Google Cloud Proof & Final Sealed Sourcing Draft (2:45 – 4:00)

* **Visual on Screen:**
  1. Open Google Cloud Console showing the currently ready Cloud Run revision and service URL.
  2. Tab to `/api/lots` and open the cycle output named by the sealed artifact manifest.
  3. Show the current test run in terminal (`make test`).
* **Voiceover:**
  > *"Everything runs in production on Google Cloud Run and Vertex AI. The repository collects {{tests.collected}} tests; {{tests.passed}} pass locally and {{tests.skipped}} skip by policy.*
  >
  > *The final sheet commits {{money.committed_max|usd}} across {{cycle.approved_bids}} approved bids—{{money.committed_all_in|usd}} all-in after fees.*
  >
  > *The system compiles an operator-reviewed email draft and publishes it only with the same sealed cycle manifest as the workbook and decision state. Sending remains a human action.*
  >
  > *Blue Toad Fleet: Velocity to distill the information. Collaboration on the judgment."*

---

## Summary Checklist for Recording

- [ ] Opening Title Card shown for 3 seconds (`Built solo, in 13 days, by one person.`).
- [ ] Messy AuctionZip gallery (400+ photos) shown.
- [ ] Architecture diagram and evidence-backed photo grouping explained.
- [ ] Grounded-research / structured-extraction split explained.
- [ ] Live Cloud Run Gate Console demonstrated ([https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app](https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app)).
- [ ] BT-002 ×3 ruling and clerk instruction shown.
- [ ] Bounded challenge contract shown; if the verified cycle has no eligible conflict, say so.
- [ ] Google Cloud Console (`threebatdrone-prod-420`) and unit tests displayed.
- [ ] Total time: Under 4 minutes.
