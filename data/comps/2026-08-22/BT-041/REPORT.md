# BT-041 — comp report

**Lot of Edison phonograph cylinder records and cardboard containers, including
Edison Gold Moulded Record and Blue Amberol Record tubes, Thomas A. Edison,
Inc., early 20th century** — 11–12 canisters plus a bare roll.

| | |
|---|---|
| Screenshots | `sold_365d.png` **2026-08-22 01:04:07 CDT** · `active.png` **01:06:07 CDT** |
| Raw figures | `data/comps/2026-08-22_ebay_absorption.json`, recorded 2026-08-22T00:40 CDT |
| Source | eBay Seller Hub → Research → Product research, authenticated as `richmondgeneral` |
| Query | `Edison cylinder records lot` |
| Sold window | **Aug 21, 2025 – Aug 21, 2026** — as printed by the page (visible in `sold_365d.png`) |
| Method | `docs/PLAYBOOK-ebay-velocity.md` |

---

## Result

```
sold units, 365d        >=450     (offsets 0,100,200,400 all full pages;
                                   walk NOT completed — floor, not a count)
active listings now       233     (page's own "Total active listings")

ABSORPTION              >=1.93    months of supply <=6.2

avg sold price         $46.39     range $0.99 – $550.00
avg shipping           $14.04     landed ~$60.43
free shipping             12%     total sellers 282 (visible in sold_365d.png)
```

## QUERY TOO BROAD — the caveat that governs every price figure above

`Edison cylinder records lot` catches single cylinders and Brown Wax lots at
$102–$112 alongside container lots at $29–$43. The `$0.99 – $550.00` range is
the tell. For an 11–12 canister Gold Moulded / Blue Amberol lot like this one,
**the honest price band is the $29–$43 container-lot cluster, not the $46.39
average.** Absorption survives the broad query (junk sits in both numerator and
denominator); the price does not. This is the second lot on which that rule
held, and it is why the sold-units figure is stated as a floor: completing the
walk on a query this broad sharpens a number that is already decisive.

## Against the sheet, and the outcome

The sent sheet bid BT-041 at **START $5.00 / MAX $25.00**
(`data/aug22_absentee_bid_email_REVISED.txt:47`) — a 2.4x spread against even
the conservative $60.43 unfiltered landed average, on the deepest, fastest
market of the four lots comped this cycle. The operator's note called Edison
cylinders "an alpha pick this cycle"; the comps agreed.

**Outcome: LOST.** The auction concluded 2026-08-22; Blue Toad's own reply —
*"sorry you did not win"*, Bill Theesfield, 2026-08-22 22:22Z, Gmail message
`1a02b9171cc30d2a` — confirms no lot on the sheet was won. A $25 defensive max
on a lot with a $29–$43 comp cluster is a cap the room can beat without
overpaying; losing it is the system working as designed, not a defect. The
number to revisit next cycle is the cap, not the comp.

## Evidence

`sold_365d.png` and `active.png` in this folder, captured autonomously by
`scripts/cdp_capture.py` from the authenticated session. The frames carry the
account, query, range control, page-printed window, and full aggregate strip.
Where this report and the pixels disagree, the pixels are correct.

**These figures cannot be reproduced later** — the 365-day window rolls daily
and active counts change hourly. This is the record of what the page showed at
the stated timestamps.
