# Blue Toad Fleet

An agent fleet that turns a rural Illinois resale shop's biweekly auction sourcing —
hundreds of gallery photos, a Friday 8PM absentee deadline, real money — into a
triaged, priced, budget-allocated bid sheet and a ready-to-send prebid email.
Unattended from ingest to draft.

Built for the All Things Agentic Hackathon, August 2026.

---

## Status — day 2 of 13

| Component | State |
|---|---|
| Bid math, priority, allocation, auto-send | **Built** — `src/bidmath`, tested |
| Intake clarification queue + cross-cycle memory | **Built** — `src/appraisal`, tested |
| Appraiser routing, schemas, prompts | **Built** — `src/appraiser`, tested |
| Gallery drop parsing and fan-out planning | **Built** — `src/intake`, tested |
| Gate console renderer | **Built** — `src/gate`, tested |
| Credential-free demos | **Built** — `make demo`, `make cycles`, `make console` |
| Credential broker | **Designed** — [docs/BROKER.md](docs/BROKER.md), not implemented |
| Vertex client & model routing | **Built** — `src/appraiser`, live verified on `threebatdrone-prod-420` |
| Cloud Run deploy, Pub/Sub, Firestore | **Planned** |
| Watcher, Comps, ledger | **Planned** |

Nothing below is described as working unless this table says it is.

## Try it in 30 seconds — no GCP project, no OAuth, no API keys

```bash
git clone <repo> && cd blue-toad-fleet
make install
make demo
```

`make demo` runs the real decision pipeline over a seeded set of appraised lots
with stubbed adapters. You will see per-lot decision cards, the auto-send
split, refused lots, and the allocated sheet against a budget cap. This is the
same code path that runs in production downstream of the Appraiser.

```bash
make test    # 160 unit tests
```

## The problem

Richmond General is a one-person resale shop in Richmond, Illinois. Blue Toad
Auctions is 2.3 miles north, over the Wisconsin line — five minutes up US-12.

Whether the owner is in the room or behind the counter, the work is the same, and
it is the work he does not have time for.

**Blue Toad is not a live online auction.** There is no bidding app to keep half
an eye on between customers, and there are no lot numbers. What the house
publishes is a long run of numbered photographs and a long list of SEO keywords,
for goods that are one-off and one-of-a-kind. A live online sale he can follow
from the counter. This one he cannot.

So the cycle has two outcomes and both cost him.

**When he goes**, he goes at 9:00 AM for the preview — doors open, everyone gets
their first look, one hour before the start. He comes back with a truckload for
under $300, and then sorts and sells it across the following year.

**When he cannot go, he misses it.** Not for lack of money. Preparing an absentee
bid means opening hundreds of unlabelled photographs, working out what each object
actually is, finding comparables, computing a maximum, and submitting before
Friday at 8:00 PM. For one person also running a shop, that is not going to
happen — and it never has. The absentee channel is real, published, and has never
once been used.

Capital is not the constraint. **Time is.**

And a truckload is not the goal. The goal is five to ten high-velocity items that
turn in under thirty days at the best margin available.

### The hypothesis this project tests

If the prebids go in on the right set of items, consistently, every two weeks,
auction after auction, the results should beat ad-hoc buying by a wide margin. And
if the identification, the comps and the bid math are each done properly, **every
prebid carries positive expected value — win or lose.**

Losing more often than winning is acceptable. Bidding badly is not. That is the
claim, and it is the thing the ground-truth columns are there to eventually test.

The July 2026 cycle, from the shop's own prep, is what one round of that work
costs by hand:

- **428 gallery photos** reviewed by hand
- **88 lots** worked up on the full bid sheet — 24 A-priority, max bids
  summing to **~$5,945**
- trimmed to a plan of **~61 candidates / 17 absentee bids / ~$1,820 max**
- Hard cutoff: **Friday 8:00 PM** — the auction house's own listing states
  *"send us a brief description of the item(s), your start bid, and your max bid
  by 8:00pm the night before the listed auction date."*
- Bid rule: **max ≈ 35–40% of low-mid resale**, all-in = bid × 1.15 absentee fee
  × tax. The 15% is published (*"15% Buyer Fee on ALL Absentee Bids"*); Walworth
  County is 5.5%, but the shop has a resale exemption on file, so its own all-in
  is the fee alone.

That prep was finished for July 11 and the absentee submission never ran. The
owner attended in person instead — Bidder #31, nine lots, $105 hammer, paid by
card. Which is the point: **attending is what happens when the prep does not get
done in time.** Nine lots off the floor, chosen in a preview hour, rather than a
short list chosen deliberately against comps.

## What the fleet does

