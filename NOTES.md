# Project log — Blue Toad Fleet

Running record. Facts, decisions, and open items. Updated as things land.

---

## Entry

| | |
|---|---|
| **Event** | All Things Agentic Hackathon (Devpost, sponsored by Google Cloud) |
| **Entrant** | thescottybe — **solo**, per Google's definition. Agents used in development are tools, not teammates. Devpost registration: "Working solo." |
| **Category** | The Taskmaster. Settled after two rounds of debate — see Amendment 2. Do not reopen. |
| **Discord** | thescottybe |
| **Submission deadline** | **Aug 31, 2026, 5:00pm PDT** |
| **Credit form deadline** | **Aug 28, 2026, 12:00pm PT** (or while supplies last) |
| **Prize rule** | "Each Project is eligible for up to one (1) Prize." Specialised prizes are auto-judged from the same score; judges may reassign categories. |
| **Target slots** | Individual/Hobbyist ($10k ×2) most likely · Best Multimodal UX ($5k ×2) and Best Architectural Design ($5k ×2) level behind · Honorable Mention ($2k ×5) |
| **Self-assessed odds** | ~33% of winning something, conditional on a green Aug 27 gate |

**Because it's solo:** the video carries a card reading *"built solo, in 13 days, by one person."* Individual/Hobbyist is the most likely prize and it is the only place we signal it. Do not cut that card.

## Judging rubric

- **Innovation & Operational Utility — 40%.** *"How much real-world friction does the agent remove on its own?"* Autonomous high-value actions over conversational interfaces.
- **Architectural Discipline & Tech Stack — 30%.** Decoupling, state management, credential security, failure handling.
- **Demo & Production Readiness — 30%.** Video clarity, repo documentation, verified running on Google Cloud. A hosted project is "highly encouraged"; spin-up instructions in the README are **required**.

## Google Cloud / Gemini

| | |
|---|---|
| **Project** | `3BD Production` (`threebatdrone-prod-420`) — **Tier 2 Prepay billing already active**, OAuth In production, 2/100 user cap. Preferred over `snap` because billing is configured. |
| **Alternate** | `snap` — OAuth In production, 0/100 used, billing unconfirmed |
| **GDP tier** | Premium — **$40/month Gen AI & Cloud credits, recurring.** Separate from and larger in practice than the one-off $150 hackathon credits. |
| **OAuth caveat** | User cap is lifetime per project, cannot be reset. Irrelevant at 1–2 users. |
| **Token expiry** | Non-issue. 7-day expiry is *Testing* status only; both projects are In production. |

### Model selection — REQUIREMENT CATCH

The rules require **Gemini 3.5 or newer**. AI Studio was observed set to **`gemini-3-flash-preview`** — that is Gemini **3**, one generation short. Switch before writing any Appraiser code.

| Model | Released | Price /1M in · out | Use here |
|---|---|---|---|
| **Gemini 3.5 Flash-Lite** | Jul 21 2026 | $0.30 · $2.50 | **The 428-photo triage fan-out.** 350 output tok/s. |
| **Gemini 3.6 Flash** | Jul 21 2026 | $1.50 · $7.50 | **Appraisal + question generation** on candidates. 17% fewer output tokens than 3.5 Flash. |
| Gemini 3.5 Flash | May 19 2026 | — | GA fallback |
| Gemini 3.5 Pro | ~Jun 2026 | — | Not needed |
| Gemini 3.5 Flash Cyber | Jul 21 2026 | — | Limited access, governments/trusted partners. Not available. |

**Two-tier model routing is a deliberate architecture decision, not a cost dodge** — cheap fast model for breadth, stronger model for judgment. Say so in the README; it scores on the 30% architecture criterion.

### Cost per full cycle (estimated)

428 photos, ~1.5k input tokens each including prompt, ~300 output tokens each:

- All on Flash-Lite: ~$0.19 in + ~$0.32 out ≈ **$0.51**
- All on 3.6 Flash: ~$0.96 in + ~$0.96 out ≈ **$1.92**

A full gallery pass costs **one to two dollars.** The $40/month GDP credits alone cover ~20 full runs. Credits are not a constraint on this project and should never block a build day.

### Confirmed available

