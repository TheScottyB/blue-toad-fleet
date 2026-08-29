#!/usr/bin/env python3
"""
Google-Search the lots that never entered grounded_prices.json.

Writes a SIDECAR. Does not overlay the live sheet — load_grounded_prices still
reads grounded_prices.json only. Resume-safe.

    python scripts/run_grounded_search_remaining.py
    python scripts/run_grounded_search_remaining.py --limit 5 --workers 2
"""

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.appraiser import AppraisalEngine
from src.appraiser.pricing import median_price, price_is_usable, MIN_CALLS
from src.assemble.grounded import load_grounded_prices

DATA = ROOT / "data" / "aug22_gallery_4160518"
CACHE = DATA / "grounded_search_remaining.json"


def _query_for(lot, seq, triage_by_photo) -> tuple[str, str]:
    cap = (lot.caption or "").strip()
    photo = seq.get(lot.lot_id) or {}
    triage = triage_by_photo.get(photo.get("photo_id")) or {}
    ident = cap or (triage.get("summary") or "").strip() or (photo.get("caption") or "").strip()
    cat = lot.category or triage.get("category") or ""
    return ident, cat


def search_one(lot_row: dict) -> dict:
    engine = AppraisalEngine()
    samples, notes = [], []
    for _ in range(MIN_CALLS):
        try:
            hit = engine.grounded_search(
                lot_row.get("identification", ""), lot_row.get("category", ""))
        except Exception as e:
            print(f"    {lot_row['lot_id']}: call failed — {str(e)[:70]}",
                  file=sys.stderr)
            hit = None
        if hit is None:
            samples.append(None)
            notes.append(None)
            continue
        samples.append(hit.get("price"))
        notes.append({
            "prose": hit.get("prose") or "",
            "sources": hit.get("sources") or [],
        })

    usable = price_is_usable(samples)
    merged = median_price(samples)
    return {
        "lot_id": lot_row["lot_id"],
        "identification": lot_row.get("identification", ""),
        "category": lot_row.get("category", ""),
        "fit_score": lot_row.get("fit_score"),
        "usable": bool(usable),
        "low": merged.low if merged else None,
        "high": merged.high if merged else None,
        "sold_comp_count": merged.sold_comp_count if merged else 0,
        "sources": merged.sources if merged else [],
        "samples": [None if s is None else
                    {"low": s.low, "high": s.high, "comps": s.sold_comp_count}
                    for s in samples],
        "notes": notes,
    }


def remaining_lots():
    from src.server import get_aug22_state
    already = load_grounded_prices()
    photos = json.loads((DATA / "manifest.json").read_text())["photos"]
    seq = {f"BT-{p['sequence']:03d}": p for p in photos}
    triage = json.loads((DATA / "triage_results.json").read_text())
    triage_by_photo = {t.get("photo_id"): t for t in triage}
    _, _, lots, _, _, _, _ = get_aug22_state()
    out = []
    for lot in lots:
        if lot.lot_id in already:
            continue
        ident, cat = _query_for(lot, seq, triage_by_photo)
        out.append({
            "lot_id": lot.lot_id,
            "identification": ident,
            "category": cat,
            "fit_score": lot.fit_score,
        })
    out.sort(key=lambda r: r["lot_id"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    done = {}
    if CACHE.exists():
        raw = json.loads(CACHE.read_text())
        if isinstance(raw, list):
            done = {r["lot_id"]: r for r in raw if isinstance(r, dict) and r.get("lot_id")}

    todo = [l for l in remaining_lots() if l["lot_id"] not in done]
    if args.limit:
        todo = todo[:args.limit]

    print(f"[*] sidecar {CACHE.name}: {len(done)} done, {len(todo)} to search, "
          f"{args.workers} workers", flush=True)
    if not todo:
        print("[=] nothing to do", flush=True)
        return 0

    t0 = time.time()
    results = list(done.values())
    completed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(search_one, l): l for l in todo}
        for f in as_completed(futures):
            row = f.result()
            results.append(row)
            completed += 1
            mark = "OK " if row["usable"] else "refused"
            span = (f"${row['low']:,.0f}-${row['high']:,.0f}"
                    if row["low"] else "no price")
            notes_ok = sum(1 for n in row.get("notes") or [] if n and n.get("prose"))
            print(f"  [{completed}/{len(todo)}] {row['lot_id']} {mark:>7}  {span:>16}  "
                  f"{row['sold_comp_count']} comps  {notes_ok}/3 notes  "
                  f"{len(row['sources'])} src", flush=True)
            CACHE.write_text(json.dumps(sorted(results, key=lambda r: r["lot_id"]), indent=1))

    with_notes = sum(1 for r in results if any((n or {}).get("prose")
                                               for n in (r.get("notes") or [])))
    usable = [r for r in results if r["usable"]]
    print(flush=True)
    print(f"[✓] {with_notes}/{len(results)} have search notes, "
          f"{len(usable)}/{len(results)} would pass agreement "
          f"in {time.time()-t0:.0f}s -> {CACHE}", flush=True)
    print("[=] sidecar only; grounded_prices.json and the live sheet were not written",
          flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
