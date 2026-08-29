#!/usr/bin/env python3
"""
scripts/cache_estatesales.py — Offline Cacher for EstateSales.NET listings.

Fetches the complete listing manifest, seller metadata, and high-resolution
1200x900 appraisal-grade images from EstateSales.NET, saving them locally so the
spatial clustering, triage fan-out, and appraisal test loops can execute
100% offline.

EstateSales.NET publishes high-resolution 1200x900 photos directly on its CDN
(picturescdn.estatesales.net) with zero WAF challenge, making it an ideal primary
or supplementary image source for cross-listed Blue Toad Fleet auctions.

Examples:
    python scripts/cache_estatesales.py https://www.estatesales.net/WI/Genoa-City/53128/5042877
    python scripts/cache_estatesales.py 5042877 --output-dir data/aug22_es_5042877
    python scripts/cache_estatesales.py 5042877 --no-images
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.intake.estatesales import cache_estatesales_listing, extract_sale_id


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Cache EstateSales.NET listing drop and appraisal-grade images offline."
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="https://www.estatesales.net/WI/Genoa-City/53128/5042877",
        help="EstateSales.NET listing URL or numeric Sale ID (default: 5042877 for Aug 22 sale)",
    )
    parser.add_argument(
        "--url",
        default=None,
        help="EstateSales.NET URL (overrides positional target)",
    )
    parser.add_argument(
        "--sale-id",
        default=None,
        help="EstateSales.NET numeric sale ID (overrides positional target)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Destination directory (default: data/estatesales_<sale_id>)",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="Only fetch metadata & write manifest.json without downloading images",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Concurrent download threads (default: 8)",
    )
    parser.add_argument(
        "--no-verify-grade",
        action="store_true",
        help="Skip appraisal-grade resolution checks on downloaded images",
    )

    args = parser.parse_args()

    target = args.url or args.sale_id or args.target
    sale_id = extract_sale_id(target)
    if not sale_id:
        print(f"[!] Error: Could not determine valid EstateSales.NET sale ID from '{target}'", file=sys.stderr)
        return 1

    out_dir = args.output_dir or f"data/estatesales_{sale_id}"

    try:
        results = cache_estatesales_listing(
            url_or_id=target,
            output_dir=out_dir,
            max_workers=args.workers,
            download_images=not args.no_images,
            verify_grade=not args.no_verify_grade,
        )
    except Exception as e:
        print(f"[!] Caching failed: {e}", file=sys.stderr)
        return 1

    manifest = results["manifest"]
    meta = results["metadata"]
    print("\n" + "=" * 60)
    print(f"Sale:     {meta['name']}")
    print(f"Seller:   {meta['seller'].get('name', 'N/A')} ({meta['seller'].get('phone', 'N/A')})")
    print(f"Location: {meta['location'].get('city')}, {meta['location'].get('state')} {meta['location'].get('postal_code')}")
    print(f"Photos:   {manifest['total_photos']} total ({manifest['captioned_photos']} captioned)")
    print(f"Output:   {out_dir}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
