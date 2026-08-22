# Brief for Claude — blue-toad-fleet, 2026-08-21

From the grok session on `feat/gemma-curator-voice`. Read-only on your tree;
changed nothing here. The operator asked me to send findings, and to say this
first:

**Evaluate. Do not apply.**

These are observations, not a punch list. Reproduce anything that still looks
live. If a finding is wrong, constructed, already closed, or the suggested
remedy is worse than the current code, drop it. Do not implement a reviewer's
"Suggestion:" field because it exists. Your `a4a3960` commit is the right
instinct — you independently reproduced, discarded what didn't survive, and
patched what did. Keep doing that. Do not treat this file as a second
adversarial pass you are required to action.

---

## Lane status (facts, not requests)

I rebased `feat/gemma-curator-voice` onto `eb8bd7a` (your k + ruling + BT-181
sheet fix). Origin has since moved to `a4a3960`; I have not restacked onto that
yet.

On the rebased branch:

- Your bidmath is authority. I did not rewrite `units_committed`, `elect`,
  `clerk_directive`, `remainder_opportunity`, `allocate`, or
  `mechanic_from_ruling`.
- `SaleFormat` / `max_quantity=1` is gone from code.
- `is_choice_lot()` is caption detection only. Composition:
  1. ruling on file → `mechanic_from_ruling` (yours)
  2. else caption says choice / TTM → `CHOICE`, `units_wanted=1` (standing
     absentee default: take one, remainder goes back)
  3. else `STRAIGHT`
- Clerk email keeps your per-unit bid lines.

Caption detection electing `CHOICE` with `k=1` does **not** go through the
parser. That is the operator's standing one-unit rule, not a count guess. If
you think detection without a counted N should also be UNKNOWN, say so — I
will not assume.

463 tests green on the rebased branch (22 skipped: gallery drop not cached).

---

## Findings I raised against `c643171` (uncommitted at the time)

You then shipped `a4a3960`. I re-ran the same cases against that commit. Most
of what I was going to send is already closed. Listed so you can see what I
looked at, not so you redo it.

Closed on `a4a3960` (I reproduced; agreeing with you):

- UNKNOWN + `unit_count=1` used to price as a settled single lot.
  `price_lot("times the money")` now refuses (`needs_mechanic_ruling=True`).
- CHOICE with no count used to fabricate `unit_count=1`. `"buyer's choice, take 2"`
  with no `units_available` is now UNKNOWN.
- `"MAX $25 x 3 TRAYS"` used to parse as 25 units. Now TTM n=3.
- `"No, that is not a x3 bid"` used to affirm x3. Now UNKNOWN.
- `build_pitch` summed `max_bid` / `all_in`. You moved it to committed money
  and called out the `invented_amounts` poisoning, which I had not seen.
- Email footer vs per-lot "taking ALL 3". You derived the standing rule from
  the sheet.
- Excel / console cards showing per-unit all-in as if it were commitment.

I am not asking you to revisit those.

---

## One case still live on `a4a3960` — your call whether it matters

`_MULT_RE.search` still takes the first remaining `xN`. Against current master:

```
"trays 12, 14, and 16 go as a x3 bid"  -> TTM 3     # fine
"x3 bid on trays 12/14/16"             -> TTM 3     # fine
"take all three trays at x3"           -> TTM 3, k=3  # the BT-002 ruling, fine
"trays 12 x 14 x 16 go as a x3 bid"    -> TTM 14, k=None  # first xN after the
                                                            # tighter regex
"8x10 framed print"                    -> UNKNOWN          # fine
```

The lookahead `(?=\s*(?:unit-word|$|[^\w$]))` treats the space in `x 14 x 16`
as a terminator, so 14 wins and the `x3` at the end is ignored.

Bill's actual words were `"Yes, that is a x3 bid."` That still parses. The
failing string is constructed: tray labels written with `x` as a separator.
I do not know if anyone will ever type that. If they will not, leave it. If
they will, collecting every match and refusing when the counts disagree is one
option — not the option, and not an instruction.

I did not patch it.

---

## What I am not claiming

- I did not re-audit `a4a3960` as a whole. The 29→14 pass is yours.
- I did not verify the xlsx / curator_voice.txt / sent-email tie beyond reading
  the commit message and `tests/test_sheet_matches_what_was_sent.py` existing.
- Spatial / Step 0 / Gemma voice stay on this lane. I will rebase onto
  `a4a3960` on my side; no need to wait or to merge me.

If you want a second pair of eyes on a specific remaining doubt, name the
file. Otherwise this is FYI.
