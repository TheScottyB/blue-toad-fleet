# Submission claim inventory

This is the source-of-truth boundary for judge-facing copy. A claim may be
published only when its evidence state below is `verified`; mutable cycle and
test figures must come from `media/submission_facts.json`, which in turn accepts
only a sealed, release-eligible artifact manifest.

| Claim | Required evidence | Current state | Allowed copy |
|---|---|---|---|
| Source cycle identity | Manifest plus every source object's SHA-256, staged and materialized by `src/cycles/storage.py` | Implementation verified; no fresh sealed August cycle | “Sanctioned, hash-bound gallery drop.” Do not call the historical fixture current production evidence. |
| Photo/group counts | Release-eligible `submission_facts.json` | Blocked: historical state says 415 while canonical grouping produces 414 | No current count in final media until the cycle is rerun and sealed. Historical prose may say 462 photos / 414 groups only when labeled local fixture. |
| Physical room topology | `spatial_observations.json` bound to exact source manifest, embedding model, and reviewed coverage | Feature path verified; checked-in August fixture has no sidecar | “Walk-order grouping; spatial observations unavailable.” No inferred pole-barn map, surface-signature, or co-visibility result for this cycle. |
| Non-adjacent repeat views | Reviewed reshoot edge, manifest/model hashes, unique photo ownership | Verified in schema-2 reshoot sidecar and tests | “Reviewed similarity edges can merge non-adjacent repeat views.” Counts still come from sealed facts. |
| Container alpha pricing | Visible-content evidence; confirmed alpha requires observed mark and no open mark question | Implementation and focused tests verified; fresh cycle coverage pending | Describe the fail-closed contract. Do not claim a specific cycle’s container uplift without its evidence record. |
| Grounded pricing | Search-backed research with usable citations, followed by no-tools schema extraction; at least two sold comps and bounded disagreement | Implementation and credential-free tests verified; current coverage incomplete | Describe the two-call boundary and refusal rule. Do not describe an ungrounded estimate as a comp. |
| eBay velocity / absorption | Seller Hub capture plus typed import record: sold in trailing 365 days divided by active now; never days-on-market | BT-235 verified: 46 sold / 46 active = 1.0, as of 2026-08-21 | Claim only that exact lot, window, and ratio. Do not transfer it to sports cards, Boston Bottles, or another category. |
| Curator challenge | Typed standing-rule conflict plus fresh, lot-matched evidence; prose trust validator | Contract verified; no eligible current-cycle conflict established | “Challenge is bounded and absent without evidence.” Do not publish the old Topps `<14 day`, `4x`, or `$300+` story. |
| Choice/times-the-money | Object-scoped ruling, typed mechanic, unit count/election, one decision object through allocation and clerk directive | BT-002 path verified in code/tests and cited ruling | $25/unit ×3 = $75 committed max / $86.25 all-in. |
| Budget totals | One decision list; workbook/email/state totals must reconcile; unresolved allocated lots block publish | Historical local fixture computes 9 / $275 / $316.25, but is not release-eligible | Historical only until rerun. Final numbers must be templated from sealed facts. |
| Triage speed and inference cost | Per-call usage telemetry plus stage timers from a fresh full-corpus run | Instrumentation verified; measured corpus run absent | Describe telemetry fields, not “seconds,” “$0.30/cycle,” or “a couple dollars.” Static rate estimates must be labeled estimates. |
| Queue reduction / memory | Before/after cycle evidence with exact rule keys and revisions | Mechanism tested; no sealed multi-cycle performance figure | Describe deterministic keyed memory. No percentage or time-saving claim. |
| July benchmark / receipt comparison | Auditable source rows, unique IDs, current pipeline, correct joins and totals | Quarantined | Never use as submission evidence. The July runner refuses publication. |
| Test results | Machine-generated JUnit/result summary from the release invocation | Produced only by `make release-check` | Do not hand-maintain counts in prose. Final media reads the generated facts. |
| Cloud deployment parity | Ready Cloud Run revision mapped to the tested commit/image digest, plus health probe | Operator hold: not checked or deployed in this remediation | Say only that a public endpoint exists. Do not call it current, flawless, sub-second, or revision-matched. |
| Screenshots and walkthrough | Challenge/landing-page validation, expected marker, staged captures, sealed facts SHA | Capture tooling verified; checked-in screenshots/video are historical | Label old media historical. Re-record only after the release gate passes and operator approves. |
| Final MP4 | Canonical assembler, release-eligible facts, declared input hashes, embedded facts/input digest, media validation | Builder verified; current final is historical | Do not use checked-in MP4 as current evidence. Canonical rebuild must refuse until the cycle is release-eligible. |
| Bid transmission | Explicit operator action outside automated publisher | Not automated and not authorized here | “Drafts; sending remains a human action.” Never say autonomous bidding or sent by the agent. |

## Artifact coverage

The claim boundary applies to `README.md`, `docs/DEVPOST.md`,
`docs/VIDEO_SCRIPT.md`, `docs/blog/index.html`,
`docs/blog/SOCIAL_POST.md`, `NOTES.md`, generated title cards, screenshots, and
the final MP4. `scripts/collect_submission_facts.py` owns mutable figures;
`scripts/assemble_final.py` owns final-media publication.
