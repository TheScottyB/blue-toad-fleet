# Blue Toad Fleet — 4-Minute Walkthrough Video Script

> **Recording note — the cut in `media/blue_toad_fleet_demo.mp4` was captured
> 2026-08-20 17:56, and the figures narrated in Beat 4 are that evening's sheet:
> 12 lots, $335.00 max, $385.25 all-in, 173 tests.**
>
> The sheet has since moved twice for reasons that are recorded in git, not
> drift: the auctioneer ruled the labelled jewelry tray run "a x3 bid"
> (`c643171`), and BT-181 was found to be a close-up of trays already inside
> BT-002 and declined rather than bought twice (`eb8bd7a`). Current figures are
> **9 lots, $275.00 max, $316.25 all-in, 565 passing tests (572 collected)** — matching the absentee
> sheet Blue Toad actually received, which `tests/test_sheet_matches_what_was_sent.py`
> pins.
>
> This note is deliberately not a rewrite of the narration. The script records
> what was said on camera; silently editing it to quote today's numbers would
> make the document disagree with the video it transcribes, which is the exact
> failure it would be trying to hide. Re-record Beat 4 to close the gap.

## Required replacement lines for the final submission cut

These lines are not present in the current `media/blue_toad_fleet_demo.mp4` and
must be recorded before they can be claimed by the video.

* **Beat 2, replace the final pricing sentence:**
  > *"Live Vertex testing uncovered a grounding trap: structured output kept the search queries but dropped every citation. Blue Toad separates grounded research from schema extraction, takes the median of three samples, and refuses any price it cannot cite or reproduce."*
* **Beat 3, replace the generic Choice-Lot sentence:**
  > *"On BT-002, Gemini saw three labeled jewelry trays and asked whether the bid applied once or three times. The auctioneer confirmed x3. Blue Toad carried that written ruling into a $75 committed ceiling, $86.25 all-in, and an explicit instruction telling the clerk to take all three."*
* **Beat 4, replace the old result and test-count sentences:**
  > *"The final sheet commits $275 across nine approved bids—$316.25 all-in against $713 to $879 in estimated gross resale, a 2.25 to 2.78 times gross multiple before selling costs. The repository collects 572 tests; 565 pass locally and seven network checks skip by default."*

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

## 🎬 Beat 2: Spatial Room Graph & Container Decomposition (0:45 – 1:45)

* **Visual on Screen:**
  1. Switch to the Architecture Diagram ([`docs/architecture_diagram.png`](architecture_diagram.png)) or terminal showing Vertex AI model routing.
  2. Show Gemini 3.5 Flash-Lite triage logs ($0.30/cycle) and Gemini 3.6 Flash container decomposition on the Edison cylinders (Photo #41) and Topps cards (Photo #1).
* **Voiceover:**
  > *"Generic vision models treat an auction gallery as a disconnected bag of 450 photos. But auctioneers don't teleport—they walk a physical room. Blue Toad Fleet reconstructs the physical 200 Elizabeth Lane pole barn showroom.*
  >
  > *By classifying table surface invariants—like blue vinyl tablecloths versus raw plywood—and tracking peripheral co-visibility on image borders, the agent maps every lot to its physical location. It collapses 10 loose under-table box photos into ONE Poppy Trail dinnerware set, eliminating 95 duplicate multi-angle bids.*
  >
  > *Crucially, spatial isolation enables Container Lot Decomposition: the agent zooms into mystery bins to mine for gold—extracting 11 Edison cylinder records and vintage Topps cards—while explicitly masking out adjacent table clutter to prevent dirty comps. And when an unmarked piece of pottery has no verifiable comps, it enforces our Honest Refusal Rule: 'NO EXTERNAL COMP — human pricing required'."*

---

## 🎬 Beat 3: The Gate Console, Choice-Lot Sniper & Proactive Pushback (1:45 – 2:45)

* **Visual on Screen:**
  1. Switch to the live Cloud Run Gate Console ([https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app](https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app)).
  2. Hover over the **Interactive 2D Showroom Floor Map**, the **Curator's Negotiation Banner**, and the **Question Queue**.
* **Voiceover:**
  > *"On Friday afternoon, the fleet doesn't dump an unconstrained $14,000 wishlist on the owner. It opens the Gate Console—serving serverless on Google Cloud Run in universal dark mode.*
  >
  > *The fleet acts as an expert commercial peer. It surfaces our 'Choice-Lot Sniper'—protecting us on wall runs of travel posters and table lines of lanterns by enforcing a strict single-unit limit, preventing a $900 auctioneer multiplication trap.*
  >
  > *When I told the agent to drop all sports cards due to store backlog, it didn't act like a passive yes-man. It pushed back using real-time eBay velocity: defending Photo #1—13 Golden Era 1959–69 Topps cards in top-loaders at a $100 cap because of rapid 14-day liquidity at a 4x margin.*
  >
  > *And with deterministic keyed memory, answers to house policy questions are learned permanently, shrinking repetitive friction cycle after cycle."*

---

## 🎬 Beat 4: Live Google Cloud Proof & Final Sealed Sourcing Draft (2:45 – 4:00)

* **Visual on Screen:**
  1. Open Google Cloud Console on project `threebatdrone-prod-420` showing Cloud Run revision `blue-toad-fleet-00009-8kb` and Vertex AI metrics.
  2. Tab to `/api/lots` and open the sealed [`data/aug22_absentee_bid_email.txt`](../data/aug22_absentee_bid_email.txt).
  3. Show the 173 passing unit tests in terminal (`make test`).
* **Voiceover:**
  > *"Everything runs in production on Google Cloud Run and Vertex AI. All 173 unit tests pass in under half a second.*
  >
  > *Our greedy allocator committed exactly $335.00 across 12 approved high-velocity lots—$385.25 all-in with the mandatory 15% absentee fee, strictly formatted to standard $5.00 auction increments.*
  >
  > *The system compiles the final sealed email draft ready for info@bluetoadauctions.com while Richmond General stays open for business.*
  >
  > *Blue Toad Fleet: Velocity to distill the information. Collaboration on the judgment."*

---

## Summary Checklist for Recording

- [ ] Opening Title Card shown for 3 seconds (`Built solo, in 13 days, by one person.`).
- [ ] Messy AuctionZip 450-photo gallery shown.
- [ ] Architecture diagram & Spatial Room Graph explained.
- [ ] Grounded-research / structured-extraction split explained.
- [ ] Live Cloud Run Gate Console demonstrated ([https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app](https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app)).
- [ ] BT-002 ×3 ruling and clerk instruction shown.
- [ ] Proactive Pushback on 1959–69 Topps cards highlighted.
- [ ] Google Cloud Console (`threebatdrone-prod-420`) and unit tests displayed.
- [ ] Total time: Under 4 minutes.