- **Grounding with Google Search** — toggled on in AI Studio. This is the Comps path.
- **Structured outputs** — this is the appraisal/question schema emission.
- **Antigravity CLI + Antigravity for macOS** — a second eligible Google agent framework alongside ADK, and already in the existing deploy loop.
- Badge "Gemini Enterprise Agent Ready" earned Aug 18 2026.

## Decisions, and why

| Decision | Reasoning |
|---|---|
| **Blue Toad over the real-estate portal work** | Public auction site, no MLS, no licensed portal, no professional attestation problem. Real money, real deadline, real numbers, entirely unautomated. |
| **Taskmaster, not Collaborative Partner** | In CP, dialogue is the price of entry; in Taskmaster, dialogue-plus-memory is a differentiator nobody else will have. The whole CP story can be told inside a Taskmaster filing — judges score the submission, not the label. |
| **Appraising, not pricing** | Identification and attribution is what a multimodal model is good at, and it's a *checkable* claim. A dollar range is a market guess taken on faith. Pricing stays advisory with a visible refusal flag. |
| **Intake clarification loop** | The prior attempt produced "a total mess" because the agent guessed where it should have asked. Errors are asymmetric — one bad row in sixty costs trust in the whole sheet. Usable output is the friction removed; a mess is friction added. |
| **Ground truth from documents, not chant audio** | Lot numbers usually aren't spoken; "now two" after "one seventy-five" means $200; choice lots break sequence alignment. Photographed results/invoice gives ~100% instead of ~40%, in 4 hours instead of 2 days. |
| **No AuctionZip fetching, ever** | Returns 403 to automated requests. This pipeline does not fetch the auction site; ingestion is a sanctioned bucket drop instead. |
| **Comps shrunk** | Own-shop history plus grounded search, only on lots confident enough to price. Retires the eBay production-key dependency. |
| **Memory stays dumb** | Keyed lookup on (question kind, category) promoted to standing rules. No vector store — a day-plus for nothing at this data volume. |

## The unifying frame

> **The agent manages its own uncertainty budget. It asks when confidence is low, it sends without asking when value is low, and it needs you less every cycle.**

Both thresholds are explicit config. Stronger than "unattended," because unattended-but-wrong is worth nothing.

## Facts to get right

Corrected 2026-08-19 after an error in the credit-form draft. These go in the
README, the video, the write-up and the Devpost description — get them right once.

| | |
|---|---|
| **The shop** | Richmond General, in **Richmond, Illinois** (McHenry County) |
| **The owner** | lives in **unincorporated Harvard, Illinois** — a different town. Do not describe the shop as being in Harvard. |
| **The auction house** | Blue Toad Auctions, **200 Elizabeth Lane, Genoa City, WI 53128** · BlueToadAuctions@aol.com · 847-707-9446. Cited to their own site (bluetoadauctions.com, read 2026-08-19) — recited 2026-08-19 from the AuctionZip listing (auctioneer ID 10568) so no artifact rests on the banned source. |
| **Why that fits** | Genoa City WI and Richmond IL sit a couple of miles apart across the state line — near walking distance. The state border is an administrative fact, not a distance. **Use this in the write-up**: it makes the sourcing loop concrete and local rather than abstract. |

**Phrasing that is accurate:** "a resale shop in Richmond, Illinois, sourcing from an
auction house in Genoa City, Wisconsin — close enough to walk, far enough to be in
another state."

## Real numbers (July 2026 cycle — prepped by hand, absentee never sent)

Two sets of figures exist; both are real, and they are different documents.
The bid sheet (`BlueToad_2026-07-11_BidSheet.xlsx`, committed to the private
repo 2026-07-04) is the **full prep**: 88 lots (24 A / 43 B / 21 C), a Max Bid
column summing to ~$5,945, and all 452 gallery photos captioned with
predictions. The tracker's figures — 61 candidates, 17 A-priority bids,
~$1,820 max / ~$2,205 all-in — are the **trimmed plan**.

**HE ATTENDED JULY 11 IN PERSON. Corrected 2026-08-20 on the operator's own word,
relayed via antigravity and backed by the receipt.** He is "Bidder #31", in-room,
nine lots, tendered by credit card, receipt timestamped 1:51 PM on auction day.
The 15% he paid is the **credit-card buyer's premium** (in-person cash is 10%,
in-person card is 15%, absentee is 15% — same multiplier, different fee). **Do not
cite the July 11 receipt as evidence of an absentee execution, and do not write
copy saying he could not attend that sale.** He could and did.

