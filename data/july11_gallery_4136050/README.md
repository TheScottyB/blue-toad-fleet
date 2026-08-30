# July 11, 2026 gallery drop — frozen A/B input

AuctionZip listing **4136050**, Blue Toad Auctions, Saturday July 11, 2026.
This directory is the hash-bound input for a later same-photos comparison.
It is not submission evidence.

## What is frozen here

| Artifact | Role |
|---|---|
| `manifest.json` | 452 photos, 324 captioned. Captions were parsed from the photopanel when the listing was live. |
| `images/` | Appraisal-grade `_fl` variants (560×420 WebP, tracked — AuctionZip HTML is already 403). `sha256` / size on each manifest row. |
| `BlueToad_2026-07-11_BidSheet.xlsx` | **Side A — ad-hoc desktop run.** 88-lot bid sheet plus a 452-row training tab, produced with desktop SOP + openpyxl builders (not this repo's pipeline). |

`data/BlueToad_2026-07-11_Benchmark_Comparison.xlsx` is the **quarantined synthetic scorecard**. It is not Side A and it is not Side B. Do not quote its figures.

## The A/B this drop exists to run

- **A.** The BidSheet above: Friday prep with ad-hoc desktop apps on these 452 photos.
- **B.** A new workbook from the **current** Blue Toad Fleet pipeline on the **same** cached images, joined by photo sequence / stable lot id.

Do not regenerate B by re-running `scripts/run_july11_benchmark.py`. That entry point still refuses: its old comparison triple-counted totals, truncated ids, and misjoined rows. Side B is a current-pipeline run against this drop, written to a new filename, after grouping / appraisal / grounded pricing / allocate.

Until that workbook exists, there is no July A/B to publish.

## Provenance

See `provenance.json`. The BidSheet sha256 is pinned there and in `tests/test_july11_drop.py`.
