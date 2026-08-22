# BT-235 — comp report

**1933 Chicago World's Fair "A Century of Progress" embossed clear glass souvenir
bottle with metal cap**

| | |
|---|---|
| Captured | Screenshots **2026-08-22 01:03 CDT** · raw exports **01:12:04 CDT** |
| Source | eBay Seller Hub → Research → Product research, authenticated as `richmondgeneral` |
| Query | `1933 Century of Progress bottle` |
| Marketplace | `EBAY-US`, All Categories, no condition/format/price filter |
| Sold window | **Aug 21, 2025 – Aug 21, 2026** — as printed by the page, not as requested |
| Method | `docs/PLAYBOOK-ebay-velocity.md` |
| Screenshot | `sold_365d.png` · `active.png` — captured autonomously, see Evidence |

---

## Result

```
sold units, 365d          46      (45 rows; one listing sold 2)
active listings now       46      (page's own "Total active listings")

ABSORPTION                46 / 46 = 1.00
months of supply          12.0

avg sold price        $24.11      range $4.99 – $105.00
avg shipping           $8.83      landed ~$32.94
free shipping             7%
sell-through                -     (empty on this query)
total sellers              43
```

**Active side:** avg listing `$30.45`, range `$9.00 – $89.99`, avg shipping
`$10.02`, free shipping `15%`, promoted `22%`.

Sellers are asking `$30.45` against a `$24.11` realised average — asks run about
26% above what actually clears.

## Against the sheet

The Aug 22 sheet bids BT-235 at **max $10.00 / all-in $11.50**
(`data/BlueToad_2026-08-22_BidSheet.xlsx`, verified). Against a `$32.94` landed
comp that is a **3.3x spread** — the best ratio of the lots comped this session.

But absorption `1.00` means one full year of standing supply. Best margin,
slowest money. That is the trade the velocity number exists to make visible;
price alone would have ranked this lot above BT-041, and on turn it is behind.

## Comp quality

Not every result is the same object. Visible in the active set: **bottle openers**
and a **metal key fob bottle opener** (not bottles), a **"Bottle Art Deco
Waterfall"**, and lidded jars vs plain bottles vs capped bottles — which are
different objects at different prices.

**Non-comp count is NOT finalised for this lot.** An automated pattern flagged 17
of 46 active, but reading the flagged rows back, several are genuine bottles that
the pattern over-matched. The absorption figure tolerates this — junk appears in
both numerator and denominator and largely cancels — but **the price band does
not**, and `$4.99 – $105.00` is wide enough that the cap/no-cap/lid distinction
is probably doing real work inside it. Anyone quoting a price off this report
should classify the rows first.

## Evidence

`sold_365d.png` and `active.png` in this folder, captured by
`scripts/cdp_capture.py` from the authenticated Seller Hub session. Each frame
carries, in the picture itself: the signed-in account (`richmondgeneral`), the
query, the range control, the date window as the page printed it, and the whole
aggregate strip. Nothing in them is transcribed by an agent.

That is the point of the format. Text is the medium an agent fabricates in; a
screenshot is not. The operator: *"ive never seen an agent generate a fake
screenshot image, ive seen them make a lot shit up in text."* Where the figures
in this report and the pixels disagree, **the pixels are correct.**

The capture script exits non-zero if it lands on a signin or challenge page, so
a picture of a login screen cannot be filed here as proof.

The same page state is also preserved as re-parseable text:

- `sold_365d.tsv` — 45 rows: price, quantity, date, title
- `active.txt` — all 46 active listing titles
- `capture.json` — both aggregate blocks and capture metadata

The raw exports were read from the same fixed query URLs nine minutes after the
screenshots; the aggregates and row counts match the pixels.

**These figures still cannot be reproduced later.** The 365-day window rolls
daily and active counts change hourly. The screenshots are the record of what
the page showed at the stated timestamps.
