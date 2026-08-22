# TODO — open work, 2026-08-21

**Originally verified against `d622862`; re-reviewed against HEAD `8ef89bc` on
2026-08-22.** Line numbers move, and several older status notes below still
describe the earlier tree. Re-grep before trusting a citation and complete B8
before treating this file as the authoritative submission checklist.

Ranked by consequence. Every item names a file:line and what goes wrong if it
stays. Items marked **[lane: X]** belong to another session — do not take them
without saying so, and see `docs/lane-briefs/` for the boundary.

Submission deadline **Aug 31 2026 5:00pm PDT**. Deploy drop-dead **Aug 27**.

Master remediation documents:

- Design: `docs/superpowers/specs/2026-08-22-repository-remediation-design.md`
- Execution plan: `docs/superpowers/plans/2026-08-22-repository-remediation.md`

The design and plan cover every finding below. They do not mark a finding closed;
closure still requires the rebaseline and evidence called for in B8/Task 1.

---

## A. Money-path bugs (bidmath lane — mine)

- [ ] **A1. The negation guard refuses the operator's own phrasing.**
      `src/bidmath/__init__.py:580,616`. `_NEGATION_RE` matches a bare `not`
      anywhere in the string, and the sent email's register is literally
      *"Please do NOT limit me to one unit on this lot."* Verified:
      `mechanic_from_ruling("take all three trays at x3, do not limit me to one
      unit")` → UNKNOWN → `price_lot` refuses → `clerk_directive` says DO NOT
      BID. A correct x3 ruling becomes a lost lot.
      **Fix:** only fire when the negation scopes the mechanic phrase itself
      ("that is NOT a x3 bid"), not anywhere in the sentence.

- [ ] **A2. A speculative remainder would go to the auctioneer as a firm bid.**
      `scripts/run_vertex_pipeline.py:594,602`.
      `remainder_opportunity` sets `speculative=True` and `clerk_directive`
      guards it with "ONLY IF IT COMES BACK UP".
      **Half closed at `d622862`:** the console now renders the directive
      (`src/gate/render.py:286`), so the card is safe. The EMAIL is not — it
      still builds its own line and would print ">> Times the money. I am taking
      ALL 3 <<" for a contingent bid, to the auctioneer.
      **Fix:** route the email through `clerk_directive` too (see A3).

- [ ] **A3. Two implementations of the clerk sentence; two APIs still uncalled.**
      **Partly closed at `d622862`:** `clerk_directive` is now wired into the
      console at `src/gate/render.py:286`. But `scripts/run_vertex_pipeline.py:594,602`
      still hand-builds the same sentence in a different format, so the console
      and the email can now disagree about the same lot — and
      `remainder_opportunity` and `elect` (`src/bidmath/__init__.py`) still have
      no production caller at all, tests only (verified by grep at `d622862`).
      **Fix:** route the email through `clerk_directive` as the console now does,
      and either give the other two a caller or delete them. Do not leave tests
      standing against an API nothing calls.

- [ ] **A4. An implausible count refuses in one path and is dropped in the
      other.** `src/bidmath/__init__.py` `_as_count`. Narrower than first
      reported: with no `units_available`, `"times the money, take all 900"`
      does return UNKNOWN (re-verified at `d622862`). The asymmetry is still
      real — an implausible MULTIPLIER refuses the whole ruling, an implausible
      ELECTION is silently discarded — so with `units_available=5` it becomes
      TIMES_THE_MONEY committing all five on the strength of a number the module
      judged implausible. Low severity; the paths should simply agree.

- [ ] **A5. A speculative remainder consumes real cap headroom.**
      `src/bidmath/__init__.py:484`. `allocate` subtracts `committed_all_in`
      without regard to `speculative`, and `summarize` does not separate
      contingent from committed — so "$327.75 committed of $600" cannot be read
      for how much is hypothetical. Latent until A3 gives it a caller.

- [ ] **A6. An Answer changes the queue, not the sheet.**
      `src/server.py:511-562,321-328`. `/api/answer` persists a rule and calls
      `get_aug22_state()` again, but no standing rule is applied to grouping,
      appraisal, bid mechanic, fit, comps, allocation, or the generated email.
      The response therefore reports `pending_reappraisal: true` while its
      `before.allocated` and `after.allocated` lists come from the same cached
      appraisals and hard-coded `OPERATOR_APPROVED` overrides. This is broader
      than "cached dollars do not recompute": the human answer cannot change any
      decision-bearing field. **Fix:** define a typed answer application seam,
      apply it before `price_lot`/`allocate`, regenerate the email from that
      resulting state, and test one answer that changes committed money.