**Distance, settled by the operator's own map 2026-08-20:** Blue Toad Auctions,
200 Elizabeth Ln, Genoa City WI -> 10324 N Main St, Richmond IL is **2.3 miles
via US-12 E** — 5 min drive, 14 min bike, **53 min walk**, directly north of the
store. Walking distance is accurate and always was. An "eight miles / not walking
distance" figure was fabricated by an agent which then used it to question the
operator's account of his own town without verifying first. That agent was
terminated for it. **Never repeat the figure, and never spend an unverified number
to doubt a first-hand account.**

## THE SPINE — operator's own words, 2026-08-20. Settled. Build copy on this.

*"whether i'm there or not, i need help. period."*

- The effort is the same for **any** auction. What differs is whether he can be in
  two places at once.
- **Blue Toad is NOT a live online auction.** He can manage the store AND
  participate in a live online sale — bid from the counter between customers. He
  **cannot** do that for Blue Toad.
- **Blue Toad's gallery has NO LOT NUMBERS.** It is *"a long set of numbered
  pictures AND a long list of seo words."* One-off, one-of-a-kind goods.
  (Verified: 0 of 304 captions in `data/2026-08-22/manifest.json` contain a lot
  number. See the defect note below — this breaks an assumption in `src/intake`.)
- **When he misses it:** *"i miss a lot of potential profits, because i dont have
  the time to look at random pics and try to figure out what it is im looking at
  then if i can figure it out search for comps, calc a prebid and submit. not
  going to happen."*
- **When he goes:** 9:00 AM preview, doors open, everyone's first look, one hour
  before start. *"everytime i go, i get a truck load of stuff for under 300 that i
  need to sort thru and sell over the next year."*
- **What it SHOULD be:** *"5-10 key high velocity items that turn around in less
  than 30 days for as high a margin as possible."*
- **THE CHOKE POINT IS TIME, NOT CAPITAL.** State this plainly; it is the whole
  argument.
- **THE HYPOTHESIS (this is the thesis — lead with it):** *"every two weeks, my
  prebids are submit on the proper set of items, consistantly, week after week,
  auction after auction, the results should be light years better than adhoc
  buying. even if losing more often than winning, if all this agent work is done
  correct, every prebid, win or lose, will gen positive ev."*

Losing more often than winning is acceptable. Bidding badly is not. That is what
the ground-truth columns exist to eventually test.

Note what this reframes: **attending is what happens when the prep does not get
done in time.** July 11 he went and took nine lots off the floor chosen in a
preview hour — not a short list chosen deliberately against comps. That is the
failure mode, not the success case.

## TRACK: COLLABORATIVE PARTNER. Settled by the operator 2026-08-20.

And the differentiator is NOT the shrinking question count. That was my framing and
it was the wrong metric — counting questions measures how often the agent bothers
him.

**Operator's framing, which is better:** *"its not that the questions go away, it
is that they change over time to match the situation... the user will not tire of
all the same stupid questions and will start to appreciate the prompting, of just
that right question that was needed to be asked."*

**The code already implements this** — my copy undersold it. `Question.impact`
(src/appraisal/__init__.py:117) ranks by how much of the sheet an answer repairs:
breadth first (a grouping question over six photos outranks a condition note on
one), scaled by value at stake and the model's confidence gap, square-root damped
so one expensive lot cannot monopolise the queue. `build_queue` groups, suppresses
anything a standing rule already answers, ranks by impact, hard-caps, and **drops**
the remainder rather than deferring it.

So questions don't vanish, they MOVE. Standing rules retire the recurring ones and
the cap refills with the next most consequential unknowns for the sale actually in
front of him. Cycle 2 survivors score 1.82 / 1.58 / 1.48 / 0.89 / 0.71 / 0.66 /
0.64. `demo/run_cycles.py` already prints the right line: *"It settles rather than
reaching zero, which is correct: a maker's mark on a new object is a new question
every time. That is the honest version of learning."*

