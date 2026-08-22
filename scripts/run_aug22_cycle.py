#!/usr/bin/env python3
"""Retired writer for the obsolete twelve-bid August schedule."""

from __future__ import annotations

import sys


def main() -> int:
    print(
        "[REFUSED] This legacy runner cannot write bid artifacts. Use "
        "`python -m scripts.run_vertex_pipeline` for the canonical August "
        "compatibility cycle, or stage a new cycle with scripts/stage_cycle.py.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