- [ ] **A7. Lot-specific grouping and scope answers become category-wide
      standing rules.** `src/appraisal/__init__.py:81-84,132-135,251-270`.
      `LOT_GROUPING` and `SCOPE` questions are cluster-scoped for display, but
      `Question.rule_key` discards the cluster/lot id and `learn` promotes both
      kinds as `(kind, category)`. An answer that trays 12/14/16 are an x3 lot can
      therefore suppress an unrelated future jewelry grouping question. Today
      this hides unresolved ambiguity; once A6 applies rules to money it can
      authorize the wrong mechanic. **Fix:** persist object/cluster rulings by
      stable lot or cluster id; reserve category-wide memory for genuinely
      general policy/appetite answers.

## B. Things a judge runs or reads

- [ ] **B0. Remove or rebuild the entire July 11 benchmark before submission.**
      `docs/DEVPOST.md`, `README.md`, `NOTES.md`,
      `scripts/run_july11_benchmark.py`, and
      `data/BlueToad_2026-07-11_Benchmark_Comparison.xlsx` present the artifact as
      a ground-truth A/B comparison, but every headline section has a blocking
      defect:

      * **Legacy total is triple-counted.** The source workbook contains
        `$5,945.00` of item-level max bids, then a `$5,945.00` TOTALS row and a
        `$2,450.00` A-priority subtotal. `run_july11_benchmark.py:127-135` sums
        column I through `max_row`, adding all three to manufacture `$14,340.00`.
        The fallback at `:111` permanently bakes in the same bad total.
      * **The V2 side is synthetic, not the submitted pipeline.** The `$1,910.00`
        result comes from the hard-coded keyword `VALUATION_TAXONOMY`, a uniform
        `condition_penalty=0.10`, adjacency/caption heuristics, and hard-coded
        `$2,205.00`/`$40.00` thresholds — not Gemini appraisal, grounded pricing,
        embeddings, current memory, or the live answer path.
      * **The generated detail rows are misjoined.** `allocate()` reorders
        decisions, then `run_july11_benchmark.py:237` uses
        `zip(lots, decisions)`. Descriptions and comp columns from one lot are
        paired with another lot's id, bid, allocation, and reason. The workbook
        consequently shows unpriced `unsorted` items with sourced max bids.
      * **Lot ids are not unique.** `run_july11_benchmark.py:166` truncates each
        gallery id to six characters. The 357 workbook rows collapse to only
        seven ids; one id is repeated 105 times, so no row can be audited back to
        a unique lot.
      * **The Choice-Lot proof did not run.** The script claims Photos 183-190
        became one `Buyer's Choice` lot capped at one unit, but the grouping
        heuristic creates four two-photo groups and the benchmark never sets
        `BidMechanic.CHOICE`, `unit_count`, or an election. The claimed `$360`
        blowout prevention is prose, not this run's behavior.
      * **"Cuts Friday review to under 2 minutes" is unmeasured.** The benchmark
        derives a count of approval flags but records no review-time measurement.

      **Stage-zero rule:** do not use the workbook or any July comparison figure
      as submission evidence. Prefer removing the comparison and replacing it
      with the tested invariant that deterministic allocation cannot exceed an
      operator-supplied all-in cap. If retained, commit a reproducible legacy
      input; filter true item rows; delete corrupt fallbacks; use stable unique
      ids and an id-based join; run the actual current pipeline; prove the
      Choice-Lot mechanic from state rather than copy; label any synthetic inputs;
      and regenerate every downstream document and workbook.

- [ ] **B1. The `.gitignore` re-inclusion rules do not work.** `.gitignore:12-23`.
      Git will not descend into an excluded directory, so `!path/file.jpg` under
      `data/**/images/` is inert. Verified: `git add` without `-f` is refused.
      The twelve images are tracked only because they were force-added, so a
      delete-and-re-add silently reverts the clean-clone fix and the 22 image
      guards start skipping again.
      **Fix:** exclude `data/**/images/*` (the contents, not the directory) so
      the `!` lines take effect.
      *Note: `git check-ignore` reports these paths as "not ignored" and is the
      wrong instrument — it does not model the tracked-file override. The test
      that measures this is `git rm --cached` then `git add` without `-f`, which
      is still refused at `d622862`.*

- [ ] **B2. The doc-guard fixture errors outside this machine.**
      `tests/test_docs_match_the_sheet.py:45`. `subprocess.run(['.venv/bin/pytest',
      ...])` raises `FileNotFoundError` — not a skip — if the venv is named
      differently or cwd is not the repo root. That is 2 errors in the file whose
      purpose is a green suite for a judge.
      **Fix:** `sys.executable -m pytest`, repo root from `__file__`.

