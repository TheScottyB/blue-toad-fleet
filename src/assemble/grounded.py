"""Read the offline grounded-price cache. Does not price the live sheet.

`scripts/run_grounded_pricing.py` writes this file. The absentee sheet that
went to Blue Toad is still `REFERENCE_COMPS` plus operator fit/cap. Overlaying
these 21 usable rows onto allocate() would move the sheet from 9 bids / $275
to 23 / $460 — so the live path must not silently merge them.
"""

from __future__ import annotations

import json
from pathlib import Path


def load_grounded_prices(path=None) -> dict[str, dict]:
    path = Path(path or "data/aug22_gallery_4160518/grounded_prices.json")
    if not path.is_file():
        alt = Path("/app") / path
        path = alt if alt.is_file() else path
    if not path.is_file():
        return {}
    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        return {}
    return {row["lot_id"]: row for row in raw if isinstance(row, dict) and row.get("lot_id")}