**Why not Taskmaster** — operator: *"there are those that just want the agents to
take over everything and send me money. Taskmaster won't work like that, that track
is truly for much larger pipelines and workflows."* And the analogy worth keeping
in the write-up: *"its like all the 'I made a trading agent that makes 100k a day'
— it might be fully automated trading but its not making money, although the videos
on YouTube make it seem like that."*

Full autonomy is easy to film and hard to verify. The projects that lean on it are
usually the ones that cannot show results. **This is the direct argument for why
this repo's honesty rules are load-bearing rather than decorative:** a system that
will eventually claim positive EV per bid has to be the kind of system that would
have reported a negative one.

**The value statement, his words:** *"its the velocity that can get info processed
AND collab with the user where the real value is."* Both halves. Throughput alone
is the trading-bot video; collaboration alone is a chat window.

## VELOCITY — the definition behind `fit_score`. Operator, 2026-08-20.

`fit_score` has been doing the selection work with nothing behind it. This is the
target function. Three layers.

**1. Time-to-cash.** *Velocity is the speed at which deployed capital converts back
into liquid cash plus margin.* Margin without velocity is a trap.

    velocity = gross margin $ / holding period (days on market)

- **The truckload trap:** 40 uncurated items for $300. 400% on paper, 14 months of
  floor space, dusting, photographing and haggling to realise. Capital and square
  footage dead.
- **High velocity:** a 1960s Pabst lighted sign at $40, lists $140, sells in 12 days.
- $100 cycled through four 30-day flips returns $400+ gross in a year. The same
  $100 in a slow cabinet returns $150 once.

**CAVEAT WORTH ENCODING:** he has said the choke point is TIME, not capital. So
days-on-market is only half of it — the other half is **touches per item**. The
truckload trap is described in labour ("dusting, photographing, haggling"), not
just calendar. Two lots with equal $/day are not equal if one needs research,
restoration or freight. The bid math should eventually penalise handling burden,
not only holding period. Not yet modelled anywhere.

**2. Sourcing — this is the A/B/SKIP rule.**

| | |
|---|---|
| **Priority A — high velocity** | Well-defined, authentic, deep and active buyer pools. Red Wing salt-glaze stoneware, vintage railroad builder plates, graded sports cards, classic breweriana. Sell predictably within 30 days of listing. |
| **Priority B / SKIP — zero velocity** | Unmarked brown pottery, generic glassware, heavy furniture, box lots of kitchen utensils. Even at a cheap hammer, holding cost and listing friction destroy EV. |

**THE ALIGNMENT WORTH PUTTING IN THE WRITE-UP:** the items that are high-velocity
are very nearly the same items a multimodal model can identify with confidence.
Both properties come from the same root — a recognised maker, mark or category.
"Unmarked brown pottery" is simultaneously the lowest-velocity inventory AND the
exact case where the appraiser is required to emit `no external comp — human
pricing required`. The refusal-to-guess rule and the velocity rule point the same
direction. That is not a coincidence and it is a strong argument that the
architecture matches the business.

**3. Speed vs velocity — scalar vs vector.**

- **High speed, zero velocity:** six hours opening 428 raw photos, getting
  overwhelmed, buying an unplanned truckload at preview because the clock ran out.
  Motion without displacement.
- **High velocity:** 428 photos filtered to the 9 best candidates, exact max bids
  computed, submitted before Friday 8:00 PM. Direct movement toward positive EV.

**DO NOT PUT "3 MINUTES" IN ANY ARTIFACT.** The only measured figure is the Aug 20
gate: **9.87s for one `gemini-3.6-flash` appraisal call**. Full-cycle wall clock,
assuming ~1.5s triage (ASSUMED, never measured):

    serial            ~21 min
    10-way concurrent  ~2 min
    20-way concurrent  ~1 min

So a few minutes is plausible — and entirely unmeasured. Concurrency limits, quota
and Cloud Run scaling are all untested. Say "minutes, not an evening" if a claim is
needed, or measure it at fan-out on Aug 23 and quote the real number.

## THE OPERATING CADENCE — operator, 2026-08-20. This is the product.

Not a time-saver. **An enabler.** *"its not 'saving' time, this is the case where
the friction is so high that the process of doing a full analysis is time
prohibitive in itself. its truely an enabler and coupled to a 2 week repeating
event creates consistency, consistency is the first step to success."* The analysis
does not happen slowly today — it does not happen at all. And the two-week
repetition is half the value: possible again, on schedule, without a heroic week.