- [ ] **B3. Deploy.** The live Cloud Run revision predates `a3ffe72` — proven by
      the console still serving a banner that commit deleted, and by the live API
      reporting a fourth set of totals. `./infra/deploy.sh` fixes the live
      numbers, removes the banner, and switches Gemma on in production.
      **Outward-facing: operator's call.**

- [ ] **B4-video. Re-record video Beat 4.** `docs/VIDEO_SCRIPT.md` carries a dated note
      with both figure sets. The recorded cut narrates 12 lots / $335.00 /
      $385.25 / "173 tests"; current is 9 / $275.00 / $316.25 / 565 passing (572 collected). The script
      was deliberately NOT rewritten — it transcribes a recording.
      **Operator's call.**

- [ ] **B4-SSIM. Validate the probe's SSIM against a reference fixture.**
      `scripts/probes/rescore_upscaling.py` carries a hand-rolled SSIM (scipy is
      not in `.venv`). Every SSIM figure in `docs/CAPABILITY_PROBE.md` inherits
      any error in it, and none of them has been checked. Cheap: one known
      fixture, or add scipy/skimage to a dev extra and diff.

- [ ] **B5. Repeat the upscaling-appraisal arms to get a fabrication RATE.**
      `src/appraiser/engine.py:201` runs at `temperature=0.1` with no seed, and
      the probe took one sample per arm — enough to prove fabrication *can* reach
      a record undetected, not how often. ~27 appraisal-tier calls in randomized
      order, reporting field-level exact-match. **Spends Vertex quota — operator's
      call.** Does not block the do-not-deploy decision, which rests on a
      zero-tolerance rule, not on a rate.

- [x] **B6. Public browser mutations now fail closed.** Fixed 2026-08-22.
      `src/server.py` returns 503 on Cloud Run when `OPERATOR_TOKEN` is absent and
      401 when it is wrong; the Gate Console sends the operator-entered token for
      both Answer and cycle-start actions, and `tests/test_server.py` covers the
      unauthenticated, wrong-token, and authorized paths. The token is never
      embedded in the generated page. A real identity-backed session/IAP remains
      the preferred post-hackathon replacement for the shared operator token.

- [ ] **B7. Judge-facing copy is stale in more places than README/video.**
      `README.md`, `docs/DEVPOST.md`, `docs/VIDEO_SCRIPT.md`,
      `docs/blog/index.html`, `docs/blog/SOCIAL_POST.md`, `NOTES.md`, and
      `scripts/make_title_cards.mjs` repeat some combination of the unsupported
      physical-room map, surface/co-visibility, real-time eBay velocity,
      autonomous bidding, agent-fleet, and old test/count claims. The README no
      longer says 173 tests, but the recorded video does; even the proposed
      replacement line still says 572 collected instead of the current 671.
      Current code/live state also reports 353 lots and 170 human-pricing
      refusals, while README still says 415 lots, 46 duplicate merges, and 190
      refusals. **Fix:** build one claim/metric inventory across every judged
      artifact, derive mutable counts from one source, and re-record/rebuild the
      media after the copy is final.

- [ ] **B8. Reconcile this TODO against current HEAD before using it as a launch
      checklist.** The file was written against `d622862`; several entries still
      describe that tree. Known examples at `8ef89bc`: B3 says the service is not
      deployed even though `/health` reports the current Python/Firestore build;
      B4-video prescribes 572 tests while 671 collect; C3/E3 use the pre-embedding
      415-lot state and say non-adjacent duplicate protection is absent. Re-check
      every open/closed status and update citations rather than layering new work
      onto obsolete verdicts. The formerly duplicate B4 ids are now uniquely
      named B4-video and B4-SSIM; retain those stable ids.

## C. Feature floor — build up to the claims, never down

The operator's instruction, verbatim: *"dont lower the floor of the feature set
proposed in this repo, elevate it."* No claim in README.md or docs/DEVPOST.md is
to be softened to match the code. The code comes up to meet it.

- [ ] **C1. Spatial Room Graph** — `README.md:74`. **[lane: grok / intake]**
      Step 0 sees the listing, not the photo. Build on `gemini-embedding-2`, not
      dHash: recall@25 85.7% vs 0.0% for dHash, 0.0% for sequence proximity and
      35.7% for a colour-histogram baseline (`docs/CAPABILITY_PROBE.md`). Do NOT
      add an upscaling stage — it fabricated a lens serial the 560px original had
      read correctly, and `appraise_lot` transcribed the fabrication at unchanged
      confidence.

