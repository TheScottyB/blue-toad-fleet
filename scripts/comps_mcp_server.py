#!/usr/bin/env python3
"""
scripts/comps_mcp_server.py — the comp connector for the desktop Cowork app.

An MCP server (stdio) exposing the eBay Seller Hub lookups and intelligent
comp selection to any local Claude surface. Everything runs on THIS machine:
the Cowork app, this server, and the dedicated CDP Chrome that is signed in to
Seller Hub as the operator — so the data path is exactly the one the comp
reports already use, screenshots included.

Prerequisites (one-time):

  1. The dedicated Chrome is running with remote debugging:
         /Applications/Google Chrome.app/Contents/MacOS/Google Chrome \
           --remote-debugging-port=9222 --user-data-dir=$HOME/.btf-chrome-profile \
           --no-first-run --no-default-browser-check about:blank &
  2. That window is signed in to eBay (once; the profile persists).
  3. `pip install -r requirements.txt` (declares `mcp` and `websockets`).

Register with the Cowork / Claude Code app (from the repo root):

    claude mcp add btf-comps -- \
      "$(pwd)/.venv/bin/python" "$(pwd)/scripts/comps_mcp_server.py"

Design constraints inherited from the playbook and the operator, restated here
because they are enforced in the layers below, not in this file:

  - ebay_velocity = sold_units_365d / active_now. An absorption rate,
    CHANNEL-SPECIFIC to eBay. Days-on-market is not computed anywhere.
  - A silent empty page raises rather than reading as "sold 0".
  - Comp selection answers "is this THAT item" per row; "unsure" is a valid
    verdict; selection failure is reported as UNFILTERED, never hidden.
  - Screenshots are the proof medium. A failed capture is reported as failed.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp.server import MCPServer  # noqa: E402

from src.comps import (absorption, months_of_supply,  # noqa: E402
                       require_annual_window, require_known_condition)
from src.comps import live  # noqa: E402

server = MCPServer(
    name="btf-comps",
    title="Blue Toad Fleet — eBay comp connector",
    instructions=(
        "eBay Seller Hub research for one identified auction lot, on the "
        "operator's own seller account. `ebay_absorption` is the cheap pass: "
        "the channel-specific velocity number. `ebay_comps` is the full read: "
        "absorption plus model-screened comparables ('is this THAT item') and "
        "a comp-only price band, with optional screenshot evidence. All "
        "figures are eBay-channel only and expire as the 365-day window "
        "rolls; the `window_as_printed` field is the authority on what was "
        "measured. Read-only on the account: research pages only, never "
        "listings, orders, or messages."),
)


@server.tool(
    description=(
        "Absorption rate for a search query on eBay: sold units in the last "
        "365 days divided by active listings now. Channel-specific (eBay "
        "only). Cheap — no model calls, no screenshots. Returns the window "
        "the page actually printed, which is the authority on what was "
        "measured — and REFUSES (NonAnnualWindow) when that printed window "
        "is absent or not ~365 days, rather than serving a mis-windowed "
        "count as annual. `sold_results_truncated` true means the page cap "
        "stopped the walk with rows unread: sold figures are a floor. "
        "Raises rather than returning 0 when the page renders "
        "empty without eBay's own zero-results message. `filters_as_printed` "
        "lists the filter markers the page showed. Measured 2026-08-29: a "
        "sticky chip can be display-only (data unfiltered), so non-empty = "
        "the page CLAIMED that scope; [] = clean bar; null = no bar printed "
        "(unknown). Optional condition_id (known eBay ids only, e.g. 3000 "
        "Used, 1000 New) genuinely scopes the read; unknown ids are refused "
        "because the server silently ignores them."))
def ebay_absorption(query: str, condition_id: int | None = None) -> dict:
    label = require_known_condition(condition_id)
    sold = live.read_sold(query, condition_id=condition_id)
    require_annual_window(sold)
    active = live.read_active(query, condition_id=condition_id)
    rate = absorption(sold.sold_units, active.total_active or 0)
    return {
        "query": query,
        "channel": "eBay only — not store or other channels",
        "condition_scope": {
            "condition_id": condition_id,
            "label": (label if condition_id is not None
                      else "no condition filter sent — unfiltered read")},
        "window_as_printed": sold.window,
        "filters_as_printed": {"sold": sold.filters, "active": active.filters},
        "sold_units_365d": sold.sold_units,
        "sold_listings_365d": len(sold.rows),
        "sold_results_truncated": sold.truncated,
        "active_now": active.total_active,
        "absorption": rate,
        "months_of_supply": months_of_supply(sold.sold_units,
                                             active.total_active or 0),
        "genuine_zero": sold.genuine_zero,
        "landed_avg_unfiltered": sold.landed_avg,
    }


@server.tool(
    description=(
        "Full comp read for ONE identified lot: absorption (raw, by design — "
        "it survives a dirty comp set), model-screened comparables answering "
        "'is this THAT item' per listing title, a comp-only price band "
        "(price does NOT survive a dirty set), and optional screenshot "
        "evidence written under data/comps/. `identification` is the "
        "appraiser's description of the item; `query` defaults to it. "
        "REFUSES (NonAnnualWindow) when the sold page's printed window is "
        "absent or not ~365 days; `sold_results_truncated` true means the "
        "sold figures are a floor (page cap hit with rows unread). When "
        "selection is unavailable the result says UNFILTERED explicitly. "
        "`filters_as_printed` lists any filter markers the pages showed — "
        "non-empty means the pages CLAIMED that scope (a sticky chip can be "
        "display-only; measured 2026-08-29), so verify before trusting. "
        "Optional condition_id (known eBay ids only) genuinely scopes the "
        "read; unknown ids are refused, not silently ignored."))
def ebay_comps(identification: str, query: str | None = None,
               with_evidence: bool = False,
               condition_id: int | None = None) -> dict:
    q = query or identification
    evidence_dir = None
    if with_evidence:
        import datetime
        day = datetime.date.today().isoformat()
        safe = "".join(c if c.isalnum() else "-" for c in q)[:48]
        evidence_dir = ROOT / "data" / "comps" / day / safe
    return live.comp_report(identification, q, evidence_dir,
                            condition_id=condition_id)


if __name__ == "__main__":
    server.run("stdio")
