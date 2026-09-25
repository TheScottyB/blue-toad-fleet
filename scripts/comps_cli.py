#!/usr/bin/env python3
"""
scripts/comps_cli.py — the comp connector from any shell.

The same reads the MCP server exposes, printed as JSON on stdout, so
scripts, cron jobs, and agents without MCP registration (e.g. the Richmond
General pricing workflow) get byte-identical output to a tool call. This
file is deliberately a THIN argparse wrapper over the exact tool functions
in scripts/comps_mcp_server.py — one source of truth for what a read
returns.

Usage (from the repo root, with the dedicated CDP Chrome running — the
Richmond General wrapper ops/scripts/ebay-comps starts it for you):

    .venv/bin/python scripts/comps_cli.py absorption "boston champion pencil sharpener"
    .venv/bin/python scripts/comps_cli.py absorption "sega nomad" --condition-id 3000
    .venv/bin/python scripts/comps_cli.py comps "Boston Champion hand-crank sharpener, complete" \
        --query "boston champion pencil sharpener" --with-evidence --rows-out rows.json

Guards exit nonzero with the reason on stderr — a wrong number never
leaves as exit 0: NonAnnualWindow (window not a year, or a sale dated
outside it), SuspectEmpty (empty without eBay's zero message),
ChallengePage (signed out / bot wall), UnknownConditionId,
CDPUnavailable (Chrome not answering), TimeoutError (--timeout hit).
"""

from __future__ import annotations

import argparse
import json
import signal
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
      signed out / bot wall, empty response without eBay's zero message,
      window not a year or a sale dated outside it, unknown condition id,
      Chrome not answering, --timeout exceeded.

prerequisite: the dedicated CDP Chrome on port 9222 (profile
~/.btf-chrome-profile, signed in to Seller Hub). All figures are
eBay-channel only. Do not wrap this in `timeout` (not on macOS) — use
--timeout. Gotchas: docs/PLAYBOOK-ebay-velocity.md."""


def _deadline(seconds: int) -> None:
    """A hard wall-clock limit that raises inside the read (SIGALRM), so a
    hung page becomes an ordinary refusal on stderr, never a stuck agent."""
    if seconds <= 0:
        return

    def _expired(signum, frame):
        raise TimeoutError(f"read exceeded --timeout {seconds}s")

    signal.signal(signal.SIGALRM, _expired)
    signal.alarm(seconds)


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
        help="save the raw research API responses under data/comps/")
    p_comps.add_argument(
        "--screenshots", action="store_true",
        help="also save Seller Hub screenshots (slower; implies "
             "--with-evidence)")
    p_comps.add_argument(
        "--rows-out", type=Path, default=None,
        help="write every sold row (price, shipping, qty, date, /itm/ link, "
             "comp verdict) to this JSON file; stdout stays compact")
    p_comps.add_argument("--condition-id", type=int, default=None,
                         help=_CONDITION_HELP)
    for p in (p_abs, p_comps):
        p.add_argument("--timeout", type=int, default=180,
                       help="hard wall-clock limit in seconds (default 180; "
                            "0 = none)")

    args = parser.parse_args(argv)
    _deadline(args.timeout)
    try:
        if args.command == "absorption":
            out = comps_mcp_server.ebay_absorption(
                args.query, condition_id=args.condition_id)
        else:
            out = comps_mcp_server.ebay_comps(
                args.identification, query=args.query,
                with_evidence=args.with_evidence,
                condition_id=args.condition_id,
                screenshots=args.screenshots,
                include_rows=args.rows_out is not None)
            if args.rows_out is not None:
                rows = out.pop("sold_rows", [])
                args.rows_out.parent.mkdir(parents=True, exist_ok=True)
                args.rows_out.write_text(json.dumps({
                    "identification": out["identification"],
                    "query": out["query"],
                    "captured_at": out["captured_at"],
                    "window": out["window"],
                    "condition_scope": out["condition_scope"],
                    "rows": rows}, indent=1, ensure_ascii=False))
                out["rows_out"] = str(args.rows_out)
    except Exception as e:
        print(f"{type(e).__name__}: {e} — read refused", file=sys.stderr)
        return 1
    finally:
        if args.timeout > 0:
            signal.alarm(0)
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