- [ ] **C2. Container Lot Decomposition** — `README.md:81`. **Unowned as of this
      writing; another lane began `src/appraiser/containers.py` mid-review.**
      Settled design: purpose is find-the-alpha and price the lot on it; alpha
      comp + bulk floor; an unconfirmed alpha bids the bulk and names the alpha
      as upside. "Confirmed" = mark present in `marks_observed` with no open
      `mark` question. Note the empirical bound: a hallmark on a bulk tray is not
      legible even at 1200x900, so for that lot class the unconfirmed path is the
      only honest outcome.

- [ ] **C3. Choice-lot detection** — `README.md:109`. The mechanic model exists
      and is inert on real data: all 415 lots are STRAIGHT because only one
      `ruling` string exists. The appraiser already asks the right question —
      21 `lot_grouping` questions across the corpus — so the missing wire is
      queue answers → `StandingRule` → `mechanic`/`unit_count`/`units_wanted`,
      generalised beyond the hand-entered `OPERATOR_APPROVED["ruling"]` field.

- [ ] **C4. eBay velocity = absorption rate, from the operator's own Seller Hub.**
      `README.md:113`. Implemented nowhere; `fit_score` stands in for it.

      **The metric, operator 2026-08-21, verbatim:** *"ebay velocity is sold per
      year / active listing, and thats just the ebay velocity. or absorption
      rate. we dont care about dom for each listing."*

          ebay_velocity = sold_in_last_365_days / active_listings_now

      An absorption rate: how much of the standing supply clears in a year.
      **Days-on-market per listing is explicitly NOT wanted** — do not compute
      it, do not store it, do not reintroduce it as a proxy.

      That maps straight onto the page's two tabs: **SOLD** gives the numerator
      over a 365-day window, **ACTIVE** gives the denominator as it stands now.
      One query, two reads, one ratio.

      **Route:** Seller Hub → Research → Product research, driven authenticated
      as `richmondgeneral` through the browser connection. NOT Google-Search
      grounding. Operator's framing: this is *"the second bigger remover of
      friction"* after the gallery-to-sheet pipeline, and it makes the README's
      "real-time eBay velocity data" claim literally true rather than something
      to soften.

      **Verified live 2026-08-21** on `Boston Champion pencil sharpener`,
      `tabName=SOLD`, read twice with identical results. The page returns as
      plain text, no API: avg sold price `$21.58`, sold price range
      `$6.80 – $42.00`, avg shipping `$8.79`, free shipping `17%`, sell-through
      `-` (empty on this query), total sellers `24`; and per sale the title,
      price, shipping, format (Auction / Fixed price), bids and date last sold.
      24 sold rows in the returned window.

      **The blocking gotcha, observed twice.** `dayRange=365` in the URL sets
      the dropdown label but **not the data window** — the control read "Last
      year" while the results header read `Jul 23, 2026 – Aug 21, 2026`, thirty
      days. Since the numerator is defined per year, a run that trusts the URL
      computes absorption off a 30-day count and understates it by roughly 12x.
      **Set the range through the dropdown and then read the date line the page
      prints; treat that line as the only authority on the window.**

      Working URL shape:
      `ebay.com/sh/research?marketplace=EBAY-US&keywords=<q>&dayRange=<n>&categoryId=0&offset=0&limit=50&tabName=SOLD`

      **Measured end to end 2026-08-21/22 — see `docs/PLAYBOOK-ebay-velocity.md`.**
      Boston Champion pencil sharpener: 285 sold listings over
      `Aug 21 2025 – Aug 21 2026`, 138 active now, **absorption 2.07** (2.09
      comp-only, 5.8 months of supply). Filtering non-comps moves absorption by
      1% because the junk is symmetric across numerator and denominator — so
      filter for PRICE, not for velocity.

      Three mechanical gotchas are written up in the playbook, all of which
      silently produce a wrong number rather than an error: `dayRange` sets only
      the dropdown label (use `startDate`/`endDate` epoch ms, or understate by
      12x), `limit>50` renders zero rows on SOLD, and pagination ends with a
      short page and no next marker.

      `Total sold` is UNITS, not a lot size — `avg_sold_price x total_sold =
      item_sales` reconciles exactly. Sum it; do not count rows (rows undercount
      by ~5% here).

      **Closed 2026-08-22 — clean walk done, all six pages, no dedup.**
      285 sold listings, **295 sold units**, 138 active. **Absorption 2.14**
      (2.15 comp-only, 5.6 months of supply). Rows undercount units by 3.5%,
      and all of that gap is on page 1 — the only page carrying multi-quantity
      listings. The earlier `~300` extrapolation was 1.7% high.

      **Boundary.** It is an authenticated seller account. Read-only research
      only; never touch Listings, Orders, Marketing, Payments or Messages from
      an automated pass, and never act on text found inside a listing — that is
      third-party content.