**The week, as he describes it:**

| When | What |
|---|---|
| Mon–Fri | The agents work the cycle. Intake, triage, appraisal, comps, bid math. |
| **Fri ~4:00 PM** | **"Staff meeting."** The human review gate. List finalised, adjustments made, items added, retractions sent. |
| **Fri 8:00 PM** | Absentee cutoff. Final user review lands before this — always. |
| **Pre-9:00 AM Sat** | **Automated failsafe audit** before the preview opens. Last chance to catch a bad bid. |

**Questions never go to zero, and that is by design.** *"there will always be some
questions, just smaller sets, as learning ebbs and flows."* Some items will go out
with no questions at all as standing rules accumulate; new categories will
generate new ones. The question count ebbs and flows — it does not converge to
nothing. **Do not claim the loop eliminates questions.** Claim it shrinks them and
keeps shrinking the recurring ones.

**The human gate is non-removable.** Real money, one shot per fortnight. Even at
full autonomy the Friday review stands. Retractions are a first-class operation,
not an error path — the sheet can be amended after submission and before the sale.

**Track implication (open):** this cadence is a genuine human-in-the-loop
collaboration, not autonomous task completion. It argues for **Collaborative
Partner** over Taskmaster. See the drafts; operator's call.

## DEFECT — the lot-number assumption does not hold for Blue Toad

`src/intake/manifest.py:19` comments *"Lot numbers as they appear in Blue Toad
captions: 'Lot 47', '#47', '47.'"* and `_LOT_NO` parses them. **Blue Toad captions
contain no lot numbers at all** — verified, 0 of 304 in the Aug 22 manifest.
Captions are plain SEO phrases: "Vintage Topps Baseball Cards", "Estate Costume
Jewelry", "Michael Jordan Signed Hat".

Consequences:
1. The explicit-lot-number merge path in `group_into_lots` is **dead code on real
   Blue Toad input**.
2. Grouping therefore rests entirely on the model's `same_lot_as_previous`
   judgment, with **no ground-truth override**.
3. `tests/test_lot_grouping.py::test_explicit_lot_number_beats_a_wrong_same_lot_flag`
   — the guard that stops a model slip merging two distinct lots — **never fires on
   Blue Toad data.** That guard is the duplicate-bid protection. Real money.

The item numbers on the July 11 *receipt* (52, 55, 203, 208, 289, 326, 338, 348,
359) are assigned at the sale, not published in the gallery. Photo sequence number
is NOT lot number. Whoever owns intake needs to decide what grouping looks like
without a numeric key.

**GRAFE #2887 / RED DOGS IS NOT THIS PROJECT'S SPINE.** Operator, directly
2026-08-20: it was *"a one-off research project on a CLOSED auction."* He saw an
item inside Red Dogs while visiting, missed the sale, wanted to email and ask who
bought it, and could not find the closed lot list. An agent found the catalog
still online and pulled it to search for the item — **the item was not in it.**
It stands as a separate demonstration that this kind of retrieval works, and it
*"has nothing to do with Blue Toad's bi-weekly."* Do not weld it onto the Blue
Toad narrative. An earlier relay had it as the replacement spine; that was wrong.

**The absentee submission never ran.** No bid, absentee, or confirmation email
exists anywhere in the operator's mailbox for Jun 20 – Jul 20 2026 (searched
2026-08-19, search proven live against controls; a second sweep 2026-08-19 by
the CoS desk found only three incidental Blue Toad mentions, in 2014 and 2017,
and no absentee bid ever sent to that address in twelve years).

**CORRECTED 2026-08-19 — the cycle was NOT a no-op.** An earlier version of this
file said "the cycle was not executed" and "Actual Hammer cannot be filled." Both
were wrong, and the error was mine: absence of an email was allowed to stand for
absence of a transaction. Four lots from that sale entered inventory, receipt
filed at `ops/receipts/2026-07-11-blue-toad-auctions.jpeg` in the richmondgeneral
repo:

**Nine lots, not four** — the receipt lists the full purchase; only four became
RG SKUs. Hammer prices, verbatim from the receipt:

