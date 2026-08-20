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
| Vertex client, Cloud Run deploy, Pub/Sub, Firestore | **Planned** |
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

Richmond General, a resale shop in Richmond, Illinois, buys inventory from Blue
Toad Auctions — a Wisconsin auction house a couple of miles over the state
line, close enough to walk, far enough to be in another state. The July 2026
cycle, from the shop's own prep:

- **428 gallery photos** reviewed by hand
- **88 lots** worked up on the full bid sheet — 24 A-priority, max bids
  summing to **~$5,945**
- trimmed to a plan of **~61 candidates / 17 absentee bids / ~$1,820 max
  (~$2,205 all-in)**
- Hard cutoff: **Friday 8:00 PM**
- Bid rule: **max ≈ 35–40% of low-mid resale**, all-in = bid × 1.15 absentee
  fee × tax. Walworth County is 5.5%, but the shop has a resale exemption on
  file with the auction house, so its own all-in is the fee alone.

The prep was finished. **The absentee submission never ran.** No bid, absentee,
or confirmation email exists in the shop's mailbox for that window — searched
2026-08-19, proven live against controls. The shop has exactly one operator, the
sale ran Saturday morning, and the store had to stay open. That last mile — one
person who cannot be in two places, and an absentee channel that has never once
been used — is the friction this fleet removes.

Four lots from that sale did reach inventory, by some route other than an
absentee bid. How — in person, by phone, after the sale — is not recorded
anywhere this repository can verify, so it is not claimed here. What is recorded
is the receipt (`ops/receipts/2026-07-11-blue-toad-auctions.jpeg`, in the shop's
private inventory repo) and four items naming that sale as their source:

| Lot | Item | Paid |
|---|---|---|
| 203 | Tobacco sign | $10.00 |
| 208 | Uncle Sam picture | $5.00 |
| 55 | Railroad spikes | $30.00 |
| 326 | Hanging lamp, stained glass | $10.00 |

That is worth stating plainly because the July bid sheet carried predictions for
three of those four lots. It is a small sample and it is not a benchmark, but it
is real prediction against real hammer prices on real money — the only such
evidence this project has, and it exists because the cycle was prepped even
though the bids were never sent.

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