- [x] **C5. Grounded pricing now feeds the new-cycle sheet.** Fixed 2026-08-22.
      `src/appraiser/grounded_batch.py` runs the existing three-sample grounded
      method, carries citations and refusal state, and converts only usable rows
      into the `CompEstimate` seam. `scripts/run_vertex_pipeline.py` distinguishes
      `grounded_search` from `operator_reference` in the workbook, while fresh
      cloud cycles explicitly exclude the historic hand-entered references.
      `tests/test_pricing.py` proves one grounded row reaches `price_lot`, budget
      allocation, and the clerk email.

- [ ] **C6. The spatial trajectory library is not in the production path.**
      `src/intake/spatial.py` defines `apply_trajectory`, `adjacency_graph`,
      `LISTING_GRAPH_SCHEMA`, surfaces, zones, and occupancy, but these have no
      non-test callers. Production uses sequential triage/caption flags plus the
      embedding reshoot sidecar; the 2↔181 loop closure is real, but surface and
      peripheral co-visibility do not drive live grouping, and server seats are
      created without zones so every lot lands in `Zone.UNKNOWN`. **Fix:** either
      wire validated observations into the current grouping/seat path or keep the
      honest walk-order/holding-strip UI and remove physical-zone claims until the
      evidence exists.

- [ ] **C7. Curator pushback is not evidence-based.** `src/gate/pitch.py` denies
      the curator comps, resale bands, margins, and velocity; `src/gate/voice.py`
      can only phrase allocated lots and standing rules. It cannot challenge a
      SKIP with the eBay absorption or comp evidence claimed in README/video.
      **Fix:** after C4/C5, create a bounded deterministic challenge fact object
      carrying the exact SKIP rule, matched lot, sourced absorption/comp evidence,
      and allowed figures; keep the model limited to phrasing those facts.

- [ ] **C8. "460+ photos in seconds" is unsupported by the implemented triage
      path.** `src/appraiser/engine.py:430-484` accepts `max_workers=4` but loops
      sequentially because each request consumes the previous summary. Appraisal
      uses a pool; triage does not. **Fix:** meter the real end-to-end duration and
      change the claim to the measured result, or redesign grouping/context so
      bounded chunks can run concurrently without losing the adjacency signal.

- [ ] **C9. Cycle cost is estimated, not metered.**
      `src/appraiser/routing.py:16-71` multiplies assumed tokens by copied list
      rates. The `~$0.30` triage claim is plausible as a planning estimate, but no
      live telemetry reconciles request counts, actual input/output tokens,
      retries, model fallback, decomposition, grounding, embeddings, or curator
      calls. **Fix:** capture per-call usage/model/retry data, aggregate by cycle,
      and label the current function explicitly as an estimate until measured.

## D. Undersold — real work in no judged artifact

- [ ] **D1. The Vertex grounding discovery.** `src/appraiser/engine.py:221-235`:
      attaching a `response_schema` to a Google-Search-grounded call returns zero
      `grounding_chunks` — the search runs, the citations vanish, silently.
      Verified live both ways. The two-call design is the response. This appears
      in no README, no DEVPOST, no video.

- [ ] **D2. The BT-002 end-to-end story.** Appraiser sees three labelled trays →
      asks whether that is one lot or three → auctioneer rules "x3 bid" → the
      ruling reaches `committed_max` $75.00 and the clerk line. That is the
      agent loop closing on real money, and it is not in the submission.

- [ ] **D3. Return, not just spend.** The submission states what it committed and
      never what it returns. From the sheet's own comps: $316.25 all-in against
      $713–$879 estimated resale, 2.25x–2.78x. **Derive at submission time from
      one path and state it once** — a hand-typed figure here recreates exactly
      the divergence the judging panel flagged.

## E. Unreviewed / carried

- [ ] **E1. 148 triage questions dropped over cap, never reviewed.** If any of
      those lots deserved a bid, the sheet does not know it.
- [ ] **E2. Comps are partial** — `grounded_prices.json` covers 46 lots of 142.
      BT-002/BT-087 have none, so their maxes derive from `value_magnitude_hint`,
      a model prior, and the sheet does not surface that distinction.
- [ ] **E3. Non-adjacent duplicate guard.** **[lane: grok / intake]** Today's
      sheet is free of double-bids by luck of which lots were approved, not by a
      guard. Long-gap recaptions confirmed at 1↔284, 26↔455, 15↔404, 2↔181.

## F. Scripts audit — artifact safety and reproducibility (2026-08-22)

