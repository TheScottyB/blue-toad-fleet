# Cloud cycle execution

## What existed before this path

The gallery cacher wrote `manifest.json` and full-size photographs to a local
`data/...` directory. A person ran `scripts/run_vertex_pipeline.py` from that
machine. Its JSON caches, spreadsheet, and email draft stayed on that disk.
`gcloud run deploy --source .` then copied selected repository data into the
container image, and the Cloud Run service rendered those baked files.

That meant Cloud Run was a viewer over a precomputed cycle. It did not own the
source photographs, start a new cycle, or execute the 450-photo pipeline.
Firestore stored standing rules only.

## Implemented cycle contract

Cloud Storage is now the durable boundary. One cycle occupies:

```text
gs://$BTF_CYCLE_BUCKET/
  shops/<shop>/cycles/<cycle>/
    control/request.json
    input/manifest.json
    input/images/<every full-resolution source image>
    control/READY.json
    control/LAUNCHED.json
    status/status.json
    output/blobs/<sha256>/manifest.json
    output/blobs/<sha256>/triage_results.json
    output/blobs/<sha256>/appraisal_results.json
    output/blobs/<sha256>/decomposition_results.json  # when applicable
    output/blobs/<sha256>/grounded_prices.json
    output/blobs/<sha256>/pipeline_state.json
    output/blobs/<sha256>/bid_sheet.xlsx
    output/blobs/<sha256>/absentee_bid_email.txt
    output/artifact_manifest.json             # sealed last
  shops/<shop>/ACTIVE.json
```

`READY.json` is written only after the manifest and every image named by it are
present. Eventarc delivers Cloud Storage finalization events to
`POST /api/events/storage`; the receiver ignores every object except the exact
READY path. `LAUNCHED.json` is created with a generation precondition, so
Eventarc retries and manual retries cannot start the same cycle twice.

The receiver invokes the configured Cloud Run Job with only the bucket, shop,
and cycle identifiers. The job downloads the immutable input to its ephemeral
disk, rewrites machine-specific `local_path` values to that disk, runs Vertex AI,
grounds candidate prices with three independent citation-preserving sold-comp
samples, uploads the derived files, and writes `ACTIVE.json` only after success. Job
failures remain in `status/status.json`; a failed cycle never becomes active.
Derived objects are content-addressed. Consumers discover them only through the
sealed artifact manifest named by `ACTIVE.json`, so a partial upload cannot look
like a published cycle.

Historic August 22 reference comps and operator overrides are explicitly empty
for new cloud cycles. A new sale cannot inherit a price or decision merely
because it reuses a sequence number such as `BT-001`. Only usable grounded rows
from that cycle cross into `CompEstimate`; their provenance and citations are
carried into the workbook. A refusal remains unpriced. Durable shop-level
standing policies are read from Firestore; cycle-specific lot questions and
historic lot rulings are not copied forward.

## Operator flow

First create the sanctioned local snapshot as today. Then stage it without
spending inference:

```bash
make stage-cycle \
  SOURCE_DIR=data/gallery_12345 \
  CYCLE_ID=2026-09-05 \
  AUCTION_TITLE="September Estate Auction" \
  AUCTION_DATE=2026-09-05 \
  TIMEZONE_NAME=America/Chicago \
  VENUE="200 Example Lane, Genoa City, WI" \
  DEADLINE=2026-09-04T20:00:00-05:00
```

To upload and start in one deliberate action:

```bash
make start-cycle \
  SOURCE_DIR=data/gallery_12345 \
  CYCLE_ID=2026-09-05 \
  AUCTION_TITLE="September Estate Auction" \
  AUCTION_DATE=2026-09-05 \
  TIMEZONE_NAME=America/Chicago \
  VENUE="200 Example Lane, Genoa City, WI" \
  DEADLINE=2026-09-04T20:00:00-05:00
```

Those fields are mandatory cycle identity, not presentation defaults. They may
instead live under `auction` in the source manifest. The uploader refuses to
fall back to the August sale's title, address, or cutoff.

Once a snapshot is staged, the deployed Gate Console also shows **Start staged
auction** when `OPERATOR_TOKEN` is configured. Entering that token and cycle ID
writes READY and reports queued/running/published status in the page. The browser
does not upload hundreds of images; it only starts an already verified snapshot.

If a cycle was staged earlier, write only its READY marker:

```bash
.venv/bin/python scripts/stage_cycle.py \
  --cycle-id 2026-09-05 \
  --listing-id 12345 \
  --ready-only
```

The uploader refuses a missing image, a manifest/listing mismatch, a duplicate
filename, and reuse of an existing cycle ID. It uploads source material only;
local appraisal caches and spreadsheets are never accepted as new-cycle input.

## Deployment

`infra/deploy.sh` now deploys both runtime shapes and provisions their boundary:

- private, regional Cloud Storage bucket with uniform access;
- one user-managed runtime service account;
- interactive Cloud Run service;
- single-task Cloud Run processing job with a two-hour task timeout;
- Eventarc Cloud Storage trigger routed to `/api/events/storage`;
- least-purpose roles for Vertex AI, Firestore, Storage, logging, Eventarc, and
  executing the configured job with per-cycle overrides.

Run it only from an account authorized to create IAM bindings and billable cloud
resources:

```bash
GOOGLE_CLOUD_PROJECT=threebatdrone-prod-420 make deploy
```

The deploy script uses the existing Secret Manager secret named
`operator-token` by default (override its name with `BTF_OPERATOR_SECRET`). It
grants only the runtime service account access and maps its latest version to
`OPERATOR_TOKEN`. If that secret does not exist, cloud event processing still
works, but public browser mutations stay disabled. This avoids placing a
long-lived operator token in the repository, command line, or generated page.

The direct `POST /api/cycles/start` endpoint fails closed on Cloud Run unless
`OPERATOR_TOKEN` is configured. Eventarc does not trust request-supplied cycle
settings: it reads the staged request and READY object back from the private
bucket before attempting a launch.

## Deliberate boundaries

- Processing can start automatically after READY; sending an absentee bid
  cannot.
- Cloud Storage owns source and derived artifacts. Container disk is scratch.
- The processing job may retry, but a published cycle is a no-op on retry.
- Opening the Gate Console does not start a job.
- Google Search grounding and authenticated Seller Hub research remain separate
  evidence sources. Grounded sold-comp pricing runs in the job; authenticated
  Seller Hub absorption is attached only when the operator has recorded it, and
  neither source is fabricated by the cycle trigger.
