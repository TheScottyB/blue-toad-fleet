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
  - A silent empty response raises rather than reading as "sold 0".
  - Comp selection answers "is this THAT item" per row; "unsure" is a valid
    verdict; selection failure is reported as UNFILTERED, never hidden.
  - The raw API responses are the proof medium (re-parseable); screenshots
    are optional, and a failed capture is reported as failed.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp.server import MCPServer  # noqa: E402

from src.comps import live  # noqa: E402

server = MCPServer(
    name="btf-comps",
    title="Blue Toad Fleet — eBay comp connector",
    instructions=(
        "eBay Seller Hub research for one identified item, on the operator's "
        "own seller account, read from the Seller Hub research JSON API. "
        "`ebay_absorption` is the cheap pass: the channel-specific velocity "
        "number. `ebay_comps` is the full read: absorption plus "
        "model-screened comparables ('is this THAT item') with prices, "
        "shipping and /itm/ links, comp-only price stats, and the lowest "
        "active asks. All figures are eBay-channel only over a pinned "
        "365-day window. Read-only on the account: research endpoints only, "
        "never listings, orders, or messages."),
)


@server.tool(
    description=(
        "Absorption rate for a search query on eBay: sold units in the last "
        "365 days divided by active listings now. Channel-specific (eBay "
        "only). Cheap — no model calls. The 365-day window is pinned with "
        "explicit dates and every returned sale date is checked inside it; "
        "REFUSES (NonAnnualWindow) otherwise. `sold_results_truncated` true "
        "means the page cap stopped the walk with rows unread: sold figures "
        "are a floor. Raises rather than returning 0 when the response is "
        "empty without eBay's own zero-results message. `sold_cross_check` "
        "compares the row-by-row unit walk with eBay's Total sold aggregate. "
        "Optional condition_id (known eBay ids only, e.g. 3000 Used, 1000 "
        "New) genuinely scopes the read; unknown ids are refused because the "
        "server silently ignores them. Seller Hub UI filter chips do not "
        "scope these reads."))
def ebay_absorption(query: str, condition_id: int | None = None) -> dict:
    return live.absorption_report(query, condition_id=condition_id)


@server.tool(
    description=(
        "Full comp read for ONE identified item: absorption (raw, by design "
        "— it survives a dirty comp set), model-screened comparables "
        "answering 'is this THAT item' per listing title — each with price, "
        "shipping, landed total, date and /itm/ link — comp-only price stats "
        "(median, quartiles, landed), and the five lowest active asks. "
        "`identification` is the appraiser's description of the item; "
        "`query` defaults to it. `with_evidence` saves the raw API responses "
        "(and, with `screenshots`, Seller Hub PNGs) under data/comps/. "
        "`include_rows` adds every sold row with its verdict. REFUSES "
        "(NonAnnualWindow) when the window is not a year or a sale date "
        "falls outside it. When selection is unavailable the result says "
        "UNFILTERED explicitly. Optional condition_id (known eBay ids only) "
        "genuinely scopes the read; unknown ids are refused."))
def ebay_comps(identification: str, query: str | None = None,
               with_evidence: bool = False,
               condition_id: int | None = None,
               screenshots: bool = False,
               include_rows: bool = False) -> dict:
    q = query or identification
    evidence_dir = None
    if with_evidence or screenshots:
        import datetime
        day = datetime.date.today().isoformat()
        safe = "".join(c if c.isalnum() else "-" for c in q)[:48]
        evidence_dir = ROOT / "data" / "comps" / day / safe
    return live.comp_report(identification, q, evidence_dir,
                            condition_id=condition_id,
                            screenshots=screenshots,
                            include_rows=include_rows)


if __name__ == "__main__":
    server.run("stdio")