| Component | Job |
|---|---|
| **Watcher** | Cloud Scheduler job polling a Gmail label for the auction announcement. Opens a cycle, pings Slack, schedules the Friday nag. |
| **Intake** | Eventarc on a GCS bucket. Staff drop the saved gallery page; Intake fans out one Pub/Sub message per photo. |
| **Appraiser** | ADK + Gemini 3.5 multimodal. Identification, category, condition, fit score. Idempotent on `(cycle, photo)`. |
| **Comps** | *Planned.* Own sales history plus Gemini with Google Search grounding, run only on lots confident enough to price. Everything else emits `no external comp — human pricing required`. |
| **Bidder** | The bid math in [`src/bidmath`](src/bidmath/__init__.py). Priority, pricing, greedy allocation against a budget cap. |
| **Gate** | Review, trim, approve → Gmail draft. Lots at or under a configured all-in threshold send without a human. |
| **Broker** | Credential proxy. Agents hold no tokens. See [docs/BROKER.md](docs/BROKER.md). |

## Model routing

Two tiers, deliberately. **Gemini 3.5 Flash Lite** triages all ~428 photos —
a wide fan-out is a throughput problem, and Flash Lite runs it for about
thirty cents. **Gemini 3.6 Flash** appraises the ~60 survivors, where judgment
matters. One model for both would waste money on the first pass or accuracy on
the second. A full cycle costs roughly **$1.50–2.00**: a real appraisal call
ran 2,149 tokens in and 917 out — 589 of them thinking tokens, which bill as
output and roughly double the naive per-call estimate.

The model endpoint is pinned separately from `CLOUD_RUN_REGION` because it has
to be: both models 404 on `us-central1` and serve only from the `global`
endpoint (verified 2026-08-19), so `.env.example` sets `VERTEX_LOCATION=global`.

## Three design decisions worth explaining

**Pricing is advisory; triage is the product.** Sorting hundreds of photos into
categorised candidates with condition notes is what a multimodal model is
genuinely good at. Defending a dollar figure for a piece of breweriana from a
photograph is what it is worst at — and the shop owner knows the market better
than the model does. So lots without an external comp are **not priced**. They
are surfaced with `no external comp — human pricing required`. Refusing to
guess is a feature.

**The clarification loop is the point.** An earlier attempt at this pipeline
produced an unusable spreadsheet because the agent guessed where it should have
asked. Errors here are asymmetric — one wrong row in sixty costs trust in the
whole sheet, not a sixtieth of it. So the Appraiser emits ranked, grouped,
hard-capped questions wherever a determining attribute isn't visible, and
answers are promoted to standing rules so the same question isn't asked every
fortnight. Questions never block: at the cutoff the sheet ships with unanswered
rows flagged.

**This pipeline does not fetch the auction site.** AuctionZip returns 403 to
automated requests; ingestion is a sanctioned bucket drop instead. Staff
export the gallery once per cycle into a bucket, and everything after that is
unattended.

## Architecture

```
Gmail label ──▶ Watcher ──▶ cycle opened (Firestore)
                                  │
   staff drop gallery ──▶ GCS ──▶ Intake ──▶ Pub/Sub (one msg per photo)
                                                │
                                          ┌─────┴─────┐
                                       Appraiser × N (Cloud Run, Gemini 3.5)
                                          └─────┬─────┘
                                                ▼
                                        Comps ──▶ Bidder ──▶ sheet (Firestore)
                                                              │
                                                            Gate ──▶ Gmail draft
                                                              │        ▲
                                                              └── Broker (KMS-signed
                                                                   grants, Secret Manager)
```

Dead-letter topics on every subscription. Per-photo idempotency. Deadline-aware
degradation: at Friday 4PM the sheet ships with whatever is classified, flagged
incomplete, rather than not shipping.

## Stack

Gemini 3.5 via Vertex AI (multimodal + Search grounding) · Google ADK ·
Cloud Run · Pub/Sub · Firestore · Cloud Storage + Eventarc · Cloud Scheduler ·
Secret Manager · Cloud KMS · Cloud Trace

## Deploying for real

See [`infra/deploy.sh`](infra/deploy.sh). You will need: a GCP project with
billing, Vertex AI enabled, and a Gmail OAuth client whose publishing status is
**In production** — verification is not required to publish, and the 100-user
cap on unverified apps is irrelevant for a single operator. The 7-day refresh
token expiry applies only to apps left in *Testing* status.

## Disclosure

All code in this repository was written between August 18 and August 31, 2026.

Pre-existing work: (a) a private repository, `rg-auction-pipeline` — an
earlier working version of this pipeline: roughly 42 KB of Python that
assembled a 452-row bid workbook for a July 2026 auction cycle, plus a
scheduled listing-watch task. No code was copied from it; this repository is a
from-scratch rewrite, decomposed and tested differently. (b) an internal
Anthropic-format skills library including a catalog classification taxonomy —
the taxonomy is reused as configuration, no skill code is included; (c) design
lessons on token brokering from an unrelated project. The bid math and workflow
follow the business's own documented process.

Built solo, in 13 days, by one person.
