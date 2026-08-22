#!/usr/bin/env python3
"""Quarantined historical benchmark entry point.

The retained workbook is not submission evidence: its legacy total includes
summary rows, its synthetic comparison does not run the current pipeline, its
detail join is positional, and its shortened ids collide. Rebuilding it requires
the audited procedure in remediation-plan Task 23.
"""

from __future__ import annotations

import sys


QUARANTINE_REASON = (
    "July 11 benchmark is historical/unverified and cannot produce a release "
    "artifact; follow remediation-plan Task 23 to rebuild it from auditable input"
)


def main() -> int:
    print(f"[REFUSED] {QUARANTINE_REASON}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
