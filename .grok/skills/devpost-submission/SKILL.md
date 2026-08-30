---
name: devpost-submission
description: Use when drafting or updating Blue Toad Fleet Devpost copy, hackathon form fields, Additional Info, judged README/DEVPOST claims, submission 1144616, All Things Agentic, additional-info/edit, Google SDK/Cloud checkboxes, or when the user runs /devpost-submission.
---

# Blue Toad Fleet Devpost submission

Paste surface for humans: `docs/DEVPOST.md`. Claim boundary: `docs/SUBMISSION_CLAIMS.md`. Mutable figures: `media/submission_facts.json` only after a sealed, release-eligible snapshot.

**REQUIRED SUB-SKILL:** Use `report-gate` before emitting any judged sentence a stranger could prove wrong.

Devpost URLs (login is the operator's):
- Project details: `https://devpost.com/submit-to/30845-all-things-agentic-hackathon/manage/submissions/1144616-blue-toad-fleet/project_details/edit`
- Additional info: `https://devpost.com/submit-to/30845-all-things-agentic-hackathon/manage/submissions/1144616-blue-toad-fleet/additional-info/edit`

## Authority order

1. Executable tests (`tests/test_sheet_matches_what_was_sent.py`, `tests/test_docs_match_the_sheet.py`, `tests/test_submission_facts.py`).
2. `docs/SUBMISSION_CLAIMS.md` — `verified` only.
3. `media/submission_facts.json` — only if the facts seal is current; otherwise label the figure as the resealed local fixture.
4. `docs/DEVPOST.md` form-field block — the paste home. Update it *after* 1–3, never invent a parallel number.

Do not type test counts, src/ line counts, or Cloud Run SHAs into judged prose. Point at `make release-check` / `docs/evidence/RELEASE.md` / a live `/health` probe dated in the same sentence.

## Live vs this tree

Before any sentence about "the live console":

```bash
curl -sS https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app/health
git rev-parse HEAD
```

If `git_commit` ≠ `HEAD`, the hosted app is a different revision. Say so. Do not attribute un-deployed Friday-desk, walk-return, envelope, audit, or PhotoMember behavior to the URL.

`GET /` on Cloud Run never Vertex-embeds or Google-Searches. Gemma curator voice may run there. Sending a bid is never automated.

## Frozen money (do not paraphrase)

Sent sheet, mailbox-backed: **9 lots / $275.00 / $316.25**, cap **$600**. Test: `tests/test_sheet_matches_what_was_sent.py`.

Full fixture figures must match `get_aug22_state()` / the DEVPOST test (`tests/test_docs_match_the_sheet.py`). Label them provenance-sealed local fixture, not "what was sent."

## Forbidden judged claims

| Do not say | Why |
|---|---|
| Grouping is a funnel / triage drops photos from the sheet | Puzzle loop: every photo is assigned; unmatched → singleton |
| `$1,000` cap | Cap is `$600` |
| `select_challenge` is on the live console | Contract tested, not wired |
| Autonomous send / agent emailed the clerk | Drafts only; human sends |
| Pole-barn topology for Aug-22 | No spatial sidecar |
| Sports-card absorption / Topps `<14 day` | BT-235 only: 46/46 = 1.0 |
| July A/B as evidence | Quarantined |
| `measured $0` Google spend from zero calls | `cost_status` is `no_calls` |
| Hand-maintained pytest counts | Release report owns them |
| E1 fully closed | Live queue can still ask on an allocated lot (check `queue.asked` ∩ allocated) |

Full inventory: `docs/SUBMISSION_CLAIMS.md`.

## Recipe when asked to fill or refresh Devpost

1. Fetch `/health`; compare `git_commit` to `HEAD`.
2. Run `get_aug22_state()` (full + `sheet="sent"`) and read `docs/SUBMISSION_CLAIMS.md`.
3. Update `docs/DEVPOST.md` form-field block and story sections so they match 1–2. Keep the strings `tests/test_docs_match_the_sheet.py` asserts.
4. Run report-gate on the edited copy. Refuted numbers are replaced, not deleted quietly.
5. Run `.venv/bin/python -m pytest tests/test_docs_match_the_sheet.py tests/test_sheet_matches_what_was_sent.py tests/test_submission_facts.py`.
6. If the Devpost page is a login wall, stop and give the operator the paste from `docs/DEVPOST.md`. Do not guess form widgets.
7. Do not deploy, force-push, or send mail from this skill.

## Form field homes

Paste values live in `docs/DEVPOST.md`:
- **Form Fields Quick Reference** — gallery-visible story fields.
- **Additional Info** — the judges-only page (SDK, Cloud services, models, testing instructions, bonus links).

Checkbox rules for that page: `references/additional-info.md`.

Track: **Collaborative Partner** (form wording; gallery may show "The Collaborative Partner"). Submitter: Individuals, United States. Organization name: `Richmond General`. Start date: `08-18-2026`. Hosted URL: `https://blue-toad-fleet-u5gvrqwvua-uc.a.run.app`.

Google models the code calls: `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-2.5-flash` (fallback), `gemma-4-26b-a4b-it-maas`, `gemini-embedding-2`. List those, not a marketing subset. SDK is **google-genai**, never ADK.

## Red flags

- Typing 46/520/598 or 9/275/316.25 from memory instead of the test.
- "Live" attributed without a `/health` SHA.
- Funnel language in the grouping paragraph.
- A second copy of a figure that `media/submission_facts.json` already owns.
- Checking ADK, Cloud SQL, or GKE.
- Checking Startup Excellence without a corporate email.
- Pasting a Facebook *page* URL as the social bonus (needs the post permalink).
- Google models field listing only the three Flash names (omit Gemma 4 / Embedding 2).