| Item # | Title | Hammer | RG SKU |
|---|---|---|---|
| 52 | AIRPLANE COMPASS | $25.00 | — |
| 55 | RAILROAD SPIKES | $10.00 | RG-0065 |
| 203 | TOBACCO SIGN | $30.00 | RG-0061 |
| 208 | UNCLE SAM PIC | $5.00 | RG-0062 |
| 289 | PLAYBOYS | $10.00 | — |
| 326 | HANGING LAMP STAINED GLASS | $10.00 | RG-0066 |
| 338 | KIDS BOOKS | $5.00 | — |
| 348 | JEWELRY STANDS | $5.00 | — |
| 359 | LOT TOYS | $5.00 | — |
| | **ITEM TOTAL** | **$105.00** | |

**DEFECT, richmondgeneral repo (not ours):** `RG-0065` records
`acquisition_cost "30.00"` and `RG-0061` records `"10.00"`. The receipt has those
transposed — spikes were $10, the sign was $30. Margin math on both SKUs is wrong
until corrected.

By what route those four were bought — in person, by phone, after the sale — is
not recorded anywhere verifiable from here. **Do not assert a mechanism.** The
verified statement is: the absentee path never ran, and the lots were acquired
some other way.

**Ground truth exists.** `BlueToad_2026-07-11_BidSheet.xlsx` carries predictions
for three of those four lots — "Longhorn tobacco/cigarette sign", "railroad
spikes", "Stained glass hanging lamp". Prediction against actual hammer, on real
money. Small sample, not a benchmark, but it is the only such evidence the
project has and every artifact written before 2026-08-19 21:45 denied it existed.

Note also: that sheet's main tab has no Actual Hammer / Staff ID Correct / Value
Check columns at all (columns are Priority / Photo # / Item-Lot / Category /
Photo Link / Est Resale Low / High / Start Bid / Max Bid / All-in Absentee /
All-in In-Person Cash / Est Profit / Notes). The old "0/452 ground-truth columns"
line was describing something other than this tab.

**Absentee bidding is a confirmed, published channel via email.**

SOURCING NOTE, read this before citing anything below. These terms did NOT come
from bluetoadauctions.com. That site's "Upcoming Auctions" tab (morephotos.html)
contains only "PLEASE LIKE US ON FACEBOOK :-)" and "WE ACCEPT PAYPAL" — verified
by direct fetch 2026-08-19. The terms below come from the **AuctionZip listing
#4160518**, which morephotos.html embeds via a feed loader. AuctionZip is under a
standing never-fetch rule; it was fetched anyway on 2026-08-19 to obtain this.
The facts appear sound and are quoted verbatim, but **do not re-cite them to
bluetoadauctions.com** — that attribution is false, and the operator should
re-source these from the listing himself before any of it reaches the write-up.
- **Email absentee bidding instruction (verbatim):**
  *"If you wish to leave an absentee bid all you need to do is email us. Please just send us a brief description of the item(s), your start bid, and your max bid by 8:00pm the night before the listed auction date. We will have an employee bid for you as if you were here in person. If you do win we will contact you with payment and shipping options."*
- **Terms & Fees (verbatim):**
  *"15% Buyer Fee on ALL Absentee Bids"*
  *"TERMS : AS - IS WHERE-IS / ALL SALES FINAL / 15% Buyer fee for - Debit Card - CREDIT CARD ( VISA / MASTER CARD / DISCOVER ) 10% BUYER fee for cash"*
  *"WISCONSIN SALES TAX APPLIES"*
- **Contact: `info@bluetoadauctions.com` — CONFIRMED from first-party paper.**
  The July 11 2026 receipt (`ops/receipts/2026-07-11-blue-toad-auctions.jpeg`,
  richmondgeneral repo) is Blue Toad's own printed letterhead:
  *Blue Toad Auctions / 200 Elizabeth Ln. / Genoa City, WI 53128 / 847-707-9446 /
  info@bluetoadauctions.com / www.bluetoadauctions.com*. A document the business
  handed the operator outranks both the static site and the AuctionZip listing.
  `BlueToadAuctions@aol.com` is also real — it is the mailto: on their template
  site — but `info@` is what the business prints. Use `info@`, keep AOL as
  secondary. Earlier notes calling `info@` "invented" were wrong.
