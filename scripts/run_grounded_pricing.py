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
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.appraiser.grounded_batch import run_grounded_pricing_batch
from scripts.run_vertex_pipeline import REFERENCE_COMPS

DATA = ROOT / "data" / "aug22_gallery_4160518"
CACHE = DATA / "grounded_prices.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-fit", type=float, default=0.70)
    ap.add_argument("--limit", type=int, default=0, help="0 = every qualifying lot")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    appraisals = json.loads((DATA / "appraisal_results.json").read_text())
    results = run_grounded_pricing_batch(
        appraisals,
        CACHE,
        min_fit=args.min_fit,
        workers=args.workers,
        limit=args.limit,
        excluded_lot_ids=set(REFERENCE_COMPS),
        progress_callback=lambda done, total: print(f"  [{done}/{total}]", flush=True),
    )
    usable = [r for r in results if r["usable"]]
    print(f"[✓] {len(usable)}/{len(results)} priced with agreement -> {CACHE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
