#!/usr/bin/env python3
"""
scripts/run_grounded_pricing.py — put real prices on the lots the appraiser liked.

Stage 2 identifies every lot; only the twelve with hand-entered comps could ever
be bid. This prices the rest from completed sales, three independent calls per
lot, median each bound, and refuses anything the calls disagree about.

    python scripts/run_grounded_pricing.py --limit 5
    python scripts/run_grounded_pricing.py --min-fit 0.70

Results are cached per lot, so a re-run costs nothing for lots already priced
and the job can be stopped and resumed.
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
from scripts.run_vertex_pipeline import REFERENCE_COMPS

DATA = ROOT / "data" / "aug22_gallery_4160518"
CACHE = DATA / "grounded_prices.json"


def price_one(lot) -> dict:
    """
    Three independent calls for one lot, then the agreement check.

    The engine is built here rather than shared. A single genai client handed to
    a thread pool starts answering "Cannot send a request, as the client has
    been closed" partway through — which drops a lot to two samples and refuses
    it for the wrong reason, looking exactly like genuine disagreement.
    """
    engine = AppraisalEngine()
    samples = []
    for _ in range(MIN_CALLS):
        try:
            samples.append(engine.price_lot_grounded(
                lot.get("identification", ""), lot.get("category", "")))
        except Exception as e:
            samples.append(None)
            print(f"    {lot['lot_id']}: call failed — {str(e)[:70]}", file=sys.stderr)

    usable = price_is_usable(samples)
    merged = median_price(samples)
    return {
        "lot_id": lot["lot_id"],
        "identification": lot.get("identification", ""),
        "category": lot.get("category", ""),
        "fit_score": lot.get("fit_score"),
        "usable": bool(usable),
        "low": merged.low if merged else None,
        "high": merged.high if merged else None,
        "sold_comp_count": merged.sold_comp_count if merged else 0,
        "sources": merged.sources if merged else [],
        "samples": [None if s is None else
                    {"low": s.low, "high": s.high, "comps": s.sold_comp_count}
                    for s in samples],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-fit", type=float, default=0.70)
    ap.add_argument("--limit", type=int, default=0, help="0 = every qualifying lot")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    appraisals = json.loads((DATA / "appraisal_results.json").read_text())
    done = {}
    if CACHE.exists():
        done = {r["lot_id"]: r for r in json.loads(CACHE.read_text())}

    todo = [l for l in appraisals
            if l["lot_id"] not in REFERENCE_COMPS
            and l["lot_id"] not in done
            and float(l.get("fit_score") or 0) >= args.min_fit]
    todo.sort(key=lambda l: -float(l.get("fit_score") or 0))
    if args.limit:
        todo = todo[:args.limit]

    print(f"[*] {len(done)} already priced, {len(todo)} to price "
          f"(fit >= {args.min_fit}), {args.workers} workers")
    if not todo:
        print("[=] nothing to do")
        return 0

    t0 = time.time()
    results = list(done.values())
    completed = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(price_one, l): l for l in todo}
        for f in as_completed(futures):
            row = f.result()
            results.append(row)
            completed += 1
            mark = "OK " if row["usable"] else "refused"
            span = (f"${row['low']:,.0f}-${row['high']:,.0f}"
                    if row["low"] else "no price")
            print(f"  [{completed}/{len(todo)}] {row['lot_id']} {mark:>7}  {span:>16}  "
                  f"{row['sold_comp_count']} comps  {len(row['sources'])} src")
            CACHE.write_text(json.dumps(sorted(results, key=lambda r: r["lot_id"]), indent=1))

    usable = [r for r in results if r["usable"]]
    print()
    print(f"[✓] {len(usable)}/{len(results)} priced with agreement "
          f"in {time.time()-t0:.0f}s -> {CACHE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
