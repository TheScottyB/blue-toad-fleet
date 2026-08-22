#!/usr/bin/env python3
"""Store a sanctioned local gallery drop in Cloud Storage and optionally start it.

READY is uploaded last. With the Eventarc trigger installed, ``--start`` is the
operator's explicit kick-off action; without it the cloud copy is staged only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.cycles import (  # noqa: E402
    CycleRepository, CycleRequest, GCSObjectStore, LocalObjectStore,
)


def _repository(args) -> CycleRepository:
    if args.local_root:
        return CycleRepository(LocalObjectStore(args.local_root))
    project = args.project or os.environ.get(
        "GOOGLE_CLOUD_PROJECT", "threebatdrone-prod-420")
    bucket = args.bucket or os.environ.get(
        "BTF_CYCLE_BUCKET", f"{project}-blue-toad-cycles")
    return CycleRepository(GCSObjectStore(bucket))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source-dir", help="Directory containing manifest.json and images/")
    ap.add_argument("--cycle-id", required=True, help="Stable cycle id, e.g. 2026-09-05")
    ap.add_argument("--listing-id", help="Auction listing id; defaults to the manifest")
    ap.add_argument("--shop-id", default="richmond-general")
    ap.add_argument("--auction-title", help="Public auction title")
    ap.add_argument("--auction-date", help="Auction date, YYYY-MM-DD")
    ap.add_argument("--timezone", dest="timezone_name",
                    help="IANA timezone, e.g. America/Chicago")
    ap.add_argument("--venue", help="Auction venue or pickup location")
    ap.add_argument("--deadline", help="Bid deadline as ISO datetime with offset")
    ap.add_argument("--email-to", help="Auctioneer absentee-bid address")
    ap.add_argument("--budget-cap", type=float, default=600.0)
    ap.add_argument("--auto-send-threshold", type=float, default=35.0)
    ap.add_argument("--project")
    ap.add_argument("--bucket")
    ap.add_argument("--local-root", help="Credential-free local object-store root")
    ap.add_argument("--start", action="store_true",
                    help="write READY after upload, causing Eventarc to start processing")
    ap.add_argument("--ready-only", action="store_true",
                    help="write READY for a cycle that was staged previously")
    args = ap.parse_args()

    repo = _repository(args)
    if args.ready_only:
        if args.source_dir or not args.listing_id:
            ap.error("--ready-only requires --listing-id and does not accept --source-dir")
        request = repo.read_request(args.shop_id, args.cycle_id)
        if request.listing_id != args.listing_id:
            raise SystemExit("listing id does not match the staged cycle")
        marker = repo.mark_ready(request)
        print(json.dumps({"state": "ready", **marker}, indent=2))
        return 0

    if not args.source_dir:
        ap.error("--source-dir is required unless --ready-only is used")
    manifest_path = Path(args.source_dir) / "manifest.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    auction = manifest.get("auction") if isinstance(manifest.get("auction"), dict) else {}
    execution = {
        "auction_title": args.auction_title or auction.get("title"),
        "auction_date": args.auction_date or auction.get("date"),
        "timezone_name": args.timezone_name or auction.get("timezone"),
        "venue": args.venue or auction.get("venue"),
        "deadline": args.deadline or auction.get("deadline"),
        "email_to": (args.email_to or auction.get("email_to")
                     or "info@bluetoadauctions.com"),
    }
    missing = [name for name, value in execution.items()
               if name != "email_to" and not str(value or "").strip()]
    if missing:
        ap.error(
            "cycle metadata is required in manifest.auction or CLI: "
            + ", ".join(missing))
    listing_id = str(args.listing_id or manifest.get("listing_id") or "")
    request = CycleRequest(
        cycle_id=args.cycle_id,
        listing_id=listing_id,
        **execution,
        shop_id=args.shop_id,
        budget_cap=args.budget_cap,
        auto_send_threshold=args.auto_send_threshold,
        source=("sanctioned-gallery-drop:"
                + hashlib.sha256(manifest_bytes).hexdigest()),
    )
    marker = repo.stage_directory(request, args.source_dir, ready=args.start)
    print(json.dumps({
        "state": "ready" if args.start else "staged",
        "storage_backend": repo.backend_name,
        **marker,
    }, indent=2))
    if not args.start:
        print("Staged only. Re-run with --ready-only --listing-id "
              f"{request.listing_id} when the operator is ready to process.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