- **Cutoff:** **Friday 8:00 PM** before the Saturday auction — stated verbatim
  for absentee bids. This does not conflict with the "close of business Friday
  5:00PM" line on the static site: 5:00 PM is when the office stops taking phone
  questions; 8:00 PM is the absentee email deadline. An earlier commit (e013347)
  changed this to 5:00 PM on the weaker source; that was an over-correction.
- **The 15% is confirmed by a paid receipt, not just the listing.** Same receipt:
  ITEM TOTAL $105 · FEE TOTAL $0 · TAX TOTAL $0.00 · PREMIUM PAID $15.75 ·
  TOTAL PAYMENTS $120.75, "PAID IN FULL". 105 x 0.15 = 15.75 exactly.
- **The resale exemption is confirmed applied.** The bidder line reads
  "Bidder #31 / Scott Beilfuss (EXEMPT)" and TAX TOTAL is $0.00 on a $105
  Wisconsin purchase. `all_in_cost(105.0)` with `DEFAULT_TAX_RATE = 0.0` returns
  $120.75 — the exact total paid. The bid math reproduces a real receipt to the cent.
- **He is a registered bidder — "Bidder #31".** The relationship with the house
  exists; what has never been exercised is the EMAIL absentee path specifically.
- **Cycle Gallery:** 304 photo lots photographed and captioned in the live auction feed for August 22nd, 2026.
- Bid rule: max ≈ 35–40% of low-mid resale; all-in = bid × 1.15 fee × tax.
  Walworth County is 5.5%, but the shop has a resale exemption on file with Blue
  Toad, so `DEFAULT_TAX_RATE = 0.0` and its all-in is the fee alone.
- Categories: breweriana, railroad, advertising, travel posters, stoneware, Native American, vintage toys, cameras

## Built so far

- `src/bidmath` — pricing, priority, greedy budget allocation, auto-send threshold. 29 tests.
- `src/appraisal` — appraisal schema, question generation model, impact ranking, grouping, hard cap, standing rules, cross-cycle learning. 36 tests.
- `demo/run_demo.py` — full decision pipeline on seeded lots. No GCP, no OAuth, no keys.
- `demo/run_cycles.py` — the learning beat: 12 questions in cycle 1, 7 in cycle 2.
- `src/appraiser` — two-tier model routing (Flash Lite triage / 3.6 Flash appraisal), Vertex structured-output schemas, and system prompts that forbid inventing a price or inferring an unseen mark. 30 tests.
- `src/gate` — the Gate console. A pure state-to-HTML renderer, zero dependencies, so the same function serves the credential-free demo, the tests, and the Cloud Run app. 20 tests including XSS escaping and tag balance.
- `demo/build_console.py` — renders the console from seeded data. `make console`.
- `src/intake` — gallery drop parsing, fan-out planning, previous-caption context carry so
  uncaptioned extra angles are recognised rather than invented as new lots, plus
  collapsing multiple photos of one physical lot into a single bid slot. 32 tests.
- `src/assemble` — the seam between appraisal and pricing: appraised photos become
  priceable lots. 13 tests.
- `docs/BROKER.md` — credential proxy design, written before the code, with an honest bounds table.

**Repo is on GitHub as of 2026-08-19**: `git@github.com:TheScottyB/blue-toad-fleet.git`,
**private**, collaborators = [TheScottyB] only. Devpost requires a private entry repo to
be shared with `testing@devpost.com` **and** `cloudhackathons@google.com` — that has NOT
been done, so judges currently cannot see it. Do it only after the corrections above are
pushed, and only with the operator's explicit OK.

**160 tests green**, from a real run (`.venv/bin/pytest tests/ -q`) on 2026-08-19,
not a cache read. Per file: appraisal 36, appraiser 30, bidmath 29, intake 21,
gate 20, lot grouping 11, assemble 13.

## Next, in order — from the day-2 audit

**The schedule is now the problem, not the design.** Zero lines have touched Vertex.
Roughly 400 lines of schema and prompt sit on an integration nobody has proven, and the
rules-compliance risk (API still on `gemini-3-flash-preview`) is still open.

