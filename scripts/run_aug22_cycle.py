#!/usr/bin/env python3
"""
scripts/run_aug22_cycle.py — Final Sealed August 22 Absentee Bid Sourcing Run.

Strict Auction Sourcing Constraints:
- Topps Cards: Selected BT-001 (Golden Era 1959-69 in top-loaders), Dropped bulk BT-284
- Costume Jewelry: BT-002, BT-087, BT-181 approved at $25.00 max bid each
- Edison Rolls: BT-041 approved at $40.00 max bid
- Fast Smalls: Princess Phone ($20), ET Nightlight ($20), Century Progress Bottle ($15),
  Lionel Set ($25), Trading Cards ($15 x 2), Handheld Games ($10)
- Standard Auction Bidding Increments ($5 up to $100)
- Transmission Mode: STUBBED / LOCAL DRAFT (No live emails sent)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_vertex_pipeline import run_pipeline, REFERENCE_COMPS

# Exact approved bids compatibility export
APPROVED_BIDS = [
    ("BT-001", 1, "Vintage Topps Baseball Cards (1959-69 Golden Era Stars)", "vintage cards", 35.00, 100.00, "$250-$500"),
    ("BT-041", 41, "Edison rolls (11-12 canisters + bare roll)", "phonograph / records", 15.00, 40.00, "$100-$160"),
    ("BT-002", 2, "Estate Costume Jewelry (Tray 12/14/16: 50-70 pcs)", "jewelry", 10.00, 25.00, "$80-$160"),
    ("BT-087", 87, "costume jewelry (Tray Lot 2)", "jewelry", 10.00, 25.00, "$80-$160"),
    ("BT-181", 181, "estate costume jewelry (Tray Lot 3)", "jewelry", 10.00, 25.00, "$80-$160"),
    ("BT-050", 50, "Lionel building set", "vintage toys", 10.00, 25.00, "$50-$120"),
    ("BT-021", 21, "princess phone", "vintage electronics", 10.00, 20.00, "$40-$100"),
    ("BT-048", 48, "ET nightlight", "vintage smalls", 10.00, 20.00, "$40-$100"),
    ("BT-235", 235, "Century Progress bottle", "advertising / bottles", 10.00, 15.00, "$30-$80"),
    ("BT-016", 16, "trading cards", "vintage cards", 10.00, 15.00, "$30-$80"),
    ("BT-030", 30, "non-sport trading cards", "vintage cards", 10.00, 15.00, "$30-$80"),
    ("BT-066", 66, "hand held video games (5 Radica/LCD units)", "vintage toys", 5.00, 10.00, "$25-$45"),
]

def main():
    force_live = "--live" in sys.argv
    run_pipeline(
        cycle_id="2026-08-22",
        listing_id="4160518",
        budget_cap=600.00,
        auto_send_threshold=35.00,
        force_live_vertex=force_live,
    )

if __name__ == "__main__":
    main()