Reviewed every source file under `scripts/` at HEAD `8ef89bc`. Python compilation
and Node syntax checks pass; the items below are behavioral and evidence-integrity
failures that syntax/tests do not presently catch. The July benchmark defects are
already consolidated in **B0**; live-answer and grounded-price integration are in
**A6/A7/C5**; stale submission claims are in **B7**.

- [ ] **F0. Retire the obsolete Aug-22 runner before it overwrites the
      authoritative money artifacts.** `scripts/run_aug22_cycle.py:34-48,87-99`
      still hard-codes the superseded 12-bid, `$335.00` / `$385.25` schedule,
      including BT-181 even though it is a reshoot merged into BT-002. It writes
      directly over the current nine-bid `data/aug22_absentee_bid_email.txt` and
      `data/BlueToad_2026-08-22_BidSheet.xlsx`; README still calls it the
      production sourcing compiler. **Fix:** delete it, make it a read-only
      historical fixture with non-production filenames, or delegate to one
      canonical pipeline. Add a guard proving no obsolete entry point can write
      the authoritative sheet paths.

- [ ] **F1. A degraded live model run can publish a final sealed sheet.**
      `scripts/run_vertex_pipeline.py:445-459,594-674` and
      `src/appraiser/engine.py:531-564,605-630`. Per-lot appraisal and
      decomposition exceptions become ordinary cached rows with an `error`
      field; the runner announces the batch as retrieved and still overwrites
      the email, workbook, and state snapshot. Triage also falls back silently
      to caption heuristics after a batch failure. **Fix:** validate complete
      coverage, required fields, and zero error rows before publication; record
      degraded mode explicitly; write every output to a staging directory and
      atomically promote the complete artifact set only after all gates pass.

- [ ] **F2. The generic runner still defaults to Aug-22 money and email
      metadata.** `scripts/run_vertex_pipeline.py:338-364,617-637` and
      `src/assemble/email.py:29`. `run_pipeline` accepts a different cycle,
      listing, and data directory, but omitted `reference_comps` and
      `operator_approved` arguments silently select the historic Aug-22 globals.
      Because every sale reuses sequence-derived ids such as `BT-001`, a caller
      can authorize a new sale from another sale's comps, fit decisions, and bid
      caps. The Cloud worker avoids that only because it remembers to pass two
      empty dictionaries. Runs without `output_dir` still select Aug-22 artifact
      filenames, and the supposedly parameterized email still prints a fixed
      `DATE: Friday, August 21, 2026`. **Fix:** make the reusable runner's defaults
      empty and cycle-safe; put historic constants behind an explicit Aug-22
      wrapper; require typed auction/message/cutoff metadata; and derive every
      artifact name from the cycle configuration.

- [ ] **F3. Make one video assembler authoritative.**
      `scripts/build_video.py:40-48` and `scripts/assemble_final.py:23-70` both
      write `media/blue_toad_fleet_demo.mp4` through incompatible paths. The old
      `build_video.py` concatenates video-only segments and can replace the
      narrated final with a silent/obsolete cut. **Fix:** archive or delete the
      legacy builder, give intermediates distinct names, and expose one command
      that verifies audio presence, duration, dimensions, and final size before
      atomically replacing the submission MP4.

- [ ] **F4. Derive video facts instead of freezing them into render scripts.**
      `scripts/build_beat2.py:69-86`, `scripts/make_title_cards.mjs:36-63`, and
      `scripts/generate_architecture_diagram.py:33-72` hard-code mutually stale
      figures and claims: 359 lots, 103 duplicates, 12 bids, 173 tests, 572/565
      tests, Python 3.11, every lot physically mapped, 3D topology, and a 4:00 PM
      review. Current live state is 353 groups, nine bids, 671 collected tests,
      Python 3.14, and every seat is unplaced. This is the script-level source of
      **B7**. **Fix:** feed renderers a versioned evidence snapshot generated by
      the canonical pipeline/test collector; reject missing or mismatched facts
      rather than rendering fallback prose.

- [ ] **F5. Do not overwrite valid screenshot evidence before validating the
      page.** `scripts/cdp_capture.py:116-152` writes the requested output PNG,
      then checks whether Chrome landed on a sign-in/CAPTCHA page. Exit code 2
      reports failure only after a previously valid proof image has already been
      destroyed. Title-only matching can also miss challenge URLs/body text.
      **Fix:** capture to a temporary file; validate final URL, title, expected
      page markers, and absence of challenge markers; atomically rename only on
      success. Close the tab in `finally` and test both valid and challenge pages.