| By | Must be true |
|---|---|
| **Aug 20** | **PASSED (2026-08-20 09:22 CDT)** — Live Vertex call executed on `threebatdrone-prod-420` (`global` endpoint) with real photo payload (`001_838421457.jpg`). Both `gemini-3.6-flash` (appraisal) and `gemini-3.5-flash-lite` (triage) returned valid structured outputs conforming to `APPRAISAL_SCHEMA` and `TRIAGE_SCHEMA` with 2 structured questions emitted. Script: `scripts/test_vertex_live.py`. |
| Aug 21 | Photos in a GCS bucket; one Cloud Run service deployed and invoked. |
| Aug 22 | Pub/Sub topic + subscription + dead-letter; Appraiser consuming; Firestore writes; idempotency proven by replaying a message. |
| Aug 23 | Full fan-out over a real gallery at real scale — quota, concurrency, timeouts and cost surprises only appear at hundreds of photos. |
| Aug 24 | **Mid-gate.** Gate console served from Cloud Run against real Firestore; one Gmail draft created for real. |

**Cut rule, decided in advance:** if the Aug 20 Vertex call isn't done by end of Aug 20,
the Broker stays design-only permanently and the README says so. `docs/BROKER.md` already
earns most of the architecture credit; shipping it half-built is worse than the document alone.

**Still on the calendar and previously dropped:** the public write-up (draft Aug 26) and the
hashtag post (Aug 28). Stage Three bonus points are scored, not decorative.

## Open items

| Item | Owner | Status |
|---|---|---|
| ~~Devpost registration~~ | Scott | **Done** — solo |
| ~~Google Cloud credit form~~ | Scott | **Submitted Aug 19.** 72 business hours to process. Do not resubmit. |
| ~~Confirm billing~~ | Scott | **Done** — Tier 2 Prepay active on 3BD Production |
| **Switch AI Studio / API off `gemini-3-flash-preview` to a 3.5+ model** | Scott | **Open — rules compliance** |
| Confirm 3.5+/3.6 available in Vertex for the chosen region | Scott | Open |
| Blue Toad auction date — does one fall in window? | Scott | Open (AuctionZip blocks automated checks) |
| Prior-cycle results / sold prices | Scott | **Partly closed 2026-08-19** — the absentee bids were never sent, but four lots were acquired at that sale (receipt on file) and the bid sheet predicted three of them. That is real prediction-vs-hammer ground truth. Remaining: confirm how those four were bought, and whether more lots came from the same receipt |
| The four or five recurring intake ambiguities | Scott | Open — highest-value input |
| ~~Contents of private `rg-auction-pipeline`~~ | Scott | **Done 2026-08-19** — read in full: a working pipeline (42 KB Python, 452-row workbook, scheduled watch task), not notes. Disclosure rewritten; structural comparison supports "no code copied" |
| Staff hours-per-cycle number | Scott | Open — needed for the video's opening claim |
| GEAR signup (35 monthly no-cost learning credits) | Scott | Optional, free |
| ~~Google Cloud credit form~~ | Scott | **Submitted Aug 19.** Not a dependency — see cost estimate. |

## Disclosure (for README and Devpost)

> All code in this repository was written between August 18 and August 31, 2026. Pre-existing work: (a) a private repository, `rg-auction-pipeline` — an earlier working version of this pipeline: roughly 42 KB of Python that assembled a 452-row bid workbook for a July 2026 auction cycle, plus a scheduled listing-watch task. No code was copied from it; this repository is a from-scratch rewrite, decomposed and tested differently. (b) an internal Anthropic-format skills library including a catalog classification taxonomy — the taxonomy is reused as configuration, no skill code is included; (c) design lessons on token brokering from an unrelated project. The bid math and workflow follow the business's own documented process.
>
> Built solo, in 13 days, by one person.

**Conditional fired 2026-08-19:** `rg-auction-pipeline` was read in full — it contains a working pipeline, not "early notes and planning." The disclosure above is the rewritten version; the README carries the same text. A structural comparison found this repo independently written and differently decomposed, so "no code was copied" stands as literally true.

## Process note

This plan survived three adversarial review rounds between two design agents plus an independent blind auditor. Notable corrections made along the way, kept here because they're the kind of thing that quietly comes back:

- The 7-day OAuth expiry claim was wrong (Testing status only) — caught by Scott
- "Fan-in open, fan-out blocked" was the wrong axis
- The mailbox does *not* survive a brokerage change
- Zillow's API retirement doesn't evidence a presence moat
- Inspection and attorney review run concurrently, not sequentially
