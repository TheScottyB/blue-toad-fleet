#!/usr/bin/env python3
"""
scripts/cache_gallery.py — Offline Cacher for AuctionZip Gallery Drops.

Fetches the complete photopanel manifest and images once, saving them locally
so the full spatial clustering, triage fan-out, and lot decomposition test loops
can execute 100% offline without hitting AuctionZip repeatedly.

The photopanel markup only ever names the `_th` thumbnail — 140x105, ~5KB. That
is a contact sheet, not something an appraiser can read a hallmark off, so what
lands on disk is the `_fl` variant at 560x420. The thumbnail URL is still kept
in the manifest because it is what the page actually published.
"""

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.appraiser.images import full_size_url

_PREVIEW_PREFIX = re.compile(r"^\s*preview image for\s+", re.IGNORECASE)
_PHOTO_PATTERN = re.compile(
    r"onClick=\"DisplayFullImage\((\d+),(\d+),(\d+)\)\"><img src=\"([^\"]+)\".*?<center><b>(.*?)</b></center>",
    re.DOTALL,
)

def clean_caption(raw: str) -> str:
    cleaned = _PREVIEW_PREFIX.sub("", (raw or "").strip()).strip()
    return cleaned

def fetch_photopanel_html(listing_id: str, feed: str = "129") -> str:
    url = f"https://www.auctionzip.com/cgi-bin/photopanel.cgi?listingid={listing_id}&feed={feed}&gid=0&category=0&zip=&kwd=&PageImages=0"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, context=ctx, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def download_image(url: str, dest_path: Path, max_retries: int = 3) -> bool:
    if dest_path.exists() and dest_path.stat().st_size > 0:
        return True

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    if url.startswith("//"):
        url = "https:" + url

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko)",
            "Referer": "https://www.auctionzip.com/",
        },
    )
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=15) as resp:
                data = resp.read()
                dest_path.write_bytes(data)
                return True
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"[-] Failed to download {url}: {e}", file=sys.stderr)
                return False
            time.sleep(0.5)
    return False

def cache_gallery(listing_id: str, output_dir: str, max_workers: int = 8, download_images: bool = True):
    out = Path(output_dir)
    images_dir = out / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Fetching photopanel manifest for listing {listing_id}...")
    html = fetch_photopanel_html(listing_id)
    matches = _PHOTO_PATTERN.findall(html)

    if not matches:
        print(f"[!] No photos parsed from photopanel HTML for listing {listing_id}", file=sys.stderr)
        return

    print(f"[+] Found {len(matches)} photos in photopanel.")
    manifest_entries = []

    for listing, seq, feed, img_src, caption in matches:
        seq_num = int(seq)
        clean_cap = clean_caption(caption)
        
        photo_id_match = re.search(r"/(\d+)(?:_th|_fl)?$", img_src)
        photo_id = photo_id_match.group(1) if photo_id_match else f"fp_{seq_num:03d}"
        
        img_filename = f"{seq_num:03d}_{photo_id}.jpg"
        img_dest = images_dir / img_filename
        
        thumb_url = img_src if img_src.startswith("http") or img_src.startswith("//") else f"https://content.auctionzip.com{img_src}"
        
        manifest_entries.append({
            "sequence": seq_num,
            "photo_id": photo_id,
            "filename": img_filename,
            "caption": clean_cap,
            "has_caption": bool(clean_cap),
            "thumb_url": thumb_url,
            "full_url": full_size_url(thumb_url),
            "local_path": str(img_dest),
        })

    manifest_file = out / "manifest.json"
    manifest_file.write_text(json.dumps({
        "listing_id": listing_id,
        "total_photos": len(manifest_entries),
        "captioned_photos": sum(1 for e in manifest_entries if e["has_caption"]),
        "photos": manifest_entries,
    }, indent=2))
    print(f"[✓] Saved manifest to {manifest_file}")

    if download_images:
        print(f"[*] Downloading {len(manifest_entries)} images with {max_workers} threads...")
        success = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_entry = {
                executor.submit(download_image, e["full_url"], Path(e["local_path"])): e
                for e in manifest_entries
            }
            for future in as_completed(future_to_entry):
                if future.result():
                    success += 1

        print(f"[✓] Successfully cached {success}/{len(manifest_entries)} images into {images_dir}")

def main():
    parser = argparse.ArgumentParser(description="Cache AuctionZip gallery drop offline.")
    parser.add_argument("--listing-id", default="4160518", help="AuctionZip listing ID (default: 4160518 for Aug 22)")
    parser.add_argument("--output-dir", default=None, help="Destination directory (default: data/gallery_<listing_id>)")
    parser.add_argument("--no-images", action="store_true", help="Only save manifest, don't download image binaries")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent download threads")
    args = parser.parse_args()

    out_dir = args.output_dir or f"data/gallery_{args.listing_id}"
    cache_gallery(
        listing_id=args.listing_id,
        output_dir=out_dir,
        max_workers=args.workers,
        download_images=not args.no_images,
    )

if __name__ == "__main__":
    main()
