# Blue Toad Fleet

An agent fleet that turns a rural Illinois resale shop's biweekly auction sourcing —
hundreds of gallery photos, a Friday 8PM absentee deadline, real money — into a
triaged, priced, budget-allocated bid sheet and a ready-to-send prebid email.
Unattended from ingest to draft.

Built for the All Things Agentic Hackathon, August 2026.

---

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
make test    # 25 unit tests over the bid math
```

## The problem

Richmond General, a resale shop in Richmond, Illinois, buys inventory from Blue
Toad Auctions — a Wisconsin auction house a few miles over the state line — every
two weeks. Per cycle, from the shop's own tracker:

- **~428 gallery photos** to review
- **~61 candidate lots** shortlisted
- **~17 absentee bids** placed
- **~$1,820 max / ~$2,205 all-in** committed
- Hard cutoff: **Friday 8:00 PM**
- Bid rule: **max ≈ 35–40% of low-mid resale**, all-in = bid × 1.15 absentee
  fee × tax

All of it done by hand, on a deadline someone else sets.

## What the fleet does

| Component | Job |
|---|---|
| **Watcher** | Cloud Scheduler job polling a Gmail label for the auction announcement. Opens a cycle, pings Slack, schedules the Friday nag. |
| **Intake** | Eventarc on a GCS bucket. Staff drop the gallery export; Intake fans out one Pub/Sub message per photo. |
| **Appraiser** | ADK + Gemini 3.5 multimodal. Identification, category, condition, fit score. Idempotent on `(cycle, photo)`. |
| **Comps** | Own sales history + eBay Browse + Gemini with Google Search grounding. Emits range, confidence, source count, and a `no external comp` flag. |
| **Bidder** | The bid math in [`src/bidmath`](src/bidmath/__init__.py). Priority, pricing, greedy allocation against a budget cap. |
| **Gate** | Review, trim, approve → Gmail draft. Lots at or under a configured all-in threshold send without a human. |
| **Broker** | Credential proxy. Agents hold no tokens. See [docs/BROKER.md](docs/BROKER.md). |

## Two design decisions worth explaining

**Pricing is advisory; triage is the product.** Sorting hundreds of photos into
categorised candidates with condition notes is what a multimodal model is
genuinely good at. Defending a dollar figure for a piece of breweriana from a
photograph is what it is worst at — and the shop owner knows the market better
than the model does. So lots without an external comp are **not priced**. They
are surfaced with `no external comp — human pricing required`. Refusing to
guess is a feature.

**Nothing scrapes the auction site.** AuctionZip returns 403 to automated
requests, and this repo contains no scraper of anyone. Ingestion is a
sanctioned boundary: staff export the gallery once per cycle into a bucket, and
everything after that is unattended.

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
billing, Vertex AI enabled, and a Gmail OAuth client. **Note:** an OAuth app
left in *Testing* publishing status issues refresh tokens that expire every 7
days. For anything beyond a demo, install as an *Internal* app inside a Google
Workspace organisation.

## Disclosure

All code in this repository was written between August 18 and August 31, 2026.

Pre-existing work: (a) a private repository containing early notes and planning
for this pipeline — no code was copied from it; (b) an internal
Anthropic-format skills library including a catalog classification taxonomy —
the taxonomy is reused as configuration, no skill code is included; (c) design
lessons on token brokering from an unrelated project. The bid math and workflow
follow the business's own documented process.

Built solo, in 13 days, by one person.
