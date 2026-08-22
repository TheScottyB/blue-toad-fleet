# TODO — open work, 2026-08-21

**Verified against HEAD `d622862`.** Line numbers move — another lane pushed four
commits during the review that wrote this list, so re-grep before trusting a
citation rather than assuming it still points where it did.

Ranked by consequence. Every item names a file:line and what goes wrong if it
stays. Items marked **[lane: X]** belong to another session — do not take them
without saying so, and see `docs/lane-briefs/` for the boundary.

Submission deadline **Aug 31 2026 5:00pm PDT**. Deploy drop-dead **Aug 27**.

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

## B. Things a judge runs or reads

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

- [ ] **B4. Re-record video Beat 4.** `docs/VIDEO_SCRIPT.md` carries a dated note
      with both figure sets. The recorded cut narrates 12 lots / $335.00 /
      $385.25 / "173 tests"; current is 9 / $275.00 / $316.25 / 474. The script
      was deliberately NOT rewritten — it transcribes a recording.
      **Operator's call.**

## C. Feature floor — build up to the claims, never down

The operator's instruction, verbatim: *"dont lower the floor of the feature set
proposed in this repo, elevate it."* No claim in README.md or docs/DEVPOST.md is
to be softened to match the code. The code comes up to meet it.

- [ ] **C1. Spatial Room Graph** — `README.md:74`. **[lane: grok / intake]**
      Step 0 sees the listing, not the photo. Build on `gemini-embedding-2`
      (recall@25 85.7% vs dHash 0.0%), not dHash. Do NOT add an upscaling stage
      — it fabricated a lens serial the 560px original had read correctly.

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

- [ ] **C4. Velocity — via the operator's own eBay Seller Hub, through the
      browser connection.** `README.md:113`, defined in full in `NOTES.md`
      (commit `dce15ed`), implemented nowhere; `fit_score` stands in for it.

      **The route is settled and is NOT Google-Search grounding.** Operator,
      2026-08-21: *"for the ebay velocity claim, we use the users ebay seller
      account and research through browser connection, this is the second bigger
      remover of friction."* Seller Hub → Research → Product research, driven
      authenticated as `richmondgeneral`. That makes the README's "real-time eBay
      velocity data" claim literally true rather than something to soften.

      **Verified live 2026-08-21** on `Boston Champion pencil sharpener`,
      `tabName=SOLD`. The page yields, as text, with no API:
      - aggregate: **avg sold price $21.58**, range **$6.80–$42.00**, avg
        shipping **$8.79**, free shipping **17%**, **sell-through**, **24 total
        sellers**
      - per sale: title, sold price, shipping, format (Auction / Fixed price),
        bids, and **date last sold**
      - 24 sales dated across **Jul 23 – Aug 21 2026** — a 30-day window, which
        is the velocity signal itself: ~0.8 sales/day on that comp set

      This is strictly better than the grounded-pricing route for velocity: real
      hammer prices from eBay's own database with a date on every one, so
      `velocity = gross margin $ / days on market` is computable rather than
      inferred, and sell-through gives the probability the thing sells at all.

      **Automation gotchas, both observed:**
      - `dayRange=365` in the URL did **not** take on a fresh navigation — the
        page returned a 30-day window regardless. The range must be set through
        the dropdown, or the working param found. Do not trust the URL to have
        applied the range; read the date line the page prints and use that.
      - Working URL shape:
        `ebay.com/sh/research?marketplace=EBAY-US&keywords=<q>&dayRange=<n>&categoryId=0&offset=0&limit=50&tabName=SOLD`
      - It is an authenticated seller account. Read-only research only; never
        touch Listings, Orders, Marketing or Messages from an automated pass.

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
