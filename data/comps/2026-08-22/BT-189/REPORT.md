# BT-189 — comp report

**Concert poster: Pink Floyd, The Who, and The Move at The Palace Theatre,
Manchester ("Psychedelicamania", 31 Dec 1966)** — appraised as *"likely a later
reproduction or fantasy print"*, marks including the `(281)` catalogue number.

| | |
|---|---|
| Screenshots | `sold_365d.png` **2026-08-22 01:10:30 CDT** · `active.png` **01:11:19 CDT** |
| Raw figures | `data/comps/2026-08-22_ebay_absorption.json`, recorded 2026-08-22T00:40 CDT |
| Source | eBay Seller Hub → Research → Product research, authenticated as `richmondgeneral` |
| Query | `Pink Floyd 1966 concert poster` (the exact-venue query `Pink Floyd Palace Theatre Manchester poster` returned a **genuine zero** — the page's own "No sold results found" message, which is how a real empty market is distinguished from the silent-render bug) |
| Sold window | **Aug 21, 2025 – Aug 21, 2026** — as printed by the page (visible in `sold_365d.png`) |
| Method | `docs/PLAYBOOK-ebay-velocity.md` |

---

## Result

```
sold units, 365d           15     (12 listings; short first page = complete)
active listings now        20     (3 are not posters at all: two t-shirts,
                                   a holofoil trading card in a toploader)

ABSORPTION               0.75     months of supply 16.0

avg sold price         $22.12     range $6.98 – $65.00
avg shipping            $6.02     landed ~$28.14
free shipping             35%     total sellers 11
```

## The finding: zero originals in a year

Every sold comp is a reproduction, and the titles say so: *"Giclee Print"*,
*"Home Art Decor"*, *"2nd print Handbill"*, four at `11 X 17` — a modern repro
size. **Not one original sold in 365 days.** The market confirms the
appraiser's own hedge, and the earlier suspicion that the $25 hint was badly
low is withdrawn: $25 against a $28.14 landed repro comp is **89% of market —
a good call, not a low one.**

The velocity comparison is the sharper lesson. At nearly the same price point
as the Boston Champion sharpener ($22.12 vs $21.44 avg sold), the poster
absorbs at **0.75 vs 2.14** — 16 months of supply against 5.6. Price alone
cannot tell these two items apart; absorption can, and this pair is the first
recorded instance of the metric doing that separation on real lots.

## Against the sheet, and the outcome

**BT-189 was never bid** (`on_sheet: false`). Triage scored it fit 0.4;
the appraiser's repro reading plus a $25-grade value put it below the sheet's
line, and the comps above vindicate that outcome: slow absorption, repro-only
market, thin margin at the $10–$15 bid it would have merited.

**The auction concluded 2026-08-22 with no lots won** — Blue Toad's reply
*"sorry you did not win"* (Bill Theesfield, 2026-08-22 22:22Z, Gmail message
`1a02b9171cc30d2a`) — so the not-bid decision cost nothing either way.

## Evidence

`sold_365d.png` and `active.png` in this folder, captured autonomously by
`scripts/cdp_capture.py` from the authenticated session. The frames carry the
account, query, range control, page-printed window, and full aggregate strip.
Where this report and the pixels disagree, the pixels are correct.

**These figures cannot be reproduced later** — the 365-day window rolls daily
and active counts change hourly. This is the record of what the page showed at
the stated timestamps.