- [ ] **F6. Restore TLS verification on all evidence fetches.**
      `scripts/cache_gallery.py:42-64`, `scripts/recache_full_size.py:36-46`, and
      `scripts/dry_run_single_photo.py:67-77` disable certificate and hostname
      verification. A network intermediary can substitute the manifest or image
      bytes used as appraisal evidence. **Fix:** use the default verified SSL
      context and fail visibly on certificate errors; if a source-specific CA is
      genuinely required, configure that CA explicitly instead of `CERT_NONE`.

- [ ] **F7. Validate and atomically store initial gallery downloads.**
      `scripts/cache_gallery.py:58-87,128-149` writes response bytes directly to
      a `.jpg` path and counts the request as successful without checking HTTP
      content type, decodability, dimensions, or appraisal grade. An HTML/WAF
      response can therefore become a successful cached image, and interruption
      can leave a partial file that future runs skip because it is non-empty.
      **Fix:** download to a temporary path, enforce response/image guards, then
      rename; record hashes and failures in the manifest and return non-zero when
      requested coverage is incomplete.

- [ ] **F8. Preserve grounded-pricing attempt history.** Partially fixed
      2026-08-22: `src/appraiser/grounded_batch.py` now fingerprints the
      decision-bearing identification/category/fit plus a pricing-version key,
      never reuses interrupted attempts, and writes atomically. A successful
      retry currently replaces the transient error row, so attempt history is
      not yet retained separately for audit.

- [ ] **F9. Make forced embedding regeneration transactional.**
      `scripts/embed_gallery.py:80-117`. `--force` discards the existing vector
      map before replacements succeed; a missing image, API failure, or process
      interruption can replace a complete cache with a partial one while the old
      `reshoot_edges.json` remains preferred by readers. **Fix:** build a full
      vector cache and its edge sidecar under temporary names, require manifest
      coverage and uniform dimensions, then swap both files together. Record
      model/input hashes and preserve the last known-good pair on failure.

- [ ] **F10. Require explicit human approval for reshoot edges used on money.**
      `scripts/embed_gallery.py:113-119`, `scripts/list_reshoot_edges.py:1-2`, and
      `scripts/run_vertex_pipeline.py:393-399`. The listing script says to
      eyeball the 63 inferred edges, but the generated sidecar has no reviewed
      state and production consumes it automatically as authoritative merges.
      A false-positive edge can merge two separately sold lots and suppress a
      bid. **Fix:** separate proposed and approved edge files, capture reviewer,
      timestamp and evidence, and make the production path accept only approved
      edges. Add negative real-gallery fixtures, not only synthetic vectors.

- [ ] **F11. Bind Playwright recordings to the video created by that page.**
      `scripts/record_walkthrough.mjs:71-85`, `record_gallery.mjs:36-46`,
      `record_beat2.mjs:21-28`, and `record_terminal.mjs:21-28` scan the shared
      directory and rename the newest anonymous WebM. A leftover or concurrent
      recording can be mistaken for the current run. **Fix:** retain the page's
      `video` handle and use `await video.path()` after context close, or snapshot
      the directory before recording and require exactly one new file. Use an
      isolated temporary recording directory per run.

- [ ] **F12. Stop capture utilities from reporting success on missing output.**
      `scripts/capture_raw_gallery.mjs:5-26` catches and logs errors without
      setting a failing exit code; it also reuses `/tmp/gallery_local.html`
      forever when the file exists, regardless of manifest changes.
      `capture_screenshots.mjs:15-31` skips missing anchors and exits zero.
      **Fix:** rebuild or fingerprint inputs each run, assert HTTP status and
      expected page state, require every requested screenshot, and propagate a
      non-zero exit on any missing/stale artifact.

- [ ] **F13. Make the media pipeline reproducible without undocumented `/tmp`
      state.** `scripts/build_beat2.py:11` requires `/tmp/beat2.json` and
      `build_terminal_replay.py:9` requires `/tmp/term.json`, but the repository
      contains no producer for either file. `assemble_final.py:24-29` also
      assumes prebuilt `beat1_video.mp4` and `beat4_cloud_proof.mp4` with no
      documented builder. **Fix:** add deterministic producers and a single
      orchestration command/manifest that declares every input and output; use a
      run-specific temporary directory rather than global filenames.

- [ ] **F14. Probe media durations instead of hard-coding them.**
      `scripts/assemble_final.py:23-29,42-48` claims each target duration is the
      MP3's own length but stores four literal durations. Regenerated narration
      can be truncated or padded against the wrong video without a failed build.
      **Fix:** read durations with ffprobe at build time, validate expected beat
      boundaries, and fail when video coverage is shorter than narration beyond
      the permitted final-frame pad.

