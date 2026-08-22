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
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.appraiser.images import (
    full_size_url, image_dimensions, image_mime_type, is_appraisal_grade,
)
from src.intake.manifest import clean_caption

_PHOTO_PATTERN = re.compile(
    r"onClick=\"DisplayFullImage\((\d+),(\d+),(\d+)\)\"><img src=\"([^\"]+)\".*?<center><b>(.*?)</b></center>",
    re.DOTALL,
)

@dataclass(frozen=True)
class DownloadResult:
    ok: bool
    error: str = ""
    sha256: str | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    byte_size: int = 0


def _result(data: bytes) -> DownloadResult:
    dimensions = image_dimensions(data)
    mime_type = image_mime_type(data)
    if not mime_type or not dimensions or not is_appraisal_grade(data):
        detail = (f"{dimensions[0]}x{dimensions[1]}" if dimensions
                  else f"{len(data)} unreadable bytes")
        return DownloadResult(False, f"not an appraisal-grade image: {detail}")
    return DownloadResult(
        True,
        sha256=hashlib.sha256(data).hexdigest(),
        mime_type=mime_type,
        width=dimensions[0],
        height=dimensions[1],
        byte_size=len(data),
    )


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.name}.", suffix=".partial", delete=False)
    temporary = Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _atomic_json(path: Path, payload: dict) -> None:
    _atomic_write(path, (json.dumps(payload, indent=2) + "\n").encode())


def _normalise_mime(value: str) -> str:
    value = (value or "").split(";", 1)[0].strip().casefold()
    return {"image/jpg": "image/jpeg", "image/x-png": "image/png"}.get(value, value)

def fetch_photopanel_html(listing_id: str, feed: str = "129") -> str:
    url = f"https://www.auctionzip.com/cgi-bin/photopanel.cgi?listingid={listing_id}&feed={feed}&gid=0&category=0&zip=&kwd=&PageImages=0"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")

def download_image(
    url: str,
    dest_path: Path,
    max_retries: int = 3,
    *,
    opener=urllib.request.urlopen,
) -> DownloadResult:
    if dest_path.exists() and dest_path.stat().st_size > 0:
        existing = _result(dest_path.read_bytes())
        if existing.ok:
            return existing

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
            with opener(req, timeout=15) as resp:
                content_type = _normalise_mime(str(resp.headers.get("Content-Type") or ""))
                if not content_type.casefold().startswith("image/"):
                    raise ValueError(
                        f"response content type is {content_type or 'missing'}, not image/*")
                data = resp.read()
                result = _result(data)
                if not result.ok:
                    raise ValueError(result.error)
                if result.mime_type != content_type:
                    raise ValueError(
                        f"response declares {content_type}, bytes are {result.mime_type}")
                _atomic_write(dest_path, data)
                return result
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"[-] Failed to download {url}: {e}", file=sys.stderr)
                return DownloadResult(False, str(e))
            time.sleep(0.5)
    return DownloadResult(False, "exhausted retries")

def cache_gallery(
    listing_id: str,
    output_dir: str,
    max_workers: int = 8,
    download_images: bool = True,
) -> int:
    out = Path(output_dir)
    images_dir = out / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    print(f"[*] Fetching photopanel manifest for listing {listing_id}...")
    html = fetch_photopanel_html(listing_id)
    matches = _PHOTO_PATTERN.findall(html)

    if not matches:
        print(f"[!] No photos parsed from photopanel HTML for listing {listing_id}", file=sys.stderr)
        return 1

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

    failures = 0
    if download_images:
        print(f"[*] Downloading {len(manifest_entries)} images with {max_workers} threads...")
        success = 0
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_entry = {
                executor.submit(download_image, e["full_url"], Path(e["local_path"])): e
                for e in manifest_entries
            }
            for future in as_completed(future_to_entry):
                entry = future_to_entry[future]
                result = future.result()
                if result.ok:
                    success += 1
                    entry.update({
                        "sha256": result.sha256,
                        "mime_type": result.mime_type,
                        "width": result.width,
                        "height": result.height,
                        "byte_size": result.byte_size,
                        "download_status": "usable",
                    })
                else:
                    failures += 1
                    entry.update({
                        "download_status": "failed",
                        "download_error": result.error,
                    })

        print(f"[✓] Successfully cached {success}/{len(manifest_entries)} images into {images_dir}")

    manifest_file = out / "manifest.json"
    _atomic_json(manifest_file, {
        "listing_id": listing_id,
        "total_photos": len(manifest_entries),
        "captioned_photos": sum(1 for e in manifest_entries if e["has_caption"]),
        "photos": manifest_entries,
    })
    print(f"[✓] Saved manifest to {manifest_file}")
    return 1 if failures else 0

def main() -> int:
    parser = argparse.ArgumentParser(description="Cache AuctionZip gallery drop offline.")
    parser.add_argument("--listing-id", default="4160518", help="AuctionZip listing ID (default: 4160518 for Aug 22)")
    parser.add_argument("--output-dir", default=None, help="Destination directory (default: data/gallery_<listing_id>)")
    parser.add_argument("--no-images", action="store_true", help="Only save manifest, don't download image binaries")
    parser.add_argument("--workers", type=int, default=8, help="Concurrent download threads")
    args = parser.parse_args()

    out_dir = args.output_dir or f"data/gallery_{args.listing_id}"
    return cache_gallery(
        listing_id=args.listing_id,
        output_dir=out_dir,
        max_workers=args.workers,
        download_images=not args.no_images,
    )

if __name__ == "__main__":
    raise SystemExit(main())
