#!/usr/bin/env python3
"""
scripts/comps_cli.py — the comp connector from any shell.

The same reads the MCP server exposes, printed as JSON on stdout, so
scripts, cron jobs, and agents without MCP registration (e.g. the Richmond
General pricing workflow) get byte-identical output to a tool call. This
file is deliberately a THIN argparse wrapper over the exact tool functions
in scripts/comps_mcp_server.py — one source of truth for what a read
returns.

Usage (from the repo root, with the dedicated CDP Chrome running):

    .venv/bin/python scripts/comps_cli.py absorption "boston champion pencil sharpener"
    .venv/bin/python scripts/comps_cli.py absorption "sega nomad" --condition-id 3000
    .venv/bin/python scripts/comps_cli.py comps "Boston Champion hand-crank sharpener, complete" \
        --query "boston champion pencil sharpener" --with-evidence

Guards exit nonzero with the reason on stderr — a wrong number never
leaves as exit 0: NonAnnualWindow (the printed window is not a year),
SuspectEmpty (silent empty page), ChallengePage (bot wall),
UnknownConditionId (the server would silently ignore the id).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts import comps_mcp_server  # noqa: E402


_CONDITION_HELP = (
    "scope the read to one eBay condition id (e.g. 3000 Used, 1000 New, "
    "7000 for-parts); unknown ids are refused, not silently ignored; "
    "omitted = unfiltered read")

_EPILOG = """\
exit status:
  0   the read completed; JSON on stdout
  1   the read was REFUSED, reason on stderr — never "sold 0". Refusals:
      bot wall, silent-empty page, non-annual printed window, unknown
      condition id.

prerequisite: the dedicated CDP Chrome on port 9222 (profile
~/.btf-chrome-profile, signed in to Seller Hub). All figures are
eBay-channel only. Gotchas: docs/PLAYBOOK-ebay-velocity.md."""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="comps_cli",
        description="eBay Seller Hub comp reads (same output as the "
                    "btf-comps MCP tools)",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_abs = sub.add_parser(
        "absorption", help="the cheap pass: channel-specific velocity")
    p_abs.add_argument(
        "query",
        help="Seller Hub search keywords — what a buyer would type")
    p_abs.add_argument("--condition-id", type=int, default=None,
                       help=_CONDITION_HELP)

    p_comps = sub.add_parser(
        "comps", help="the full read: absorption + screened comparables")
    p_comps.add_argument(
        "identification",
        help="what the item IS — the full identification every candidate "
             "listing title is screened against")
    p_comps.add_argument(
        "--query", default=None,
        help="search keywords when they differ from the identification "
             "(default: the identification itself)")
    p_comps.add_argument(
        "--with-evidence", action="store_true",
        help="save Seller Hub screenshot evidence under data/comps/")
    p_comps.add_argument("--condition-id", type=int, default=None,
                         help=_CONDITION_HELP)

    args = parser.parse_args(argv)
    try:
        if args.command == "absorption":
            out = comps_mcp_server.ebay_absorption(
                args.query, condition_id=args.condition_id)
        else:
            out = comps_mcp_server.ebay_comps(
                args.identification, query=args.query,
                with_evidence=args.with_evidence,
                condition_id=args.condition_id)
    except Exception as e:
        print(f"{type(e).__name__}: {e} — read refused", file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
