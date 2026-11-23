#!/usr/bin/env python3
"""
scripts/cache_estatesales.py — Offline cacher for EstateSales.NET sale drops.

Blue Toad cross-lists its sales on estatesales.net at 1200x900 JPEG on
`picturescdn.estatesales.net` with no AWS WAF challenge — five times the pixels
of AuctionZip's 560x420 `_fl`, though usually a subset of the gallery and
without AuctionZip's captions.

EstateSales.NET serves HTTP 404 on `/sale/<id>`; the state/city/zip route is
required (`https://www.estatesales.net/<ST>/<City>/<zip>/<sale_id>`). The page
embeds the sale entity and ordered `pictures` array in Angular's `NGRX_STATE`
JSON block. Thumbnail (`/1-2/`) and full-size (`/1-1/`) CDN URLs carry distinct
UUIDs, so missing `NGRX_STATE` fails closed rather than rewriting URLs.

    python scripts/cache_estatesales.py \
        https://www.estatesales.net/WI/Genoa-City/53128/5042877
    python scripts/cache_estatesales.py \
        https://www.estatesales.net/WI/Genoa-City/53128/5042877 --no-images
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.cache_gallery import _atomic_json, download_image  # noqa: E402
from src.intake.manifest import clean_caption  # noqa: E402

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
)
_NGRX_RE = re.compile(r'<script[^>]*>\s*(\{"NGRX_STATE"\s*:.*?\})\s*</script>', re.DOTALL)
_SAFE_ID_RE = re.compile(r"[A-Za-z0-9_-]+")
_HOSTS = {"estatesales.net", "www.estatesales.net"}

_EPILOG = """\
exit status:
  0   manifest written and every requested image verified at appraisal grade
  1   invalid URL, missing NGRX_STATE, or one or more image downloads failed"""


def parse_sale_url(url: str) -> tuple[str, str]:
    """Return `(sale_id, canonical_url)` for a full EstateSales.NET listing URL."""
    cleaned = (url or "").strip()
    if cleaned.isdigit():
        raise ValueError(
            "EstateSales.NET serves 404 on /sale/<id>; pass the full state/city/zip URL "
            f"(e.g. https://www.estatesales.net/WI/Genoa-City/53128/{cleaned}), got {url!r}"
        )
    parsed = urllib.parse.urlsplit(cleaned)
    host = (parsed.hostname or "").lower()
    parts = [p for p in parsed.path.split("/") if p]
    if parsed.scheme not in {"http", "https"} or host not in _HOSTS:
        raise ValueError(
            f"expected an https://www.estatesales.net/<ST>/<City>/<zip>/<id> URL, got {url!r}"
        )
    if len(parts) < 4 or not parts[-1].isdigit():
        raise ValueError(
            "EstateSales.NET serves 404 on /sale/<id>; pass the full state/city/zip URL "
            f"(e.g. https://www.estatesales.net/WI/Genoa-City/53128/5042877), got {url!r}"
        )
    canonical = urllib.parse.urlunsplit(
        ("https", "www.estatesales.net", parsed.path.rstrip("/"), "", "")
    )
    return parts[-1], canonical


def _require_http_url(url: str, label: str) -> str:
    candidate = "https:" + url if url.startswith("//") else url
    parsed = urllib.parse.urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"invalid {label} URL: {url!r}")
    return candidate


def fetch_listing_html(url: str, *, timeout: float = 20.0, opener=urllib.request.urlopen) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    with opener(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_listing_html(html: str, sale_id: str) -> tuple[str, list[dict]]:
    """Extract `(sale_name, ordered_pictures)` from embedded `NGRX_STATE` JSON."""
    match = _NGRX_RE.search(html or "")
    if not match:
        raise ValueError(f"no NGRX_STATE JSON found in page for sale {sale_id}")
    state = json.loads(match.group(1)).get("NGRX_STATE")
    if not isinstance(state, dict):
        raise ValueError(f"malformed NGRX_STATE for sale {sale_id}")

    entity = None
    for slice_state in state.values():
        entities = slice_state.get("entitiesById") if isinstance(slice_state, dict) else None
        if isinstance(entities, dict) and sale_id in entities:
            candidate = entities[sale_id]
            if isinstance(candidate, dict) and str(
                candidate.get("saleId") or candidate.get("id") or ""
            ) == sale_id:
                entity = candidate
                break
    if entity is None:
        raise ValueError(f"sale {sale_id} not present in NGRX_STATE")

    raw_pictures = entity.get("pictures")
    if not isinstance(raw_pictures, list) or not raw_pictures:
        raise ValueError(f"sale {sale_id} has no pictures in NGRX_STATE")

    pictures = []
    for pic in sorted(raw_pictures, key=lambda p: int(p.get("pictureOrder", 0))):
        photo_id = str(pic.get("id") or "")
        if not _SAFE_ID_RE.fullmatch(photo_id):
            raise ValueError(f"sale {sale_id} has unsafe picture id: {photo_id!r}")
        full_url = pic.get("url") or ""
        best_width = int(pic.get("width") or 0)
        for variant in pic.get("images") or ():
            width = int(variant.get("width") or 0)
            if variant.get("url") and width > best_width:
                full_url = variant["url"]
                best_width = width
        if not full_url:
            raise ValueError(f"sale {sale_id} picture {photo_id} has no image URL")
        checked_full = _require_http_url(full_url, f"picture {photo_id}")
        raw_thumb = pic.get("thumbnailUrl")
        checked_thumb = (
            _require_http_url(raw_thumb, f"thumbnail {photo_id}") if raw_thumb else checked_full
        )
        caption = clean_caption(pic.get("description") or "")
        pictures.append({
            "es_order": int(pic.get("pictureOrder", 0)),
            "photo_id": photo_id,
            "caption": caption,
            "thumb_url": checked_thumb,
            "full_url": checked_full,
        })
    return str(entity.get("name") or ""), pictures


def cache_estatesales(
    url: str,
    output_dir: str | Path | None = None,
    *,
    max_workers: int = 8,
    download_images: bool = True,
    opener=urllib.request.urlopen,
) -> int:
    if max_workers < 1:
        raise ValueError(f"workers must be >= 1, got {max_workers}")
    sale_id, canonical_url = parse_sale_url(url)
    out = Path(output_dir) if output_dir is not None else Path(f"data/estatesales_{sale_id}")
    images_dir = out / "images"
    out.mkdir(parents=True, exist_ok=True)

    print(f"[*] Fetching EstateSales.NET listing {sale_id}...")
    html = fetch_listing_html(canonical_url, opener=opener)
    sale_name, pictures = parse_listing_html(html, sale_id)
    print(f"[+] Found {len(pictures)} photos for {sale_name or sale_id!r}.")

    manifest_entries = []
    for seq, pic in enumerate(pictures, start=1):
        filename = f"{seq:03d}_{pic['photo_id']}.jpg"
        manifest_entries.append({
            "sequence": seq,
            "es_order": pic["es_order"],
            "photo_id": pic["photo_id"],
            "filename": filename,
            "caption": pic["caption"],
            "has_caption": bool(pic["caption"]),
            "thumb_url": pic["thumb_url"],
            "full_url": pic["full_url"],
            "local_path": str(images_dir / filename),
        })

    failures = 0
    if download_images:
        images_dir.mkdir(parents=True, exist_ok=True)
        print(f"[*] Downloading {len(manifest_entries)} images with {max_workers} threads...")
        success = 0
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {
                pool.submit(
                    download_image,
                    entry["full_url"],
                    Path(entry["local_path"]),
                    referer="https://www.estatesales.net/",
                    opener=opener,
                ): entry
                for entry in manifest_entries
            }
            for future in as_completed(futures):
                entry = futures[future]
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
        print(f"[✓] Cached {success}/{len(manifest_entries)} images into {images_dir}")

    manifest_file = out / "manifest.json"
    _atomic_json(manifest_file, {
        "listing_id": sale_id,
        "source": "estatesales.net",
        "url": canonical_url,
        "name": sale_name,
        "total_photos": len(manifest_entries),
        "captioned_photos": sum(1 for e in manifest_entries if e["has_caption"]),
        "photos": manifest_entries,
    })
    print(f"[✓] Saved manifest to {manifest_file}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Cache an EstateSales.NET listing manifest and 1200x900 images offline.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "url",
        help="full EstateSales.NET listing URL (https://www.estatesales.net/<ST>/<City>/<zip>/<id>)",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="destination directory (default: data/estatesales_<sale_id>)",
    )
    parser.add_argument(
        "--no-images",
        action="store_true",
        help="write manifest.json only without fetching image binaries",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="concurrent image download threads (default: 8)",
    )
    args = parser.parse_args(argv)

    try:
        return cache_estatesales(
            args.url,
            output_dir=args.output_dir,
            max_workers=args.workers,
            download_images=not args.no_images,
        )
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"[!] {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