- [ ] **F15. Fix the live Vertex gate's image contract.**
      `scripts/test_vertex_live.py:48-64` reads a WebP cached under a `.jpg` name
      but declares it as `image/jpeg`; if neither fixture exists it performs a
      text-only call and can still announce that the multimodal live gate passed.
      It also accepts success from the legacy fallback model after current-tier
      failures. **Fix:** detect MIME from bytes, require an appraisal-grade image,
      assert the exact required model independently, and clearly separate
      fallback diagnostics from a release-gate pass.

- [ ] **F16. Decode and escape gallery text at the ingestion/render boundary.**
      `scripts/cache_gallery.py:38-40,105-125`,
      `scripts/build_local_gallery.py:14-20`, and `scripts/build_beat2.py:18-25`.
      Captions retain HTML entities (`M&amp;Ms`, `&quot;golden&quot;`) and local
      renderers interpolate third-party caption/path strings directly into HTML.
      This already produces `M&amp;amp;Ms` in the live console and allows markup
      injection in file-backed capture pages. **Fix:** HTML-decode once during
      manifest ingestion, escape every value during HTML generation, and add
      fixtures for ampersands, quotes, tags, and malformed captions.

- [ ] **F17. Make the capability probes reproducible from committed inputs.**
      `scripts/probes/task3_baselines.py:17-21,58-69` requires an uncommitted
      `embeddings.npz` even though the repository carries `embeddings.json`;
      `rescore_upscaling.py:19-23,108-130` requires uncommitted truth/model
      artifacts. A clean clone cannot reproduce the numbers claimed in
      `docs/CAPABILITY_PROBE.md`. **Fix:** consume the committed embedding cache,
      publish hashes plus a documented fetch recipe for redistributable truth
      images, preserve model-generation metadata, and have the report generated
      from machine-readable results. Keep the existing SSIM validation work in
      **B4-SSIM**.

- [ ] **F18. Add script-level tests for destructive and evidence-producing
      entry points.** Current guards validate canonical bid constants and the
      already-generated sheet, but they do not run `run_aug22_cycle.py`, detect
      the July workbook's seven-ID collision, protect final-video ownership,
      exercise challenge-page capture, or simulate interrupted caches. **Fix:**
      test scripts against temporary directories with injected output roots;
      assert unique ids, no publication on partial failure, atomic preservation
      of last-known-good artifacts, correct exit codes, and exactly one owner for
      each authoritative filename.

- [ ] **F19. Do not publish a manifest whose image paths die with the Cloud Run
      job.** `src/cycles/storage.py:319-339`,
      `scripts/run_vertex_pipeline.py:711-715`, and `src/cycles/worker.py:34-39`.
      Materialization rewrites every manifest `local_path` to the job's temporary
      directory, then the runner copies that runtime manifest into `output/`.
      The worker uploads it and immediately deletes the temporary directory, so
      every published image path is invalid even though `ACTIVE.json` advertises
      a successful durable cycle. **Fix:** retain a storage-relative source
      identifier separately from the runtime path and build the output manifest
      from durable object references. Add an integration test that closes the
      temporary directory and can still resolve every published photo.

- [ ] **F20. Remove Aug-22 lot questions from the generic cycle path.**
      `scripts/run_vertex_pipeline.py:492-520`. Every run constructs questions
      about BT-006, BT-010, BT-073, BT-083, and other historic lots, including a
      fresh cloud cycle whose comps and approvals were deliberately cleared.
      The returned queue can therefore claim that standing rules answered
      questions about lots that do not exist in the sale. **Fix:** inject
      cycle-specific questions through configuration, default generic cycles to
      none, and let the explicit Aug-22 wrapper supply the historic question set.
      Test that a new cycle's queue contains only its own lot ids.

- [ ] **F21. Split the 380-line runner into typed, testable pipeline stages.**
      `scripts/run_vertex_pipeline.py:338-717`. One function currently owns input
      validation, live model calls, cache policy, grouping, pricing, allocation,
      console output, email rendering, workbook rendering, JSON publication, and
      the seven-value return tuple. Its public dictionaries have no record types,
      reusable code calls `sys.exit`, and snapshot serialization reaches into
      `__dict__`. Ruff also reports 15 issues in this file, including eight unused
      imports and two blind `Exception` catches. **Fix:** introduce frozen
      `PipelineConfig` and `PipelineResult` dataclasses with `Path` and typed
      mapping fields; extract intake, appraisal, pricing, and artifact-writing
      stages; use exceptions in the reusable core and a small `argparse`
      `main(argv) -> int` at the boundary; then enable Ruff in CI and remove the
      repository `sys.path` mutation.
