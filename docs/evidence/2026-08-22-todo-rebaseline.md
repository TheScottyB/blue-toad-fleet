# TODO rebaseline evidence — 2026-08-22

This ledger rechecked all 54 stable audit ids against the current working tree.
`closed-with-evidence` means a focused automated check exists;
`intentionally-deferred` names an operator/external hold; `superseded` means the
unsafe premise is no longer allowed by the publication contract. Historical
line numbers in the original finding are not treated as current evidence.

| ID | Disposition | Current evidence / reproduction |
|---|---|---|
| A1 | closed-with-evidence | `tests/test_ruling_to_mechanic.py` covers scoped negation and the operator’s “do not limit me” x3 phrasing. |
| A2 | closed-with-evidence | `src/assemble/email.py` renders `clerk_directive`; speculative remainders retain the conditional instruction in email tests. |
| A3 | closed-with-evidence | Console and email share `clerk_directive`; `elect` and `remainder_opportunity` have application callers and regression coverage. |
| A4 | closed-with-evidence | Bid-mechanic parser tests reject implausible multiplier and election counts consistently. |
| A5 | closed-with-evidence | `SheetSummary` and allocator separate contingent remainder exposure from committed exposure; bidmath tests reconcile both. |
| A6 | closed-with-evidence | `/api/answer` persists a revisioned lot ruling; server tests show the answer changes mechanic and committed money. |
| A7 | closed-with-evidence | `LotRulingRecord` is lot-scoped while `StandingRuleRecord` remains category policy; memory tests cover isolation. |
| B0 | closed-with-evidence | `scripts/run_july11_benchmark.py` refuses publication; `tests/test_july_benchmark_quarantine.py` reproduces bad totals/ids/joins and scans judged copy. |
| B1 | closed-with-evidence | `.gitignore` ignores image contents rather than the directory; `tests/test_clean_clone_contract.py` proves ordinary re-add without force. |
| B2 | closed-with-evidence | The doc guard derives repository root from `__file__` and uses `sys.executable`; clean-clone test collects it from another cwd. |
| B3 | intentionally-deferred | Deployment is outward-facing. `docs/evidence/RELEASE.md` must first say ready; no deploy was authorized in this run. |
| B4-video | intentionally-deferred | Canonical media assembly refuses a non-release-eligible facts snapshot. Re-record/review is an explicit operator hold. |
| B4-SSIM | closed-with-evidence | `artifacts/signature_upscale_probe/ssim_reference_fixture.json` and `tests/test_capability_probes.py` validate identity and a known Wang-formula constant-field case. |
| B5 | intentionally-deferred | The randomized repeated arm spends roughly 27 paid appraisal calls. The single-run safety conclusion remains valid; no rate is claimed. |
| B6 | closed-with-evidence | Server mutation routes require the operator token in production and use expected revisions; server/auth tests cover missing, wrong, valid, and conflict cases. |
| B7 | closed-with-evidence | `docs/SUBMISSION_CLAIMS.md` inventories every judged surface; README, Devpost, video script, blog, social copy, notes, and capture anchors use the evidence boundary. Historical media is labeled. |
| B8 | closed-with-evidence | `docs/TODO.md` has one current verdict per id; `tests/test_todo_inventory.py` enforces exact inventory/status/checkbox agreement. |
| C1 | closed-with-evidence | Spatial observations require exact manifest/model/full coverage at staging and loading; production calls `apply_trajectory`; absent evidence renders walk-order only. See cycle/spatial tests. |
| C2 | closed-with-evidence | Two-pass locate/crop/itemize is in `src/appraiser/engine.py`; `comp_from_reference` uses cited bulk floor and adds alpha only with an observed mark and no mark question. See container tests. |
| C3 | closed-with-evidence | Object-scoped grouping answers flow through `mechanic_from_ruling`, optional `elect`, `price_lot`, allocation, and the clerk directive. |
| C4 | closed-with-evidence | `scripts/import_ebay_absorption.py` imports Seller Hub sidecars without DOM; committed BT-235 capture verifies 46 sold units / 46 active = 1.0. |
| C5 | closed-with-evidence | `GroundedPricingPipeline` converts only usable cited rows into `CompEstimate`; pricing tests carry one through allocation/email. |
| C6 | closed-with-evidence | `scripts/run_vertex_pipeline.py` loads `spatial_observations.json` and calls `apply_trajectory`; current Aug input lacks the sidecar and honestly stays walk-only. |
| C7 | closed-with-evidence | `src/gate/challenge.py` selects only fresh, matching typed evidence and rejects invented lots, numbers, margins, velocities, or buy/bid prose. |
| C8 | intentionally-deferred | Stage timers and per-call telemetry are implemented, but no fresh full-corpus live run has measured the headline. Judge-facing speed claims were removed. |
| C9 | closed-with-evidence | `UsageTelemetry` captures model/stage, tokens, latency, retry, fallback, error, rate snapshot, and measured cost; planning estimates remain separately labeled. |
| D1 | closed-with-evidence | README, Devpost, and schema-2 submission facts describe the grounded-search/citation then no-tools extraction boundary; pricing tests enforce it. |
| D2 | closed-with-evidence | README, Devpost, video script, and submission facts derive the BT-002 $25 ×3 → $75 / $86.25 path; ruling tests prove it. |
| D3 | closed-with-evidence | `_decision_facts` derives resale totals and multiples from exact allocated decision comp provenance; it refuses missing/duplicate provenance. |
| E1 | intentionally-deferred | The historical queue remains unresolved. Queue accounting exposes every disposition, and publication refuses any unresolved allocated lot; operator review/fresh cycle is still required. |
| E2 | superseded | Partial coverage no longer permits model-prior money: no usable comp means human pricing, and `_require_publishable_output` rejects allocated lots without accepted provenance. |
| E3 | closed-with-evidence | Schema-2 reviewed reshoot edges contain reviewer/revision/model/manifest identity; production rejects proposed/stale/unreviewed edges. |
| F0 | closed-with-evidence | `run_aug22_cycle.py` is a refusing migration stub; artifact ownership tests prevent it from writing protected outputs. |
| F1 | closed-with-evidence | Worker publication checks complete requested/successful coverage, zero errors, mechanics, provenance, queue, money, and required artifacts before sealing/activating. Failure tests preserve ACTIVE. |
| F2 | closed-with-evidence | `PipelineConfig` requires auction metadata; generic references/approvals default empty; worker passes explicit fresh-cycle values. |
| F3 | closed-with-evidence | `scripts/assemble_final.py` is the only final MP4 owner; `scripts/build_media.py` orchestrates it and ownership tests reject alternatives. |
| F4 | closed-with-evidence | `scripts/build_submission_facts.py` produces schema 2 from hashed source inputs; cards/pages/narration consume it and reject stale or ineligible facts. |
| F5 | closed-with-evidence | `scripts/cdp_capture.py` validates landing HTML and staged PNG before atomic publication, closes tabs in `finally`, and preserves last-good output on challenge pages. |
| F6 | closed-with-evidence | Gallery/full-size/dry-run fetchers use default verified TLS; source-integrity tests prohibit disabled verification. |
| F7 | closed-with-evidence | Downloads validate status, byte MIME, decoding, dimensions, hash, and completeness before rename; failures return nonzero. |
| F8 | closed-with-evidence | Grounded pricing writes current cache plus append-preserving attempt history and rejects interrupted cache reuse. |
| F9 | closed-with-evidence | Forced embedding builds a complete temporary cache and reviewed-edge companion before replacement; interruption tests preserve the previous pair. |
| F10 | closed-with-evidence | Money grouping accepts only reviewed schema-2 edges bound to exact manifest/model; reviewer/revision are required. |
| F11 | closed-with-evidence | Recording scripts use isolated per-run directories and the page-owned video path; concurrent/leftover files cannot win by mtime. |
| F12 | closed-with-evidence | Screenshot/raw-gallery capture requires every marker and valid PNG, stages the full set, and propagates nonzero failure. |
| F13 | closed-with-evidence | Video inputs and producers are declared in `media/video_manifest.json`; `/tmp` JSON dependencies were removed. |
| F14 | closed-with-evidence | Video assembly probes actual stream durations and applies manifest-bounded padding; media tests cover mismatch/refusal. |
| F15 | closed-with-evidence | Live probe and source helpers require appraisal-grade decodable image bytes and fail on HTML/WAF/thumbnail fallbacks. |
| F16 | closed-with-evidence | Manifest ingestion decodes entities once; local pages and Gate escape untrusted values. Source and capture tests cover markup/entity cases. |
| F17 | closed-with-evidence | Baseline probe consumes committed `embeddings.json`; SSIM uses a committed reference fixture; reports include input/model hashes and fail with a recovery recipe if redistributable images are absent. |
| F18 | closed-with-evidence | Artifact ownership, source interruption, capture challenge, cycle publication, July quarantine, clean clone, and release-gate tests exercise destructive/evidence entry points in temporary roots. |
| F19 | closed-with-evidence | Published source manifests retain storage-relative paths plus durable `source_object`; worker-temp teardown tests resolve every source afterward. |
| F20 | closed-with-evidence | Generic `PipelineConfig.cycle_questions` defaults empty; explicit August wrapper supplies history; foreign lot ids are rejected. |
| F21 | closed-with-evidence | Frozen intake/appraisal/decision results and separate email/workbook/state writers are called by the typed orchestrator; unsafe serialization/path mutation are gone; Ruff is declared and runs in `make release-check`. |

## Remaining holds

The safe local implementation is blocked from release by five explicit holds:

1. resolve or deliberately decline historical unresolved queue items in a fresh
   canonical cycle (E1);
2. run a measured full-corpus live cycle if a speed claim is desired (C8);
3. optionally authorize the paid repeated fabrication-rate probe (B5);
4. once release facts seal, authorize fresh screenshots/video and review them
   (B4-video);
5. only after the local report is ready, authorize deployment and live parity
   verification (B3).

No ordinary local finding remains open; the remaining items are the explicit
operator/external holds above.
