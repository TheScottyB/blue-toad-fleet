# Submission claim inventory

This is the source-of-truth boundary for judge-facing copy. A claim may be
published only when its evidence state below is `verified`; mutable cycle and
test figures must come from `media/submission_facts.json`, which in turn accepts
only a sealed, release-eligible artifact manifest.

| Claim | Required evidence | Current state | Allowed copy |
|---|---|---|---|
| Source cycle identity | Manifest plus every source object's SHA-256, staged and materialized by `src/cycles/storage.py` | Implementation verified; no fresh sealed August cycle | “Sanctioned, hash-bound gallery drop.” Do not call the historical fixture current production evidence. |
| Photo/group counts | Release-eligible `submission_facts.json` | Facts seal passes (2026-08-29 snapshot): canonical grouping reproduces the resealed 462 photos / 415 groups; release eligibility still blocked by the open-question hold | Prose may say 462 photos / 415 groups labeled as the resealed local fixture. Final media reads the sealed facts. |
| Physical room topology | `spatial_observations.json` bound to exact source manifest, embedding model, and reviewed coverage | Feature path verified; checked-in August fixture has no sidecar | “Walk-order grouping; spatial observations unavailable.” No inferred pole-barn map, surface-signature, or co-visibility result for this cycle. |
| Non-adjacent repeat views | Reviewed reshoot edge, manifest/model hashes, unique photo ownership | Verified in schema-2 reshoot sidecar and tests | “Reviewed similarity edges can merge non-adjacent repeat views.” Counts still come from sealed facts. |
| Container alpha pricing | Visible-content evidence; confirmed alpha requires observed mark and no open mark question | Implementation and focused tests verified; fresh cycle coverage pending | Describe the fail-closed contract. Do not claim a specific cycle’s container uplift without its evidence record. |
| Grounded pricing | Search-backed research with usable citations, followed by no-tools schema extraction; at least two sold comps and bounded disagreement | Implementation and credential-free tests verified; current coverage incomplete | Describe the two-call boundary and refusal rule. Do not describe an ungrounded estimate as a comp. |
| eBay velocity / absorption | Seller Hub capture plus typed import record: sold in trailing 365 days divided by active now; never days-on-market | BT-235 verified: 46 sold / 46 active = 1.0, captured 2026-08-22 01:03 CDT | Claim only that exact lot, window, and ratio. Do not transfer it to sports cards, Boston Bottles, or another category. |
| Curator challenge | Typed standing-rule conflict plus fresh, lot-matched evidence; prose trust validator | Contract verified; no eligible current-cycle conflict established | “Challenge is bounded and absent without evidence.” Do not publish the old Topps `<14 day`, `4x`, or `$300+` story. |
| Choice/times-the-money | Object-scoped ruling, typed mechanic, unit count/election, one decision object through allocation and clerk directive | BT-002 path verified in code/tests and cited ruling | $25/unit ×3 = $75 committed max / $86.25 all-in. |
| Budget totals | One decision list; workbook/email/state totals must reconcile; unresolved allocated lots block publish | Resealed 2026-08-29 fixture computes 46 / $520.00 / $598.00 with the sent nine seated first; the sent sheet itself remains 9 / $275.00 / $316.25; not yet release-eligible (open-question hold) | Both figure sets may appear when labeled — the sent nine with mailbox receipts, the sealed 46 as the resealed fixture. Final numbers must be templated from sealed facts. |
| Triage speed and inference cost | Per-call usage telemetry plus stage timers from a fresh full-corpus run | Instrumentation verified; measured corpus run absent | Describe telemetry fields, not “seconds,” “$0.30/cycle,” or “a couple dollars.” Static rate estimates must be labeled estimates. |
| Queue reduction / memory | Before/after cycle evidence with exact rule keys and revisions | Mechanism tested; no sealed multi-cycle performance figure | Describe deterministic keyed memory. No percentage or time-saving claim. |
| July benchmark / receipt comparison | Auditable source rows, unique IDs, current pipeline, correct joins and totals | Quarantined | Never use as submission evidence. The July runner refuses publication. |
| Test results | Machine-generated JUnit/result summary from the release invocation | Produced only by `make release-check` | Do not hand-maintain counts in prose. Final media reads the generated facts. |
| Cloud deployment parity | Ready Cloud Run revision mapped to the tested commit/image digest, plus health probe | Parity MATCH verified 2026-08-29: `/health` `git_commit` equals the audited deploy commit (see `docs/evidence/2026-08-29-parity-match-a1f41ae.md`) | May say the deployed revision matches the audited commit, citing the dated parity record. Do not call it flawless or sub-second; parity is a point-in-time claim — date it. |
| Screenshots and walkthrough | Challenge/landing-page validation, expected marker, staged captures, sealed facts SHA | Capture tooling verified; fresh beat recordings staged 2026-08-29 on operator instruction against the parity-matched revision; checked-in screenshots/final video remain historical | Label old media historical. Canonical assembly still refuses until the release gate passes. |
| Final MP4 | Canonical assembler, release-eligible facts, declared input hashes, embedded facts/input digest, media validation | Built 2026-08-29 by the canonical assembler from release-eligible facts (sealed artifact manifest `333ea63`); 236.1s, facts/input digest embedded, `make video-verify` passes | The checked-in MP4 is current submission evidence while `make video-verify` passes against it. |
| Bid transmission | Explicit operator action outside automated publisher | Not automated and not authorized here | “Drafts; sending remains a human action.” Never say autonomous bidding or sent by the agent. |

## Artifact coverage

The claim boundary applies to `README.md`, `docs/DEVPOST.md`,
`docs/VIDEO_SCRIPT.md`, `docs/blog/index.html`,
`docs/blog/SOCIAL_POST.md`, `NOTES.md`, generated title cards, screenshots, and
the final MP4. `scripts/collect_submission_facts.py` owns mutable figures;
`scripts/assemble_final.py` owns final-media publication.
