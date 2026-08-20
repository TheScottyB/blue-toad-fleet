#!/usr/bin/env python3
"""
scripts/recache_full_size.py — replace a cached thumbnail drop with full-size photos.

Works from an existing manifest, so it never re-fetches the photopanel HTML —
only the `_fl` image variant for each photo already listed. Adds `full_url` to
every manifest entry, downloads it over the `_th` file on disk, and verifies the
result against the same `is_appraisal_grade` check the appraiser enforces.

A download that comes back below appraisal grade is left reported, not silently
kept: the whole point of this script is that a too-small photo stops being
something the pipeline can swallow without noticing.

    python scripts/recache_full_size.py data/aug22_gallery_4160518
    python scripts/recache_full_size.py data/aug22_gallery_4160518 --only BT-002,BT-050
"""

import argparse
import json
import ssl
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.appraiser.images import full_size_url, image_dimensions, is_appraisal_grade

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def fetch(url: str, dest: Path, retries: int = 3) -> tuple[bool, str]:
    if url.startswith("//"):
        url = "https:" + url
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
                data = resp.read()
        except Exception as e:
            if attempt == retries - 1:
                return False, f"fetch failed: {e}"
            continue

        if not is_appraisal_grade(data):
            dims = image_dimensions(data)
            size = f"{dims[0]}x{dims[1]}" if dims else f"{len(data)} unreadable bytes"
            return False, f"served {size}, below appraisal grade"

        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        return True, ""

    return False, "exhausted retries"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("data_dir")
    ap.add_argument("--only", help="comma-separated lot ids, e.g. BT-002,BT-050")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    manifest_path = Path(args.data_dir) / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    photos = manifest["photos"]

    # Record the full-size URL for every photo, whether or not we fetch it now.
    for p in photos:
        p["full_url"] = full_size_url(p["thumb_url"])
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"[+] Recorded full_url for {len(photos)} photo(s) in {manifest_path}")

    targets = photos
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        targets = [p for p in photos if f"BT-{p['sequence']:03d}" in wanted]
        missing = wanted - {f"BT-{p['sequence']:03d}" for p in targets}
        if missing:
            print(f"[!] Not in manifest: {sorted(missing)}", file=sys.stderr)

    print(f"[*] Fetching {len(targets)} full-size photo(s) with {args.workers} workers...")
    ok, failures = 0, []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(fetch, p["full_url"], Path(p["local_path"])): p
            for p in targets
        }
        for f in as_completed(futures):
            p = futures[f]
            success, why = f.result()
            if success:
                ok += 1
            else:
                failures.append((f"BT-{p['sequence']:03d}", why))

    print(f"[{'✓' if not failures else '!'}] {ok}/{len(targets)} at appraisal grade")
    for lot_id, why in sorted(failures)[:20]:
        print(f"    {lot_id}: {why}")
    if len(failures) > 20:
        print(f"    ... and {len(failures) - 20} more")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
