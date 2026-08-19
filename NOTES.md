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
| **The auction house** | Blue Toad Auctions, **Genoa City, Wisconsin** (AuctionZip WI listing, auctioneer ID 10568) |
| **Why that fits** | Genoa City WI and Richmond IL sit a couple of miles apart across the state line — near walking distance. The state border is an administrative fact, not a distance. **Use this in the write-up**: it makes the sourcing loop concrete and local rather than abstract. |

**Phrasing that is accurate:** "a resale shop in Richmond, Illinois, sourcing from an
auction house in Genoa City, Wisconsin — close enough to walk, far enough to be in
another state."

## Real numbers (from the business's tracker)

- ~428 gallery photos per cycle
- 61 candidate lots shortlisted
- 17 A-priority absentee bids
- ~$1,820 max / ~$2,205 all-in committed
- Friday 8:00 PM absentee cutoff
- Bid rule: max ≈ 35–40% of low-mid resale; all-in = bid × 1.15 fee × tax
- Categories: breweriana, railroad, advertising, travel posters, stoneware, Native American, vintage toys, cameras

## Built so far

- `src/bidmath` — pricing, priority, greedy budget allocation, auto-send threshold. 25 tests.
- `src/appraisal` — appraisal schema, question generation model, impact ranking, grouping, hard cap, standing rules, cross-cycle learning. 29 tests.
- `demo/run_demo.py` — full decision pipeline on seeded lots. No GCP, no OAuth, no keys.
- `demo/run_cycles.py` — the learning beat: 12 questions in cycle 1, 7 in cycle 2.
- `src/appraiser` — two-tier model routing (Flash Lite triage / 3.6 Flash appraisal), Vertex structured-output schemas, and system prompts that forbid inventing a price or inferring an unseen mark. 24 tests.
- `src/gate` — the Gate console. A pure state-to-HTML renderer, zero dependencies, so the same function serves the credential-free demo, the tests, and the Cloud Run app. 17 tests including XSS escaping and tag balance.
- `demo/build_console.py` — renders the console from seeded data. `make console`.
- `src/intake` — gallery drop parsing, fan-out planning, previous-caption context carry so
  uncaptioned extra angles are recognised rather than invented as new lots. 19 tests.
- `docs/BROKER.md` — credential proxy design, written before the code, with an honest bounds table.

**126 tests green.** Verified from a clean extract.

## Next, in order — from the day-2 audit

**The schedule is now the problem, not the design.** Zero lines have touched Vertex.
Roughly 400 lines of schema and prompt sit on an integration nobody has proven, and the
rules-compliance risk (API still on `gemini-3-flash-preview`) is still open.

| By | Must be true |
|---|---|
| **Aug 20** | One real Vertex call from `threebatdrone-prod-420` on a 3.5+ model returning valid structured output against `APPRAISAL_SCHEMA` for one real photo. Until this exists nothing else is real. |
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
| Prior-cycle results / sold prices | Scott | Looking — a screenshot is fine, it's the ingestion path |
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
