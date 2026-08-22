#!/usr/bin/env python3
"""Validate a read-only Seller Hub capture into typed absorption evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

from src.evidence import AbsorptionEvidence


_WINDOW = re.compile(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4})\s*[–-]\s*([A-Z][a-z]{2}) (\d{1,2}), (\d{4})")
_ACTIVE = re.compile(r"(?:^|\|)\s*(\d+)\s*\|\s*Total active listings", re.I)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_window(displayed: str) -> tuple[str, str]:
    match = _WINDOW.search(displayed or "")
    if not match:
        raise ValueError("capture has no authoritative displayed sold window")
    start = datetime.strptime(" ".join(match.group(1, 2, 3)), "%b %d %Y").date()
    end = datetime.strptime(" ".join(match.group(4, 5, 6)), "%b %d %Y").date()
    return start.isoformat(), end.isoformat()


def import_capture(capture_path: Path, *, reviewer: str) -> AbsorptionEvidence:
    capture = json.loads(capture_path.read_text())
    sold = capture.get("sold") or {}
    active = capture.get("active") or {}
    window_start, window_end = _parse_window(sold.get("window_as_printed_by_page") or "")
    active_match = _ACTIVE.search(active.get("aggregate_verbatim") or "")
    if not active_match:
        raise ValueError("capture has no Total active listings denominator")
    pages = str(sold.get("pages_walked") or "")
    complete = "complete" in pages.casefold() or "short page" in pages.casefold()

    source_paths = {"capture": capture_path}
    for label, value in (capture.get("screenshots") or {}).items():
        if label not in {"sold", "active"}:
            continue
        source_paths[f"screenshot_{label}"] = capture_path.parent / str(value)
    sold_tsv = capture_path.parent / "sold_365d.tsv"
    if sold_tsv.is_file():
        source_paths["sold_rows"] = sold_tsv
    missing = [str(path) for path in source_paths.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError("capture evidence is missing: " + ", ".join(missing))

    evidence = AbsorptionEvidence(
        schema_version=1,
        lot_id=str(capture.get("lot_id") or ""),
        query=str(capture.get("query") or ""),
        marketplace=str(capture.get("marketplace") or ""),
        window_start=window_start,
        window_end=window_end,
        displayed_window=str(sold["window_as_printed_by_page"]),
        sold_units_last_365_days=int(sold.get("units") or 0),
        sold_rows=int(sold.get("rows") or 0),
        active_listings_now=int(active_match.group(1)),
        sold_pages_complete=complete,
        sold_page_count=max(1, pages.casefold().count("offset")),
        captured_at=str((capture.get("screenshots") or {}).get("captured_at")
                        or sold.get("captured_at") or ""),
        reviewer=reviewer.strip(),
        source_sha256={name: _sha256(path) for name, path in source_paths.items()},
    )
    recorded = capture.get("absorption")
    if recorded is not None and float(recorded) != evidence.absorption:
        raise ValueError(
            f"capture says absorption {recorded}, counts produce {evidence.absorption}")
    return evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--reviewer", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        evidence = import_capture(args.capture, reviewer=args.reviewer)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(evidence.as_dict(), indent=2) + "\n")
        temporary.replace(args.output)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"absorption import refused: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {args.output} (absorption {evidence.absorption:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
