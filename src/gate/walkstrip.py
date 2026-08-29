"""The walk-path strip: every photo, in shot order, as the auctioneer walked it.

A reconstruction of the photo walk — not a floor plan. Order is evidence (the
walk is why adjacency groups lots at all); physical position is not claimed,
which is exactly the line the submission copy already holds. The serpentine
layout only makes the order readable; the turns are typographic, not surveyed.

Loop closures are the one spatial claim the data actually supports: a lot whose
member photos sit far apart in the walk means the walk RETURNED to it (2↔181 is
the canonical pair, found by embeddings where sequence proximity cannot). Both
endpoints get the same badge so the return is visible without any script.

Photos the current grouping did not seat render as ungrouped tiles rather than
disappearing — a dropped photo hidden from the strip would misrepresent the
walk, and the visible gap is the honest picture of what grouping covers today.
"""

from __future__ import annotations

from html import escape

from src.intake.spatial import Seat

ROW_LEN = 20
"""Tiles per serpentine row. Purely presentational."""

CLOSURE_GAP = 30
"""Sequence gap inside one lot that counts as the walk returning to it.

Below this, split segments are ordinary adjacent shooting; the recorded
long-gap recaptions (2↔181, 1↔284, 26↔455, 15↔404) all clear it by an order
of magnitude.
"""


def closure_pairs(seats: list[Seat], gap: int = CLOSURE_GAP,
                  sequences: dict[str, int] | None = None) -> list[tuple[str, int, int]]:
    """(lot_id, anchor_seq, return_seq) for every walk return inside a seat.

    A seat's member sequences are split into segments wherever consecutive
    members sit more than ``gap`` apart; each later segment's first sequence is
    a return to the first segment's anchor.
    """
    out: list[tuple[str, int, int]] = []
    for seat in seats:
        seqs = sorted(
            sequences[pid] if sequences else int(pid)
            for pid in seat.photo_ids
            if sequences is None or pid in sequences
        )
        if len(seqs) < 2:
            continue
        anchor = seqs[0]
        prev = seqs[0]
        for seq in seqs[1:]:
            if seq - prev > gap:
                out.append((seat.lot_id, anchor, seq))
            prev = seq
    return out


_CSS = """
:root{--bg:#f6f4ef;--ink:#232019;--line:#d8d2c4;--run-a:#7a6f57;--run-b:#4a6b6e;
--accent:#b4552d;--muted:#8b837f;--tile:#fffdf8}
@media (prefers-color-scheme: dark){
:root{--bg:#181613;--ink:#e8e2d4;--line:#3a362c;--run-a:#a99a77;--run-b:#7fa6aa;
--accent:#e0794b;--muted:#8b837f;--tile:#211e19}}
*{box-sizing:border-box}
body{margin:0;padding:24px;background:var(--bg);color:var(--ink);
font:14px/1.5 ui-sans-serif,system-ui,sans-serif}
h1{font:600 20px/1.2 ui-monospace,Menlo,monospace;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 6px}
.honesty{font-style:italic;color:var(--muted);margin:0 0 18px;max-width:70ch}
.legend{display:flex;gap:18px;flex-wrap:wrap;margin:0 0 18px;color:var(--muted);
font-size:12px;align-items:center}
.legend .swatch{display:inline-block;width:12px;height:12px;border-radius:2px;
vertical-align:-1px;margin-right:5px}
.strip{max-width:100%;overflow-x:auto}
.row{display:flex;gap:6px;align-items:flex-end;margin-bottom:14px}
.row.rev{flex-direction:row-reverse}
.turn{align-self:center;color:var(--muted);font-size:18px;padding:0 4px}
.tile{margin:0;width:96px;flex:none;border:2px solid var(--line);border-radius:4px;
background:var(--tile);padding:3px;position:relative}
.tile.run-a{border-color:var(--run-a)}
.tile.run-b{border-color:var(--run-b)}
.tile.ungrouped{border-style:dashed;opacity:.62}
.tile img{width:100%;height:66px;object-fit:cover;display:block;border-radius:2px;
background:var(--line);color:var(--muted);font-size:10px}
.tile .seq{font:600 10px ui-monospace,Menlo,monospace;color:var(--muted)}
.tile .lot{font:600 10px ui-monospace,Menlo,monospace;color:var(--ink);
white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tile .badge{position:absolute;top:-9px;right:-6px;background:var(--accent);
color:var(--bg);font:700 9px/1 ui-monospace,Menlo,monospace;padding:3px 5px;
border-radius:8px}
.closures{margin:18px 0 0;color:var(--muted);font-size:12px}
.closures b{color:var(--accent)}
"""


def _tile(photo: dict, lot_id: str | None, run_class: str,
          label: bool, badge: str | None) -> str:
    seq = int(photo.get("sequence", 0))
    caption = escape(str(photo.get("caption") or ""), quote=True)
    lot = escape(lot_id, quote=True) if lot_id else None
    badge_html = f'<span class="badge">&#10554; {escape(badge)}</span>' if badge else ""
    lot_html = f'<span class="lot">{lot}</span>' if (lot and label) else ""
    cls = f"tile {run_class}" if lot else "tile ungrouped"
    return (
        f'<figure class="{cls}" title="{caption}">'
        f'{badge_html}'
        f'<img src="/walk/photo/{seq}" alt="{seq}" loading="lazy">'
        f'<span class="seq">{seq:03d}</span> {lot_html}'
        "</figure>"
    )


def render_walk_strip(photos: list[dict], seats: list[Seat], *,
                      cycle_id: str, listing_id: str,
                      row_len: int = ROW_LEN, gap: int = CLOSURE_GAP) -> str:
    ordered = sorted(photos, key=lambda p: int(p.get("sequence", 0)))
    lot_of: dict[str, str] = {}
    for seat in seats:
        for pid in seat.photo_ids:
            lot_of[pid] = seat.lot_id

    sequences = {str(p.get("photo_id")): int(p.get("sequence", 0)) for p in ordered}
    closures = closure_pairs(seats, gap=gap, sequences=sequences)
    badge_at = {seq: lot for lot, _anchor, seq in closures}
    badge_at.update({anchor: lot for lot, anchor, _seq in closures})

    tiles: list[str] = []
    prev_lot: str | None = None
    run_class = "run-b"
    for p in ordered:
        pid = str(p.get("photo_id"))
        lot = lot_of.get(pid)
        if lot is not None and lot != prev_lot:
            run_class = "run-b" if run_class == "run-a" else "run-a"
        seq = int(p.get("sequence", 0))
        tiles.append(_tile(p, lot, run_class,
                           label=(lot is not None and lot != prev_lot),
                           badge=badge_at.get(seq)))
        prev_lot = lot if lot is not None else prev_lot

    rows: list[str] = []
    for i in range(0, len(tiles), row_len):
        chunk = tiles[i:i + row_len]
        rev = (i // row_len) % 2 == 1
        turn = '<span class="turn">&#8631;</span>' if rev else '<span class="turn">&#8630;</span>'
        rows.append(
            f'<div class="row{" rev" if rev else ""}">' + "".join(chunk) + turn + "</div>"
        )

    grouped = sum(1 for p in ordered if str(p.get("photo_id")) in lot_of)
    ungrouped = len(ordered) - grouped
    closure_lines = "".join(
        f"<div><b>&#10554; {escape(lot)}</b>: shot at {anchor:03d}, "
        f"the walk returned at {seq:03d} "
        f"({seq - anchor} frames later)</div>"
        for lot, anchor, seq in sorted(closures, key=lambda c: c[1])
    ) or "<div>No walk returns detected in this grouping.</div>"

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Walk &middot; {escape(cycle_id)}</title>
<style>{_CSS}</style></head><body>
<h1>The Walk &mdash; {escape(cycle_id)} (listing {escape(listing_id)})</h1>
<p class="sub">{len(ordered)} photos &middot; {len(seats)} lots &middot;
{ungrouped} not grouped by the current pass</p>
<p class="honesty">A reconstruction of the auctioneer's photo walk, in shot
order. Order is evidence; physical position is not claimed. Serpentine turns
are typographic, not surveyed.</p>
<div class="legend">
<span><span class="swatch" style="background:var(--run-a)"></span><span
class="swatch" style="background:var(--run-b)"></span>alternating colors mark
lot boundaries</span>
<span><span class="swatch" style="background:var(--accent)"></span>&#10554;
walk returned to this lot</span>
<span><span class="swatch" style="border:2px dashed var(--muted);background:none">
</span>not grouped</span>
</div>
<div class="strip">{"".join(rows)}</div>
<div class="closures"><b>Walk returns</b> &mdash; far-apart frames the grouping
identified as the same lot:{closure_lines}</div>
</body></html>"""
